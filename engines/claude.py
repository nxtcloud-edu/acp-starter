"""Claude 엔진(claude-agent-acp, Claude Code). Claude만의 점을 플랫폼 형식에 맞춘다.

- 설정 파일을 읽지 않게 한다(settingSources: []). Claude는 작업 폴더의 상위 폴더를 거슬러
  올라가며 CLAUDE.md를 읽기 때문이다(GOTCHAS.md).
- 안전 모드 default: 파일 쓰기와 명령을 묻는다. 읽기 전용 명령(ls, date)은 묻지 않는다.
- 로그인: 샌드박스에 따로. 주소를 열고 받은 코드를 붙여 넣는다.
"""

from engines.base import AcpEngine


class ClaudeEngine(AcpEngine):
    name = "claude"
    command = ["npx", "-y", "@agentclientprotocol/claude-agent-acp@0.94.0"]
    home_env = "CLAUDE_CONFIG_DIR"
    safe_mode = "default"
    login = ["claude", "auth", "login"]
    logout = ["claude", "auth", "logout"]
    status = ["claude", "auth", "status"]
    login_mode = "code"

    def session_meta(self):
        return {"claudeCode": {"options": {"settingSources": []}}}

    @classmethod
    def logged_in(cls, returncode, output):
        return returncode == 0 and '"loggedIn": false' not in output
