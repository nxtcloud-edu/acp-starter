"""ACP로 엔진(Kiro, Claude, Codex)과 대화하는 가장 작은 클라이언트.

흐름: 에이전트 실행 → initialize → session/new → (안전 모드) → session/prompt
메시지는 JSON 한 줄씩 표준 입출력으로 주고받는다(JSON-RPC 2.0).

엔진마다 이 레포 안의 샌드박스 홈(.homes/<이름>/)을 쓴다.
그래서 내 컴퓨터의 전역 설정, 스킬, 플러그인, 기억을 가져오지 않는다.
"""

import json
import os
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).parent
ENGINES_FILE = ROOT / "engines.json"


class AcpError(Exception):
    """연결이나 응답이 잘못되었을 때 낸다."""


def load_engine(name):
    """engines.json에서 엔진 하나의 설정을 읽는다."""
    engines = json.loads(ENGINES_FILE.read_text(encoding="utf-8"))
    if name not in engines:
        raise AcpError(f"엔진 '{name}'가 engines.json에 없습니다. 고를 수 있는 것: {', '.join(engines)}")
    return engines[name]


def sandbox_env(name, engine):
    """샌드박스 홈을 가리키는 환경변수를 만든다. 폴더가 없으면 만든다."""
    home = ROOT / ".homes" / name
    home.mkdir(parents=True, exist_ok=True)
    # 샌드박스 홈에 둘 설정 파일. 이미 있으면 덮어쓰지 않는다.
    for file_name, content in engine.get("home_files", {}).items():
        path = home / file_name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    env = dict(os.environ)
    env[engine["home_env"]] = str(home)
    env.update(engine.get("env", {}))
    return env


