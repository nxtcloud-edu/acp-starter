"""custom/ 폴더와 workspace/skills/를 읽어 플랫폼에 잇는다.

학생이 바꾸는 파일은 custom/에 모여 있다. 이 모듈은 그 파일을 부를 때마다 새로 읽는다.
그래서 custom/의 파일을 고치면 대시보드를 다시 켜지 않아도 다음 요청부터 반영된다.

이 파일은 "플랫폼 층"이다. 에이전트, 스킬, 플랫폼 안내, 허락 규칙, 결과 보내기는
어느 엔진(Kiro, Claude, Codex)으로 돌려도 똑같이 작동해야 한다. 그래서 여기서는 엔진 이름을 쓰지 않는다.
"""

import json
import os
import pathlib
import re
import types

import engines

ROOT = pathlib.Path(__file__).parent
CUSTOM = ROOT / "custom"
WORKSPACE = ROOT / "workspace"

# 플랫폼 안내와 사람의 질문 사이에 넣는 줄. 에이전트는 이 줄 아래를 질문으로 읽는다.
PREAMBLE_END = "[여기까지 플랫폼 안내. 아래가 사용자의 요청이다]"

# 도구를 쓰는 방법. 엔진마다 버릇이 달라서(셸로 파일 쓰기, 시도 없이 거절됐다고 답하기) 모든 엔진에 같은 규칙을 보낸다.
TOOL_RULES = [
    "파일을 만들거나 고칠 때는 셸 명령(printf, echo, cat >) 대신 파일 쓰기 도구를 쓴다.",
    "쓰기, 명령, 인터넷이 필요하면 먼저 그 도구를 쓴다. 허락은 플랫폼이 사람이나 규칙에 묻는다. 시도하지 않고 거절되었다고 말하지 않는다.",
    "거절된 도구는 다시 요청하지 않는다. 그 도구 없이 할 수 있는 만큼 한 뒤, 하지 못한 것을 알린다.",
]

DEFAULT_BRAND = {"name": "내 에이전트 플랫폼", "tagline": "", "accent": "#087F87"}
DEFAULT_AGENT = "기본_도우미"
DECISIONS = ("allow", "deny", "ask")
HISTORY_MESSAGES = 12          # 다시 연결할 때 보내는 앞의 대화: 최근 메시지 수
HISTORY_CHARS = 8000           # 그 대화의 전체 글자 수 상한(오래된 것부터 뺀다)
MESSAGE_CHARS = 1500           # 메시지 하나의 글자 수 상한
SAFE_NAME = re.compile(r"[^\W_][\w.\-]*")   # 첫 글자는 글자나 숫자(한글 포함)
ALL_SKILLS, NO_SKILLS = "모두", "없음"


class AgentError(Exception):
    """에이전트 파일이 없거나 틀렸을 때 낸다. status는 대시보드가 돌려줄 HTTP 코드다."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---- 이름과 색 ----

def brand(custom=CUSTOM):
    """custom/brand.json을 읽는다. 파일이 없거나 틀리면 기본값을 쓴다."""
    data = dict(DEFAULT_BRAND)
    try:
        loaded = json.loads((pathlib.Path(custom) / "brand.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if isinstance(loaded, dict):
        data.update({k: v for k, v in loaded.items() if not k.startswith("_")})
    return data


# ---- 머리말이 있는 md 파일 ----

def _front_matter(text):
    """첫머리의 --- 사이를 읽는다. 돌려주는 값: (머리말 dict, 본문)."""
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        if value.strip():
            meta[key.strip()] = value.strip()
    return meta, match.group(2)


def _without_comments(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---- 스킬 ----

def skills(workspace=WORKSPACE):
    """workspace/skills/*/SKILL.md의 머리말에서 이름, 설명, 예시 요청을 읽는다."""
    found = []
    for path in sorted(pathlib.Path(workspace, "skills").glob("*/SKILL.md")):
        meta, _ = _front_matter(path.read_text(encoding="utf-8"))
        found.append({
            "name": meta.get("name", path.parent.name),
            "description": meta.get("description", ""),
            "example": meta.get("example", ""),
            "path": f"skills/{path.parent.name}/SKILL.md",
        })
    return found


