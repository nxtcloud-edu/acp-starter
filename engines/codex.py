"""Codex 엔진(codex-acp). Codex만의 점을 플랫폼 형식에 맞춘다.

- 샌드박스 홈의 config.toml: 레포의 AGENTS.md(개발 안내)를 읽지 않게 한다.
- 안전 모드 read-only: 쓰기와 인터넷은 허락을 받아야 한다. 읽기 명령은 묻지 않고 읽기만 되는 샌드박스에서 실행한다.
- 로그인: 샌드박스에 따로. 주소와 기기 코드.
- 명령을 따옴표로 한 번 더 감싸 보낸다. 여러 줄 명령은 줄바꿈을 그대로 둔다.
"""

import json

from engines.base import AcpEngine

CONFIG = "# acp-starter: 플랫폼 안의 Codex가 레포의 AGENTS.md(개발 안내)를 읽지 않게 한다.\nproject_doc_max_bytes = 0\n"


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
        if not path.exists():
            path.write_text(CONFIG, encoding="utf-8")

    @classmethod
    def logged_in(cls, returncode, output):
        return returncode == 0 and "Not logged in" not in output

    def command_text(self, value):
        text = super().command_text(value)
        if len(text) > 1 and text[0] == text[-1] == '"':
            # 여러 줄 명령은 줄바꿈을 그대로 둔 채 감싸 온다. strict=False여야 풀린다(GOTCHAS.md).
            try:
                text = json.loads(text, strict=False)
            except json.JSONDecodeError:
                pass
        return text
