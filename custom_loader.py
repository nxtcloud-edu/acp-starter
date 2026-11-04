"""custom/ 폴더를 읽어 플랫폼에 잇는다.

학생이 바꾸는 파일은 custom/에 모여 있다. 이 모듈은 그 파일을 부를 때마다 새로 읽는다.
그래서 custom/의 파일을 고치면 대시보드를 다시 켜지 않아도 다음 요청부터 반영된다.
  brand.json  이름, 한 줄 소개, 강조색
  업무.md      플랫폼 안내에 들어가는 업무
  rules.py    허락 규칙

이 파일은 "플랫폼 층"이다. 플랫폼 안내와 허락 규칙은 어느 엔진으로 돌려도 똑같이 작동해야 한다.
그래서 여기서는 엔진 이름을 쓰지 않는다.
"""

import json
import os
import pathlib
import re
import types

ROOT = pathlib.Path(__file__).parent
CUSTOM = ROOT / "custom"

# 플랫폼 안내와 사람의 질문 사이에 넣는 줄. 에이전트는 이 줄 아래를 질문으로 읽는다.
PREAMBLE_END = "[여기까지 플랫폼 안내. 아래가 사용자의 요청이다]"

# 도구를 쓰는 방법. 엔진마다 버릇이 달라서(셸로 파일 쓰기, 시도 없이 거절됐다고 답하기) 모든 엔진에 같은 규칙을 보낸다.
TOOL_RULES = [
    "파일을 만들거나 고칠 때는 셸 명령(printf, echo, cat >) 대신 파일 쓰기 도구를 쓴다.",
    "쓰기, 명령, 인터넷이 필요하면 먼저 그 도구를 쓴다. 허락은 플랫폼이 사람이나 규칙에 묻는다. 시도하지 않고 거절되었다고 말하지 않는다.",
    "거절된 도구는 다시 요청하지 않는다. 그 도구 없이 할 수 있는 만큼 한 뒤, 하지 못한 것을 알린다.",
]

DEFAULT_BRAND = {"name": "내 에이전트 플랫폼", "tagline": "", "accent": "#087F87"}
DECISIONS = ("allow", "deny", "ask")
HISTORY_MESSAGES = 12          # 다시 연결할 때 보내는 앞의 대화: 최근 메시지 수
HISTORY_CHARS = 8000           # 그 대화의 전체 글자 수 상한(오래된 것부터 뺀다)
MESSAGE_CHARS = 1500           # 메시지 하나의 글자 수 상한


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


# ---- 플랫폼 안내 ----

def _without_comments(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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


def preamble(custom=CUSTOM, history=None):
    """엔진 세션을 열 때 에이전트에게 보내는 플랫폼 안내를 만든다. 업무, 도구 규칙, 앞의 대화가 들어간다.

    ACP에는 시스템 프롬프트 칸이 없다. 그래서 플랫폼은 이 글을 첫 질문 앞에 붙인다.
    안내에는 엔진 이름이 들어가지 않는다. 어느 엔진으로 연결해도 같은 안내를 받는다.
    history가 있으면 앞의 대화를 넣는다. 대화 기억이 엔진이 아니라 플랫폼에 있으므로 엔진을 바꿔도 이어진다.
    """
    lines = ["[플랫폼 안내] 이 플랫폼이 대화를 시작할 때 보내는 글이다.", ""]
    lines += ["## 업무", "", business(custom) or "아직 정하지 않았다. 사용자의 요청에 따른다.", ""]
    lines += ["## 도구를 쓸 때", ""] + [f"- {rule}" for rule in TOOL_RULES] + [""]
    past = "\n\n".join(history_lines(history))
    if past:
        lines += ["## 지금까지의 대화", "",
                  "아래는 사용자와 앞서 나눈 대화다. 다른 엔진에서 나눈 것일 수 있다. 이 대화에 이어서 답한다.", "",
                  past, ""]
    lines.append(PREAMBLE_END)
    return "\n".join(lines)


# ---- 허락 규칙 (custom/rules.py) ----

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


def decide(request, custom=CUSTOM):
    """custom/rules.py의 decide(request)를 부른다. request는 engines.ToolRequest다.

    돌려주는 값: (결정, 오류 글 또는 None).
    """
    try:
        module = _load("rules", custom)
        if module is None:
            return "ask", None
        result = module.decide(request)
    except Exception as error:  # 학생 코드의 어떤 오류도 플랫폼을 멈추지 않게 한다
        return "ask", f"rules.py 오류: {error!r}"
    if result not in DECISIONS:
        return "ask", f"rules.py가 {result!r}를 돌려주었습니다. allow, deny, ask 가운데 하나여야 합니다."
    return result, None


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
