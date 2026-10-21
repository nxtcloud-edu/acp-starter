"""Kiro 엔진(kiro-cli acp). Kiro만의 점을 플랫폼 형식에 맞춘다.

- 엔진 설정: 샌드박스 홈의 agents/engine.json을 플랫폼이 쓴다. 역할 문장(prompt)은 넣지 않는다.
  쓸 도구는 read, write, shell, web_fetch이고, 묻지 않고 쓰는 도구는 read뿐이다.
  settings/cli.json에는 기본 자원을 물려받지 않는 설정을 넣는다. 작업 폴더에는 Kiro만의 파일을 두지 않는다.
- 로그인: 샌드박스가 아니라 컴퓨터 전체에 걸린다. 그래서 화면에서 로그인하지 않는다.
- 허락 요청의 kind를 비워 보낸다. 시작 알림의 kind로 채운다(base.tool_request).
- 쓴 양: 확장 알림 _kiro.dev/metadata의 크레딧.
"""

import json

from engines.base import AcpEngine

SPEC = {
    "name": "engine",
    "description": "acp-starter의 Kiro 엔진 설정. 플랫폼이 실행할 때마다 다시 쓴다.",
    "tools": ["read", "write", "shell", "web_fetch"],
    "allowedTools": ["read"],
    "resources": [],
    "mcpServers": {},
    "includeMcpJson": False,
    "hooks": {},
}


class KiroEngine(AcpEngine):
    name = "kiro"
    command = ["kiro-cli", "acp", "--agent", "engine"]
    home_env = "KIRO_HOME"
    expect_mode = "engine"
    login = ["kiro-cli", "login"]
    status = ["kiro-cli", "whoami"]
    login_mode = "terminal"

    @classmethod
    def prepare_home(cls, home):
        folder = home / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "engine.json").write_text(json.dumps(SPEC, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # 기본 자원(AGENTS.md, README.md 같은 파일)을 에이전트 설정에 물려받지 않게 한다.
        # Kiro가 이 파일에 다른 설정도 쓰므로 덮어쓰지 않고 이 값만 넣는다.
        settings = home / "settings" / "cli.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if data.get("chat.disableInheritingDefaultResources") is not True:
            data["chat.disableInheritingDefaultResources"] = True
            settings.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def on_extension(self, method, params):
        if method == "_kiro.dev/metadata":
            for usage in params.get("meteringUsage", []):
                if usage.get("unit") == "credit":
                    self.credits += usage.get("value", 0)