class AcpClient:
    def __init__(self, workspace, engine="kiro", on_text=None, on_tool=None,
                 on_permission=None, preamble=None, command=None, env=None, config=None):
        # workspace: 에이전트가 일하는 폴더.
        # engine: engines.json의 이름(kiro, claude, codex).
        # on_text(text): 답의 조각이 올 때마다 부른다.
        # on_tool(update): 에이전트가 도구를 쓰기 시작하거나 끝낼 때 부른다.
        # on_permission(tool_call) -> bool: 허락이 필요할 때 부른다. 없으면 모두 거절한다.
        # preamble: 첫 질문 앞에 붙여 보낼 플랫폼 안내. ACP에는 시스템 프롬프트 칸이 없다.
        # command, env, config: 테스트에서 실행 명령과 설정을 바꿀 때만 쓴다.
        self.workspace = os.path.abspath(workspace)
        self.name = engine
        self.config = config if config is not None else load_engine(engine)
        self.on_text = on_text or (lambda text: None)
        self.on_tool = on_tool or (lambda update: None)
        self.on_permission = on_permission or (lambda tool_call: False)
        self.preamble = preamble
        self.command = command
        self.env = env
        self.process = None
        self.session_id = None
        self.credits = 0.0
        self.context_tokens = None
        self._next_id = 0

    def start(self):
        command = self.command or self.config["command"]
        executable = shutil.which(command[0])
        if executable is None:
            raise AcpError(f"{command[0]}를 찾지 못했습니다. README의 준비 절을 보세요.")
        env = self.env if self.env is not None else sandbox_env(self.name, self.config)
        self.process = subprocess.Popen(
            [executable, *command[1:]],
            cwd=self.workspace,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        # 1) 앱이 무엇을 해 줄 수 있는지 알린다. 파일과 터미널은 에이전트가 스스로 다룬다.
        self._request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False},
                "terminal": False,
            },
            "clientInfo": {"name": "acp-starter", "version": "0.3.0"},
        })
        # 2) 대화 하나를 연다.
        params = {"cwd": self.workspace, "mcpServers": []}
        if self.config.get("session_meta"):
            # Claude는 상위 폴더의 CLAUDE.md까지 읽으므로, 설정 파일을 읽지 않게 따로 알린다.
            params["_meta"] = self.config["session_meta"]
        result = self._request("session/new", params)
        self.session_id = result["sessionId"]
        expected = self.config.get("expect_mode")
        current = result.get("modes", {}).get("currentModeId")
        if expected and current != expected:
            raise AcpError(f"에이전트 '{expected}'를 찾지 못했습니다(지금: {current}).")
        # 3) 안전 모드로 바꾼다. 바꾸지 않으면 Claude와 Codex는 명령을 묻지 않고 실행한다.
        safe_mode = self.config.get("safe_mode")
        if safe_mode:
            self._request("session/set_mode", {"sessionId": self.session_id, "modeId": safe_mode})

    def prompt(self, text):
        """질문 하나를 보내고, 에이전트가 이번 차례를 끝낼 때까지 기다린다."""
        if self.preamble:
            # 플랫폼 안내는 이 대화의 첫 질문에만 붙인다.
            text, self.preamble = f"{self.preamble}\n\n{text}", None
        result = self._request("session/prompt", {
            "sessionId": self.session_id,
            "prompt": [{"type": "text", "text": text}],
        })
        return result["stopReason"]

    def usage_text(self):
        """쓴 양을 사람이 읽을 글로 돌려준다."""
        parts = []
        if self.credits:
            parts.append(f"크레딧 {self.credits:.3f}")
        if self.context_tokens is not None:
            parts.append(f"컨텍스트 {self.context_tokens:,}토큰")
        return ", ".join(parts) or "알 수 없음"

    def close(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for stream in (self.process.stdin, self.process.stdout):
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- 아래는 메시지를 주고받는 부분이다 ----

    def _send(self, message):
        message["jsonrpc"] = "2.0"
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def _request(self, method, params):
        """요청을 보내고, 같은 id의 응답이 올 때까지 사이에 오는 메시지를 처리한다."""
        self._next_id += 1
        request_id = self._next_id
        self._send({"id": request_id, "method": method, "params": params})
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise AcpError(f"{self.name} 에이전트가 끝났습니다. 로그인 상태를 확인하세요(python login.py {self.name}).")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "method" in message:
                self._handle(message)
            elif message.get("id") == request_id:
                if "error" in message:
                    error = message["error"]
                    detail = error.get("message", "")
                    if error.get("code") == -32000 or "auth" in detail.lower():
                        detail += f" (로그인이 필요하면: python login.py {self.name})"
                    raise AcpError(f"{method} 실패: {detail}")
                return message["result"]

    def _handle(self, message):
        method = message["method"]
        params = message.get("params", {})

        # 에이전트가 앱에게 묻는 요청: 도구를 써도 되는가
        if method == "session/request_permission":
            allowed = bool(self.on_permission(params.get("toolCall", {})))
            wanted = "allow_once" if allowed else "reject_once"
            option = next((o["optionId"] for o in params.get("options", [])
                           if o.get("kind") == wanted), None)
            if option is None:
                outcome = {"outcome": "cancelled"}
            else:
                outcome = {"outcome": "selected", "optionId": option}
            self._send({"id": message["id"], "result": {"outcome": outcome}})
            return

        # 이 앱이 모르는 요청에는 모른다고 답한다
        if "id" in message:
            self._send({"id": message["id"],
                        "error": {"code": -32601, "message": "Method not found"}})
            return

        # 알림: 사용한 크레딧(Kiro가 더한 확장 메시지)
        if method == "_kiro.dev/metadata":
            for usage in params.get("meteringUsage", []):
                if usage.get("unit") == "credit":
                    self.credits += usage.get("value", 0)
            return

        # 알림: 답의 조각, 도구 사용, 컨텍스트 사용량
        if method == "session/update":
            update = params.get("update", {})
            kind = update.get("sessionUpdate")
            if kind == "agent_message_chunk":
                content = update.get("content", {})
                if content.get("type") == "text":
                    self.on_text(content["text"])
            elif kind in ("tool_call", "tool_call_update"):
                self.on_tool(update)
            elif kind == "usage_update" and isinstance(update.get("used"), int):
                self.context_tokens = update["used"]