# ---- 에이전트 ----
#
# 에이전트 하나는 custom/agents/<이름>.md 파일 하나다. 파일 이름이 에이전트의 이름이다.
#   ---
#   engine: kiro                  돌릴 엔진(engines/의 이름). 빼면 첫 엔진
#   description: 한 줄 설명
#   skills: memo-to-json          쓸 스킬. 쉼표로 여럿. 빼면 모두, "없음"이면 하나도 쓰지 않는다
#   ---
#   (본문) 이 에이전트의 역할과 규칙. 플랫폼 안내에 들어간다.

def _agents_dir(custom):
    return pathlib.Path(custom) / "agents"


def default_engine():
    return engines.names()[0]


def _parse_agent(name, text):
    meta, body = _front_matter(text)
    value = meta.get("skills", ALL_SKILLS)
    if value == ALL_SKILLS:
        chosen = None
    elif value == NO_SKILLS:
        chosen = []
    else:
        chosen = [s.strip() for s in value.split(",") if s.strip()]
    return {"name": name, "engine": meta.get("engine") or default_engine(),
            "description": meta.get("description", ""), "skills": chosen,
            "role": _without_comments(body)}


def agents(custom=CUSTOM):
    """custom/agents/의 에이전트를 이름 순서로 돌려준다. README.md는 안내라서 뺀다."""
    folder = _agents_dir(custom)
    paths = sorted(folder.glob("*.md")) if folder.is_dir() else []
    return [_parse_agent(p.stem, p.read_text(encoding="utf-8")) for p in paths if p.name != "README.md"]


def agent(name, custom=CUSTOM):
    """에이전트 하나를 읽는다. 없으면 AgentError(404)."""
    path = _agents_dir(custom) / f"{name}.md"
    if not SAFE_NAME.fullmatch(name or "") or name == "README" or not path.is_file():
        raise AgentError(f"에이전트 '{name}'이 없습니다. custom/agents/에 {name}.md를 만드세요.", 404)
    return _parse_agent(name, path.read_text(encoding="utf-8"))


