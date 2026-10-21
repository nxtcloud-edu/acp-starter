"""Codex 엔진(codex-acp). Codex만의 점을 플랫폼 형식에 맞춘다.

- 샌드박스 홈의 config.toml: 레포의 AGENTS.md(개발 안내)를 읽지 않게 하고, 자체 웹 검색을 끈다.
  Codex의 웹 검색은 허락을 묻지 않아서, 켜 두면 인터넷이 허락 규칙을 거치지 않는다(GOTCHAS.md).
- 안전 모드 read-only: 쓰기와 인터넷은 허락을 받아야 한다. 읽기 명령은 묻지 않고 읽기만 되는 샌드박스에서 실행한다.
- 로그인: 샌드박스에 따로. 주소와 기기 코드.
- 명령을 따옴표로 한 번 더 감싸 보낸다. 여러 줄 명령은 줄바꿈을 그대로 둔다.
- 거절 선택지가 decline(건너뛰고 계속)과 cancel(차례를 멈춤) 둘이다. decline을 먼저 고른다.
  명령과 파일 고치기 요청에는 cancel만 줄 때가 많다. 그때 멈춘 차례는 base.send가 이어 가게 한다.
"""

import json
import re

from engines.base import AcpEngine

# 샌드박스 config.toml의 맨 위에 두는 설정. 플랫폼이 엔진을 실행할 때마다 다시 쓴다.
MANAGED = {
    "project_doc_max_bytes": "0",       # 레포의 AGENTS.md(개발 안내)를 읽지 않는다
    "web_search": '"disabled"',         # 허락을 묻지 않는 자체 웹 검색을 끈다. 인터넷은 허락을 받아 쓴다
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
