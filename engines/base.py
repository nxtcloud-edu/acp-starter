"""엔진 층의 바탕: ACP로 엔진 프로그램과 이야기하는 공통 코드.

플랫폼과 엔진 사이의 통역이다.
- 플랫폼 → 엔진: 플랫폼의 질문과 허락 여부를 그 엔진이 받는 ACP 메시지로 바꿔 보낸다.
- 엔진 → 플랫폼: 엔진마다 다른 메시지(답 조각, 도구 요청, 쓴 양, 끝난 까닭)를 하나의 형식으로 포장해 넘긴다.
  하나의 형식은 ToolRequest(도구 하나)와 TurnResult(한 차례의 결과)다.

엔진마다 다른 점은 engines/<이름>.py가 이 클래스의 값과 훅을 덮어써서 맞춘다.
메시지는 JSON 한 줄씩 표준 입출력으로 주고받는다(JSON-RPC 2.0).
"""

import json
import os
import pathlib
import re
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOMES = ROOT / ".homes"


class EngineError(Exception):
    """엔진을 실행하거나 엔진과 이야기하다 실패했을 때 낸다."""


# 도구 요청의 종류. ACP가 정한 kind 값과 같고, 화면에는 오른쪽 이름으로 보인다.
KIND_LABELS = {
    "execute": "명령 실행", "edit": "파일 쓰기", "delete": "파일 지우기", "move": "파일 옮기기",
    "read": "읽기", "search": "찾기", "fetch": "인터넷", "think": "생각", "other": "도구",
}


# 끝난 까닭. ACP의 stopReason을 플랫폼의 값으로 바꾼다.
ACP_STOPS = {"end_turn": "done", "max_tokens": "limit", "max_turn_requests": "limit",
             "refusal": "refusal", "cancelled": "cancelled"}
STOP_LABELS = {"done": "끝", "limit": "한도에 닿아 멈춤", "refusal": "엔진이 답하지 않기로 함", "cancelled": "멈춤"}
URL = re.compile(r"https?://[^\s'\"<>|;)]+")


class ToolRequest:
    """에이전트가 쓰려는 도구 하나. 엔진마다 다른 모양을 같은 꼴로 맞춘 것이다.

    engine:  요청을 보낸 엔진 이름
    kind:    종류(KIND_LABELS의 왼쪽 값). 예: "execute", "edit", "fetch"
    command: 실행할 명령(kind가 "execute"일 때만)
    path:    다룰 파일. 작업 폴더 안이면 작업 폴더 기준 경로(예: "outbox/a.json")
    url:     인터넷 주소. 웹 가져오기 도구의 주소이거나, 명령에 든 주소(예: curl https://...)
             어느 엔진, 어느 도구로 인터넷에 가든 여기에 주소가 있다
    title:   엔진이 붙인 제목. 엔진마다 다르다
    raw:     엔진이 보낸 원래 모양(dict)
    """

    def __init__(self, engine, kind, title="", command="", path="", url="", raw=None):
        self.engine, self.kind, self.title = engine, kind, title
        self.command, self.path, self.url = command, path, url
        self.raw = raw or {}

    @property
    def label(self):
        return KIND_LABELS.get(self.kind, "도구")

    @property
    def detail(self):
        """사람이 읽을 세부. 명령, 파일, 주소, 제목 순서로 있는 것을 쓴다."""
        return self.command or self.path or self.url or self.title

    def __repr__(self):
        return f"ToolRequest({self.engine}, {self.kind}, {self.detail!r})"


class TurnResult:
    """한 차례의 결과. 어느 엔진이 답했든 같은 꼴이다.

    stop:     끝난 까닭. "done", "limit", "refusal", "cancelled" 가운데 하나
    text:     답. 도구를 쓰기 전과 뒤의 말을 빈 줄로 이어 붙인다
    segments: 도구 사이사이의 말
    tools:    쓰기 시작한 도구(ToolRequest)
    refused:  거절한 도구(ToolRequest)
    notices:  플랫폼이 남긴 알림. 예: 거절 뒤 멈춘 엔진에게 이어서 하게 했다
    usage:    쓴 양 {"credits": 크레딧 또는 None, "contextTokens": 토큰 또는 None}
    """

    def __init__(self, engine, stop, segments, tools, refused, notices, usage):
        self.engine, self.stop = engine, stop
        self.segments = [s.strip() for s in segments if s.strip()]
        self.tools, self.refused, self.notices, self.usage = tools, refused, notices, usage

    @property
    def text(self):
        return "\n\n".join(self.segments)

    @property
    def stop_label(self):
        return STOP_LABELS.get(self.stop, self.stop)

    @property
    def usage_text(self):
        parts = []
        if self.usage.get("credits"):
            parts.append(f"크레딧 {self.usage['credits']:.3f}")
        if self.usage.get("contextTokens") is not None:
            parts.append(f"컨텍스트 {self.usage['contextTokens']:,}토큰")
        return ", ".join(parts) or "알 수 없음"