def save_agent(data, custom=CUSTOM, workspace=WORKSPACE, create=True):
    """에이전트 파일을 만들거나(create=True) 고친다. 틀린 값이면 AgentError."""
    name = str(data.get("name", "")).strip()
    if not SAFE_NAME.fullmatch(name) or name == "README":
        raise AgentError("이름에는 한글, 영문, 숫자, 밑줄(_), 점(.), 하이픈(-)만 쓰고 글자나 숫자로 시작한다. 공백은 밑줄로 바꾼다.")
    path = _agents_dir(custom) / f"{name}.md"
    if create and path.exists():
        raise AgentError(f"에이전트 '{name}'이 이미 있습니다.", 409)
    if not create and not path.exists():
        raise AgentError(f"에이전트 '{name}'이 없습니다.", 404)
    engine = str(data.get("engine") or default_engine())
    try:
        engines.get(engine)
    except engines.EngineError as error:
        raise AgentError(str(error))
    chosen = data.get("skills")
    if chosen is not None:
        known = {s["name"] for s in skills(workspace)}
        unknown = [s for s in chosen if s not in known]
        if unknown:
            raise AgentError(f"없는 스킬: {', '.join(unknown)}")
    description = " ".join(str(data.get("description", "")).split())
    skills_line = ALL_SKILLS if chosen is None else (", ".join(chosen) or NO_SKILLS)
    text = (f"---\nengine: {engine}\ndescription: {description}\nskills: {skills_line}\n---\n"
            f"{str(data.get('role', '')).strip()}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return agent(name, custom)


# ---- 플랫폼 안내 ----

def business(custom=CUSTOM):
    """custom/업무.md에서 주석(<!-- -->)을 뺀 내용을 돌려준다."""
    try:
        return _without_comments((pathlib.Path(custom) / "업무.md").read_text(encoding="utf-8"))
    except OSError:
        return ""


def history_lines(history):
    """대화 기록(conversations.py의 메시지)에서 사람과 에이전트가 나눈 말만 골라 안내에 넣을 줄로 만든다.

    플랫폼의 알림과 앞서 보낸 플랫폼 안내는 넣지 않는다. 길면 오래된 것부터 뺀다.
    """
    names = {"user": "사용자", "agent": "에이전트"}
    talk = [m for m in (history or []) if m.get("role") in names and (m.get("text") or "").strip()]
    lines = []
    for message in talk[-HISTORY_MESSAGES:]:
        text = message["text"].strip()
        if len(text) > MESSAGE_CHARS:
            text = text[:MESSAGE_CHARS] + " …(줄임)"
        lines.append(f"[{names[message['role']]}] {text}")
    while lines and sum(len(line) for line in lines) > HISTORY_CHARS:
        lines.pop(0)
    return lines


def history_text(history):
    """플랫폼이 가진 앞의 대화를 안내에 넣을 글로 만든다."""
    return "\n\n".join(history_lines(history))


def preamble(workspace=WORKSPACE, custom=CUSTOM, agent=None, history=None):
    """대화를 시작할 때 에이전트에게 보내는 플랫폼 안내를 만든다.

    ACP에는 시스템 프롬프트 칸이 없다. 그래서 플랫폼은 이 글을 첫 질문 앞에 붙인다.
    안내에는 엔진 이름이 들어가지 않는다. 같은 에이전트는 어느 엔진으로 돌려도 같은 안내를 받는다.
    history가 있으면 앞의 대화를 넣는다. 대화 기억이 엔진이 아니라 플랫폼에 있으므로 엔진을 바꿔도 이어진다.
    """
    lines = ["[플랫폼 안내] 이 플랫폼이 대화를 시작할 때 보내는 글이다.", ""]
    lines += ["## 업무", "", business(custom) or "아직 정하지 않았다. 사용자의 요청에 따른다.", ""]
    if agent:
        lines += [f"## 너의 역할: {agent['name']}", "", agent["role"] or agent["description"] or "정해지지 않았다.", ""]
    found = skills(workspace)
    if agent and agent["skills"] is not None:
        found = [s for s in found if s["name"] in agent["skills"]]
    if found:
        lines += ["## 쓸 수 있는 스킬", "",
                  "요청이 아래 스킬에 맞으면, 먼저 그 SKILL.md를 읽고 적힌 절차를 따른다. 경로는 작업 폴더 기준이다.", ""]
        lines += [f"- {s['name']}: {s['description']} (`{s['path']}`)" for s in found]
        lines.append("")
    lines += ["## 도구를 쓸 때", ""] + [f"- {rule}" for rule in TOOL_RULES] + [""]
    lines += ["## 결과 파일", "", "만든 결과 파일은 `outbox/`에 저장한다.", ""]
    past = history_text(history)
    if past:
        lines += ["## 지금까지의 대화", "",
                  "아래는 이 에이전트와 사용자가 앞서 나눈 대화다. 다른 엔진에서 나눈 것일 수 있다. 이 대화에 이어서 답한다.", "",
                  past, ""]
    lines.append(PREAMBLE_END)
    return "\n".join(lines)


# ---- custom/의 파이썬 파일 ----

def _load(name, custom=CUSTOM):
    """custom/<name>.py를 새로 읽는다. 파일이 없으면 None.

    import를 쓰지 않고 매번 소스를 실행한다. 그래서 고친 내용이 바로 반영되고, 캐시 파일도 남지 않는다.
    """
    path = pathlib.Path(custom) / f"{name}.py"
    if not path.is_file():
        return None
    module = types.ModuleType(f"custom_{name}")
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module


def decide(agent, request, custom=CUSTOM):
    """custom/rules.py의 decide(agent, request)를 부른다. request는 engines.ToolRequest다.

    돌려주는 값: (결정, 오류 글 또는 None).
    """
    try:
        module = _load("rules", custom)
        if module is None:
            return "ask", None
        result = module.decide(agent, request)
    except Exception as error:  # 학생 코드의 어떤 오류도 플랫폼을 멈추지 않게 한다
        return "ask", f"rules.py 오류: {error!r}"
    if result not in DECISIONS:
        return "ask", f"rules.py가 {result!r}를 돌려주었습니다. allow, deny, ask 가운데 하나여야 합니다."
    return result, None


def deliver(task, agent, path, text, custom=CUSTOM):
    """custom/deliver.py의 deliver(task, agent, path, text)를 부른다. 돌려주는 값: 오류 글 또는 None."""
    try:
        module = _load("deliver", custom)
        if module is not None:
            module.deliver(task, agent, pathlib.Path(path), text)
    except Exception as error:
        return f"deliver.py 오류: {error!r}"
    return None


def load_env(path=ROOT / ".env"):
    """.env의 KEY=VALUE 줄을 환경변수로 읽는다. 이미 있는 환경변수는 덮어쓰지 않는다."""
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
