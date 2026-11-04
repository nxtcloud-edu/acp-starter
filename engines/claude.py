"""Claude 엔진(claude-agent-acp, Claude Code). Claude만의 점을 플랫폼 형식에 맞춘다.

- 설정 파일을 읽지 않게 한다(settingSources: []). Claude는 작업 폴더의 상위 폴더를 거슬러
  올라가며 CLAUDE.md를 읽기 때문이다(GOTCHAS.md).
- Claude Code의 기본 스킬과 내장 플러그인의 스킬, 자동 메모리, claude.ai 계정의 스킬과 플러그인 동기를
  끈다(GOTCHAS.md).
  스킬은 플랫폼이 알린 것만 쓰고, 대화 기록은 플랫폼이 갖는다.
- 안전 모드 default: 파일 쓰기와 명령을 묻는다. 읽기 전용 명령(ls, date)은 묻지 않는다.
- 로그인: 샌드박스에 따로. 주소를 열고 받은 코드를 붙여 넣는다.
"""

from engines.base import AcpEngine

# 세션을 열 때 넘기는 설정. 설정 파일은 읽지 않으므로 여기서 넘긴다.
SETTINGS = {
    "disableBundledSkills": True,    # Claude Code 기본 스킬(code-review, loop 같은 것)을 끈다
    "autoMemoryEnabled": False,      # Claude만의 자동 메모리를 끈다. 대화 기록은 플랫폼이 갖는다
    "syncClaudeAiSkills": False,     # claude.ai 계정에서 켠 스킬을 내려받지 않는다
    "syncClaudeAiPlugins": False,    # claude.ai 계정에서 켠 플러그인을 내려받지 않는다
    "enabledPlugins": {"plugin-authoring@builtin": False},   # 기본 스킬을 꺼도 남는 내장 플러그인의 스킬
}


class ClaudeEngine(AcpEngine):
    name = "claude"
    command = ["npx", "-y", "@agentclientprotocol/claude-agent-acp@0.94.0"]
    home_env = "CLAUDE_CONFIG_DIR"
    env = {"CLAUDE_CODE_DISABLE_BUNDLED_SKILLS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
    safe_mode = "default"
    login = ["claude", "auth", "login"]
    logout = ["claude", "auth", "logout"]
    status = ["claude", "auth", "status"]
    login_mode = "code"

    def session_meta(self):
        return {"claudeCode": {"options": {"settingSources": [], "settings": dict(SETTINGS)}}}

    @classmethod
    def logged_in(cls, returncode, output):
        return returncode == 0 and '"loggedIn": false' not in output
