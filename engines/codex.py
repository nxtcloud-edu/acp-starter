"""Codex 엔진(codex-acp). Codex만의 점을 플랫폼 형식에 맞춘다.

- 샌드박스 홈의 config.toml(관리 블록): 레포의 AGENTS.md(개발 안내)를 읽지 않고, 허락을 묻지 않는
  웹 검색과 Apps 도구, 플러그인, 계정 플러그인, Codex만의 기억을 끈다(GOTCHAS.md).
- 홈 폴더(HOME)도 샌드박스 홈으로 돌린다. 홈 폴더의 ~/.agents/skills에 있는 개인 스킬을 읽지 않게 한다.
- Codex 자체의 기본 스킬(skill-creator 같은 .system 스킬)은 남는다. 플랫폼의 스킬과 섞이지 않게 플랫폼 안내로 알린다.
- 관리 블록은 features.키 꼴로 쓴다. 그래서 config.toml에 [features] 표를 따로 만들지 않는다(TOML에서 겹친다).
- 안전 모드 read-only: 쓰기와 인터넷은 허락을 받아야 한다. 읽기 명령은 묻지 않고 읽기만 되는 샌드박스에서 실행한다.
- 로그인: 샌드박스에 따로. 주소와 기기 코드.
- 명령을 따옴표로 한 번 더 감싸 보낸다. 여러 줄 명령은 줄바꿈을 그대로 둔다.
- 거절 선택지가 decline(건너뛰고 계속)과 cancel(차례를 멈춤) 둘이다. decline을 먼저 고른다.
  명령과 파일 고치기 요청에는 cancel만 줄 때가 많다. 그때 멈춘 차례는 base.send가 이어 가게 한다.
"""

import json
import os
import re

from engines.base import AcpEngine

# 샌드박스 config.toml의 맨 위에 두는 설정. 플랫폼이 엔진을 실행할 때마다 다시 쓴다.
MANAGED = {
    "project_doc_max_bytes": "0",       # 레포의 AGENTS.md(개발 안내)를 읽지 않는다
    "web_search": '"disabled"',         # 허락을 묻지 않는 자체 웹 검색을 끈다. 인터넷은 허락을 받아 쓴다
    "features.apps": "false",           # ChatGPT Apps 도구를 끈다. 그 안의 웹 도구도 허락을 묻지 않는다
    "features.plugins": "false",        # 플러그인을 끈다. 스킬과 도구는 플랫폼이 준다
    "features.remote_plugin": "false",  # 계정에 깔린 플러그인을 내려받지 않는다
    "features.memories": "false",       # Codex만의 기억을 끈다. 대화 기록은 플랫폼이 갖는다
}
BEGIN, END = "# >>> acp-starter가 관리하는 설정. 실행할 때마다 다시 쓴다.", "# <<< acp-starter"


class CodexEngine(AcpEngine):
    name = "codex"
    command = ["npx", "-y", "@agentclientprotocol/codex-acp@2.2.2"]
    home_env = "CODEX_HOME"
    env = {"INITIAL_AGENT_MODE": "read-only"}
    safe_mode = "read-only"
    login = ["codex", "login", "--device-auth"]
    logout = ["codex", "logout"]
    status = ["codex", "login", "status"]
    login_mode = "device"

    @classmethod
    def sandbox_env(cls):
        env = super().sandbox_env()
        # Codex는 CODEX_HOME과 따로 홈 폴더의 ~/.agents/skills에서 개인 스킬을 읽는다.
        # 홈 폴더도 샌드박스 홈으로 돌린다. 어댑터(npx)는 원래 캐시를 써서 다시 내려받지 않는다.
        env.setdefault("npm_config_cache", os.path.join(os.path.expanduser("~"), ".npm"))
        env["HOME"] = str(cls.home())
        return env

    @classmethod
    def prepare_home(cls, home):
        path = home / "config.toml"
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(managed_config(old), encoding="utf-8")

    @classmethod
    def logged_in(cls, returncode, output):
        return returncode == 0 and "Not logged in" not in output

    def choose_option(self, options, allow):
        if not allow:
            # 거절 선택지가 둘이다. decline은 그 도구만 건너뛰고 계속하고, cancel은 차례를 멈춘다.
            decline = next((o["optionId"] for o in options if o.get("optionId") == "decline"), None)
            if decline:
                return decline
        return super().choose_option(options, allow)

    def command_text(self, value):
        text = super().command_text(value)
        if len(text) > 1 and text[0] == text[-1] == '"':
            # 여러 줄 명령은 줄바꿈을 그대로 둔 채 감싸 온다. strict=False여야 풀린다(GOTCHAS.md).
            try:
                text = json.loads(text, strict=False)
            except json.JSONDecodeError:
                pass
        return text


def managed_config(old):
    """config.toml의 맨 위에 관리 블록을 둔다. 사용자가 쓴 다른 줄은 그대로 둔다.

    TOML은 같은 키를 두 번 쓰면 오류다. 그래서 관리하는 키를 맨 위(첫 [표] 앞)에서 쓴 줄은 지운다.
    """
    old = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "", old, flags=re.S)
    kept, in_table = [], False
    for line in old.splitlines():
        in_table = in_table or line.lstrip().startswith("[")
        key = line.split("=", 1)[0].strip()
        if not in_table and (key in MANAGED or line.startswith("# acp-starter:")):
            continue
        kept.append(line)
    block = [BEGIN] + [f"{key} = {value}" for key, value in MANAGED.items()] + [END]
    rest = "\n".join(kept).strip("\n")
    return "\n".join(block) + "\n" + (rest + "\n" if rest else "")