class AcpEngine:
    """ACP 엔진 하나와의 세션. 엔진마다 이 클래스를 이어받아 아래 값과 훅을 정한다."""

    # ---- 엔진마다 정하는 값 ----
    name = ""                  # 플랫폼이 부르는 이름
    command = []               # 엔진 프로그램을 ACP로 실행하는 명령
    home_env = ""              # 샌드박스 홈(.homes/<이름>/)을 가리키는 환경변수
    env = {}                   # 더 넣을 환경변수
    expect_mode = None         # 연결했을 때 이 모드여야 한다
    safe_mode = None           # 연결 직후 바꿀 모드. 묻지 않고 실행하지 않게 한다
    login = []                 # 로그인 명령
    logout = []                # 로그아웃 명령. 비면 화면에서 로그아웃하지 않는다
    status = []                # 로그인 상태를 보는 명령
    login_mode = "terminal"    # device(기기 코드), code(코드 붙여 넣기), terminal(터미널에서)

    def __init__(self, workspace, on_text=None, on_tool=None, on_permission=None, on_notice=None,
                 preamble=None, command=None, env=None):
        # workspace: 엔진이 일하는 폴더.
        # on_text(text): 답의 조각이 올 때마다 부른다.
        # on_tool(request): 엔진이 도구를 쓰기 시작할 때 ToolRequest로 부른다.
        # on_permission(request) -> bool: 허락이 필요할 때 ToolRequest로 부른다. 없으면 모두 거절한다.
        # on_notice(text): 플랫폼이 엔진의 다른 점을 맞추며 한 일을 알린다.
        # preamble: 첫 질문 앞에 붙여 보낼 플랫폼 안내. ACP에는 시스템 프롬프트 칸이 없다.
        # command, env: 테스트에서 실행 명령과 환경을 바꿀 때만 쓴다.
        self.workspace = os.path.abspath(workspace)
        self.on_text = on_text or (lambda text: None)
        self.on_tool = on_tool or (lambda request: None)
        self.on_permission = on_permission or (lambda request: False)
        self.on_notice = on_notice or (lambda text: None)
        self.preamble = preamble
        self.command_override = command
        self.env_override = env
        self.process = None
        self.session_id = None
        self.credits = 0.0
        self.context_tokens = None
        self._next_id = 0
        self._kinds = {}             # 도구 번호 → 시작 알림에서 본 kind
        self._turn = None            # 지금 차례의 기록: segments, tools, refused, notices

    # ---- 샌드박스(엔진마다 덮어쓰는 훅 포함) ----

    @classmethod
    def home(cls):
        return HOMES / cls.name

    @classmethod
    def prepare_home(cls, home):
        """샌드박스 홈에 엔진의 설정 파일을 쓴다. 엔진마다 덮어쓴다."""

    @classmethod
    def sandbox_env(cls):
        """샌드박스 홈을 가리키는 환경변수를 만든다. 홈과 설정 파일이 없으면 만든다."""
        home = cls.home()
        home.mkdir(parents=True, exist_ok=True)
        cls.prepare_home(home)
        env = dict(os.environ)
        env[cls.home_env] = str(home)
        env.update(cls.env)
        return env

    @classmethod
    def installed(cls):
        """실행하고 로그인하는 데 필요한 명령이 모두 있는지 본다."""
        commands = [cls.command[0]] + [c[0] for c in (cls.login, cls.status) if c]
        return all(shutil.which(c) for c in commands)

    @classmethod
    def logged_in(cls, returncode, output):
        """로그인 상태 명령의 결과를 읽는다. 엔진마다 덮어쓴다."""
        return returncode == 0

    @classmethod
    def check_login(cls):
        """샌드박스 홈의 로그인 상태. 알 수 없으면 None."""
        if not cls.status or shutil.which(cls.status[0]) is None:
            return None
        try:
            result = subprocess.run([shutil.which(cls.status[0]), *cls.status[1:]], env=cls.sandbox_env(),
                                    capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return cls.logged_in(result.returncode, result.stdout + result.stderr)

    # ---- 플랫폼 → 엔진: 보낼 때 바꾸는 훅 ----

    def session_meta(self):
        """session/new에 붙일 _meta. 엔진마다 덮어쓴다."""
        return None

    def choose_option(self, options, allow):
        """허락 요청의 선택지에서 고른다. 선택지 이름은 엔진마다 달라서 종류(kind)로 고른다."""
        wanted = "allow_once" if allow else "reject_once"
        return next((o["optionId"] for o in options if o.get("kind") == wanted), None)

    def refusal_followup(self, refused):
        """거절 뒤 차례를 멈춘 엔진에게 보낼 글. 다른 엔진처럼 이어서 하게 한다."""
        items = "; ".join(f"{r.label} {r.detail.splitlines()[0][:80] if r.detail else ''}".strip() for r in refused)
        return (f"[플랫폼 알림] 방금 요청한 도구는 허락되지 않았다: {items}. "
                "그 도구는 다시 요청하지 말고, 그 도구 없이 할 수 있는 만큼 이어서 한 뒤 하지 못한 것을 답에 적는다.")

    # ---- 엔진 → 플랫폼: 받을 때 바꾸는 훅 ----

    def command_text(self, value):
        """도구 요청에 든 명령을 글로 바꾼다. 엔진마다 덮어쓴다."""
        if isinstance(value, list):
            return " ".join(str(v) for v in value)
        return str(value or "")

    def tool_request(self, tool_call, known_kind=None):
        """엔진이 보낸 도구 요청(ACP의 toolCall)을 ToolRequest로 바꾼다.

        - kind가 비어 있으면 같은 도구의 시작 알림에서 본 kind(known_kind)를 쓴다(Kiro).
        - url이 있는데 kind가 "read"나 비어 있으면 "fetch"로 본다(Kiro의 웹 가져오기).
        - 명령은 kind가 "execute"일 때만 꺼낸다. Kiro의 파일 쓰기는 rawInput.command가 "create" 같은 하위 명령이다.
        """
        raw_input = tool_call.get("rawInput")
        raw_input = raw_input if isinstance(raw_input, dict) else {}
        kind = tool_call.get("kind") or known_kind or ""
        url = str(raw_input.get("url") or "")
        if url and kind in ("", "read", "other"):
            kind = "fetch"
        locations = tool_call.get("locations") or []
        path = str((locations[0] or {}).get("path", "") if locations else "") \
            or str(raw_input.get("file_path") or raw_input.get("path") or "")
        command_value = raw_input.get("command") or raw_input.get("cmd")
        if not kind:
            if command_value and not path:
                kind = "execute"
            elif path:
                kind = "edit" if any(k in raw_input for k in ("content", "new_string", "file_text")) else "read"
            else:
                kind = "other"
        command = self.command_text(command_value) if kind == "execute" else ""
        if command and not url:
            found = URL.search(command)
            url = found.group(0) if found else ""
        if path:
            try:
                path = pathlib.Path(path).resolve().relative_to(pathlib.Path(self.workspace).resolve()).as_posix()
            except ValueError:
                pass
        return ToolRequest(self.name, kind, title=str(tool_call.get("title") or ""),
                           command=command, path=path, url=url, raw=tool_call)

    def on_extension(self, method, params):
        """엔진만의 확장 알림(이름이 _로 시작). 엔진마다 덮어쓴다. 기본은 무시한다."""

    # ---- 흐름 ----

    def start(self):
        command = self.command_override or self.command
        executable = shutil.which(command[0])
        if executable is None:
            raise EngineError(f"{command[0]}를 찾지 못했습니다. README의 준비 절을 보세요.")
        env = self.env_override if self.env_override is not None else self.sandbox_env()
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
        # 1) 플랫폼이 무엇을 해 줄 수 있는지 알린다. 파일과 터미널은 엔진이 스스로 다룬다.
        self._request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False},
                "terminal": False,
            },
            "clientInfo": {"name": "acp-starter", "version": "0.4.0"},
        })
        # 2) 대화 하나를 연다.
        params = {"cwd": self.workspace, "mcpServers": []}
        meta = self.session_meta()
        if meta:
            params["_meta"] = meta
        result = self._request("session/new", params)
        self.session_id = result["sessionId"]
        current = result.get("modes", {}).get("currentModeId")
        if self.expect_mode and current != self.expect_mode:
            raise EngineError(f"엔진 설정 '{self.expect_mode}'를 찾지 못했습니다(지금: {current}).")
        # 3) 안전 모드로 바꾼다.
        if self.safe_mode:
            self._request("session/set_mode", {"sessionId": self.session_id, "modeId": self.safe_mode})

    def send(self, text):
        """질문 하나를 보내고, 이번 차례가 끝나면 결과를 TurnResult(하나의 형식)로 돌려준다."""
        if self.preamble:
            # 플랫폼 안내는 이 대화의 첫 질문에만 붙인다.
            text, self.preamble = f"{self.preamble}\n\n{text}", None
        self._turn = {"segments": [""], "tools": [], "refused": [], "notices": []}
        stop = self._prompt(text)
        if stop == "cancelled" and self._turn["refused"]:
            # 거절하면 차례 전체를 멈추는 엔진이 있다(Codex). 다른 엔진처럼 이어서 하게 한 번 더 보낸다.
            notice = "엔진이 거절 뒤 차례를 멈춰서, 플랫폼이 거절을 알리고 이어서 하게 했다."
            self._turn["notices"].append(notice)
            self.on_notice(notice)
            self._turn["segments"].append("")
            stop = self._prompt(self.refusal_followup(self._turn["refused"]))
        turn, self._turn = self._turn, None
        usage = {"credits": self.credits or None, "contextTokens": self.context_tokens}
        return TurnResult(self.name, stop, turn["segments"], turn["tools"], turn["refused"], turn["notices"], usage)

    def _prompt(self, text):
        result = self._request("session/prompt", {
            "sessionId": self.session_id,
            "prompt": [{"type": "text", "text": text}],
        })
        return ACP_STOPS.get(result.get("stopReason"), result.get("stopReason"))

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
                raise EngineError(f"{self.name} 엔진이 끝났습니다. 로그인 상태를 확인하세요(python login.py {self.name}).")
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
                    raise EngineError(f"{method} 실패: {detail}")
                return message["result"]

    def _handle(self, message):
        method = message["method"]
        params = message.get("params", {})

        # 엔진이 플랫폼에게 묻는 요청: 도구를 써도 되는가
        if method == "session/request_permission":
            tool_call = params.get("toolCall") or {}
            request = self.tool_request(tool_call, self._kinds.get(tool_call.get("toolCallId")))
            allowed = bool(self.on_permission(request))
            if not allowed and self._turn is not None:
                self._turn["refused"].append(request)
            option = self.choose_option(params.get("options", []), allowed)
            if option is None:
                outcome = {"outcome": "cancelled"}
            else:
                outcome = {"outcome": "selected", "optionId": option}
            self._send({"id": message["id"], "result": {"outcome": outcome}})
            return

        # 플랫폼이 모르는 요청에는 모른다고 답한다
        if "id" in message:
            self._send({"id": message["id"],
                        "error": {"code": -32601, "message": "Method not found"}})
            return

        # 엔진만의 확장 알림
        if method.startswith("_"):
            self.on_extension(method, params)
            return

        # 알림: 답의 조각, 도구 사용, 컨텍스트 사용량
        if method == "session/update":
            update = params.get("update", {})
            kind = update.get("sessionUpdate")
            if kind == "agent_message_chunk":
                content = update.get("content", {})
                if content.get("type") == "text":
                    if self._turn is not None:
                        self._turn["segments"][-1] += content["text"]
                    self.on_text(content["text"])
            elif kind in ("tool_call", "tool_call_update"):
                if update.get("kind"):
                    self._kinds[update.get("toolCallId")] = update["kind"]
                if kind == "tool_call":
                    request = self.tool_request(update)
                    if self._turn is not None:
                        self._turn["tools"].append(request)
                        self._turn["segments"].append("")   # 도구 앞뒤의 말은 따로 묶는다
                    self.on_tool(request)
            elif kind == "usage_update" and isinstance(update.get("used"), int):
                self.context_tokens = update["used"]
