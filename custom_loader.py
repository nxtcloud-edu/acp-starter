"""custom/ 폴더와 workspace/skills/를 읽어 플랫폼에 잇는다.

학생이 바꾸는 파일은 custom/에 모여 있다. 이 모듈은 그 파일을 부를 때마다 새로 읽는다.
그래서 custom/의 파일을 고치면 대시보드를 다시 켜지 않아도 다음 요청부터 반영된다.
"""

import json
import os
import pathlib
import re
import types

ROOT = pathlib.Path(__file__).parent
CUSTOM = ROOT / "custom"
WORKSPACE = ROOT / "workspace"

# 플랫폼 안내와 사람의 질문 사이에 넣는 줄. 에이전트는 이 줄 아래를 질문으로 읽는다.
PREAMBLE_END = "[여기까지 플랫폼 안내. 아래가 사용자의 요청이다]"

DEFAULT_BRAND = {"name": "내 에이전트 플랫폼", "tagline": "", "accent": "#087F87"}
DECISIONS = ("allow", "deny", "ask")


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


# ---- 스킬 ----

def _front_matter(text):
    match = re.match(r"^---\n(.*?)\n---", text, re.S)
    meta = {}
    if match:
        for line in match.group(1).splitlines():
            key, _, value = line.partition(":")
            if value:
                meta[key.strip()] = value.strip()
    return meta


def skills(workspace=WORKSPACE):
    """workspace/skills/*/SKILL.md의 머리말에서 이름, 설명, 예시 요청을 읽는다."""
    found = []
    for path in sorted(pathlib.Path(workspace, "skills").glob("*/SKILL.md")):
        meta = _front_matter(path.read_text(encoding="utf-8"))
        found.append({
            "name": meta.get("name", path.parent.name),
            "description": meta.get("description", ""),
            "example": meta.get("example", ""),
            "path": f"skills/{path.parent.name}/SKILL.md",
        })
    return found


# ---- 플랫폼 안내 ----

def business(custom=CUSTOM):
    """custom/업무.md에서 주석(<!-- -->)을 뺀 내용을 돌려준다."""
    try:
        text = (pathlib.Path(custom) / "업무.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def preamble(workspace=WORKSPACE, custom=CUSTOM):
    """대화를 시작할 때 에이전트에게 보내는 플랫폼 안내를 만든다.

    ACP에는 시스템 프롬프트 칸이 없다. 그래서 플랫폼은 이 글을 첫 질문 앞에 붙인다.
    """
    lines = ["[플랫폼 안내] 이 플랫폼이 대화를 시작할 때 보내는 글이다.", ""]
    lines += ["## 업무", "", business(custom) or "아직 정하지 않았다. 사용자의 요청에 따른다.", ""]
    found = skills(workspace)
    if found:
        lines += ["## 쓸 수 있는 스킬", "",
                  "요청이 아래 스킬에 맞으면, 먼저 그 SKILL.md를 읽고 적힌 절차를 따른다. 경로는 작업 폴더 기준이다.", ""]
        lines += [f"- {s['name']}: {s['description']} (`{s['path']}`)" for s in found]
        lines.append("")
    lines += ["## 결과 파일", "", "만든 결과 파일은 `outbox/`에 저장한다.", "", PREAMBLE_END]
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
    """custom/rules.py의 decide(agent, request)를 부른다. request는 acp_client.ToolRequest다.

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


def deliver(task, path, text, custom=CUSTOM):
    """custom/deliver.py의 deliver()를 부른다. 돌려주는 값: 오류 글 또는 None."""
    try:
        module = _load("deliver", custom)
        if module is not None:
            module.deliver(task, pathlib.Path(path), text)
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
