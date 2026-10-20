"""Kiro CLI와 ACP로 대화하는 가장 작은 클라이언트.

흐름: kiro-cli acp 실행 → initialize → session/new → session/prompt
메시지는 JSON 한 줄씩 표준 입출력으로 주고받는다(JSON-RPC 2.0).
"""

import json
import os
import shutil
import subprocess


class AcpError(Exception):
    """연결이나 응답이 잘못되었을 때 낸다."""


class AcpClient:
    def __init__(self, workspace, agent, on_text=None, on_tool=None,
                 on_permission=None, command=None):
        # workspace: 에이전트가 일하는 폴더. 그 안의 .kiro/agents/<agent>.json을 읽는다.
        # on_text(text): 답의 조각이 올 때마다 부른다.
        # on_tool(update): 에이전트가 도구를 쓰기 시작하거나 끝낼 때 부른다.
        # on_permission(tool_call) -> bool: 허락이 필요할 때 부른다. 없으면 모두 거절한다.
        self.workspace = os.path.abspath(workspace)
        self.agent = agent
        self.on_text = on_text or (lambda text: None)
        self.on_tool = on_tool or (lambda update: None)
        self.on_permission = on_permission or (lambda tool_call: False)
        self.command = command
        self.process = None
        self.session_id = None
        self.credits = 0.0
        self._next_id = 0

    def start(self):
        command = self.command
        if command is None:
            executable = shutil.which("kiro-cli")
            if executable is None:
                raise AcpError("kiro-cli를 찾지 못했습니다. Kiro CLI를 설치하고 로그인하세요.")
            command = [executable]
        self.process = subprocess.Popen(
            [*command, "acp", "--agent", self.agent],
            cwd=self.workspace,
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
            "clientInfo": {"name": "kiro-acp-starter", "version": "0.1.0"},
        })
        # 2) 대화 하나를 연다.
        result = self._request("session/new", {"cwd": self.workspace, "mcpServers": []})
        current = result.get("modes", {}).get("currentModeId")
        if current != self.agent:
            raise AcpError(f"에이전트 '{self.agent}'를 찾지 못했습니다(지금: {current}).")
        self.session_id = result["sessionId"]

    def prompt(self, text):
        """질문 하나를 보내고, 에이전트가 이번 차례를 끝낼 때까지 기다린다."""
        result = self._request("session/prompt", {
            "sessionId": self.session_id,
            "prompt": [{"type": "text", "text": text}],
        })
        return result["stopReason"]

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
                raise AcpError("kiro-cli가 끝났습니다. 로그인 상태(kiro-cli whoami)를 확인하세요.")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "method" in message:
                self._handle(message)
            elif message.get("id") == request_id:
                if "error" in message:
                    raise AcpError(f"{method} 실패: {message['error'].get('message')}")
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

        # 알림: 답의 조각, 도구 사용
        if method == "session/update":
            update = params.get("update", {})
            kind = update.get("sessionUpdate")
            if kind == "agent_message_chunk":
                content = update.get("content", {})
                if content.get("type") == "text":
                    self.on_text(content["text"])
            elif kind in ("tool_call", "tool_call_update"):
                self.on_tool(update)
