"""내 에이전트 플랫폼의 대시보드. 브라우저로 여는 작은 웹 서버다.

실행: python dashboard.py      → http://127.0.0.1:8765 이 열린다
      python dashboard.py --no-browser   (브라우저를 열지 않는다)

서버는 JSON API만 낸다. 화면(app/static/)은 그 API를 부르는 클라이언트다.
하는 일: 엔진 목록과 로그인, 엔진 연결(한 번에 하나), 대화 하나, 허락 카드.
custom/의 파일(이름과 색, 업무, 허락 규칙)은 custom_loader.py가 읽어 잇는다.
대화 기록은 conversations.py가 conversations/에 파일로 남긴다.
"""

import datetime
import json
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import custom_loader
import engines
from conversations import ConversationError, ConversationStore
from engines import EngineError

ROOT = pathlib.Path(__file__).parent
STATIC = ROOT / "app" / "static"
STATIC_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}
HOST, PORT = "127.0.0.1", 8765
PERMISSION_WAIT_SECONDS = 300
LOGIN_WAIT_SECONDS = 900
SAFE_NAME = re.compile(r"[\w.\-]+")
# 로그인 명령의 출력에서 색과 링크 표시(ANSI 이스케이프)를 지우고 주소와 기기 코드를 찾는다.
ANSI = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-z]")
URL = re.compile(r"https://[^\s\x07\x1b]+")
DEVICE_CODE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4,5}\b")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def check_login(name):
    """엔진의 샌드박스 로그인 상태. 알 수 없으면 None."""
    return engines.get(name).check_login()


def tool_line(request):
    """대화 기록에 남길 도구 한 줄. 예: "명령 실행 ls"."""
    first = request.detail.splitlines()[0][:200] if request.detail else ""
    return f"{request.label} {first}".strip()


class EventLog:
    """화면이 가져가는 사건 기록. 화면은 마지막으로 받은 번호 뒤의 사건만 묻는다.

    epoch는 서버를 켤 때마다 바뀐다. 화면은 epoch가 바뀌면 처음부터 다시 읽는다.
    """

    def __init__(self):
        self.events = []
        self.cond = threading.Condition()
        self.epoch = secrets.token_hex(4)

    def add(self, **event):
        with self.cond:
            event["seq"] = len(self.events) + 1
            event["at"] = datetime.datetime.now().strftime("%H:%M:%S")
            self.events.append(event)
            self.cond.notify_all()
            return event

    def since(self, after, timeout=15):
        """그 번호 뒤의 사건. 새 사건이 없으면 기다린다. 서버를 다시 켜서 번호가 앞서 있으면 바로 돌려준다."""
        with self.cond:
            if len(self.events) == after:
                self.cond.wait(timeout)
            return self.events[after:]


class Logins:
    """화면에서 시작한 로그인. 로그인 명령을 실행하고 출력에서 주소와 코드를 꺼내 사건으로 알린다.

    login_mode: "device"는 주소와 기기 코드를 보여 준다(Codex).
                "code"는 주소를 보여 주고, 사람이 받은 코드를 표준 입력으로 넘긴다(Claude).
                "terminal"은 화면에서 하지 않고 터미널 명령을 알려 준다(Kiro. 로그인이 컴퓨터 전체에 걸린다).
    """

    def __init__(self, log, load_engine=engines.get, env_for=lambda name, engine: engine.sandbox_env(),
                 is_logged_in=check_login):
        self.log = log
        self.load_engine = load_engine
        self.env_for = env_for
        self.is_logged_in = is_logged_in
        self.lock = threading.Lock()
        self.running = {}            # 엔진 이름 → 로그인 프로세스
        self.stopped = {}            # 엔진 이름 → 플랫폼이 멈춘 까닭("cancelled", "timeout")

    def _engine(self, name):
        try:
            return self.load_engine(name)
        except EngineError as error:
            raise ApiError(400, str(error))

    def start(self, name):
        engine = self._engine(name)
        mode = engine.login_mode
        if mode == "terminal":
            raise ApiError(400, f"{name}은 터미널에서 로그인합니다: {' '.join(engine.login)}")
        executable = shutil.which(engine.login[0])
        if executable is None:
            raise ApiError(400, f"{engine.login[0]}를 찾지 못했습니다. README의 준비 절을 보세요.")
        # 로그인 명령은 시작하자마자 있던 로그인을 지울 수 있다(codex). 그래서 로그인된 상태에서는 시작하지 않는다.
        if self.is_logged_in(name) is True:
            raise ApiError(409, f"{name}은 이미 로그인되어 있습니다. 다른 계정으로 바꾸려면 먼저 로그아웃합니다.")
        with self.lock:
            old = self.running.get(name)
            if old and old.poll() is None:
                raise ApiError(409, "이미 로그인을 진행하는 중입니다.")
            process = subprocess.Popen([executable, *engine.login[1:]], env=self.env_for(name, engine),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                       errors="replace", bufsize=1)
            self.running[name] = process
        self.log.add(type="login", engine=name, state="started", mode=mode)
        threading.Thread(target=self._watch, args=(name, process, mode), daemon=True).start()

    def _stop(self, name, process, reason):
        """로그인 프로세스를 멈춘다. 끝난 까닭은 종료 코드가 아니라 이 표시로 판단한다.

        강제로 끝낸 프로세스의 종료 코드는 운영체제마다 다르다(macOS·Linux는 음수, Windows는 1).
        """
        self.stopped[name] = reason
        process.kill()

    def _watch(self, name, process, mode):
        timer = threading.Timer(LOGIN_WAIT_SECONDS, self._stop, args=(name, process, "timeout"))
        timer.start()
        url, code, tail = None, None, []
        for line in process.stdout:
            clean = ANSI.sub("", line).strip()
            if not clean:
                continue
            tail = (tail + [clean])[-5:]
            found_url = URL.search(clean)
            found_code = DEVICE_CODE.search(URL.sub("", clean))
            if (found_url and not url) or (found_code and not code):
                url = url or (found_url and found_url.group(0))
                code = code or (found_code and found_code.group(0))
                self.log.add(type="login", engine=name, state="waiting", mode=mode, url=url, userCode=code)
        process.wait()
        timer.cancel()
        for stream in (process.stdin, process.stdout):
            try:
                stream.close()
            except (OSError, ValueError):
                pass
        reason = self.stopped.pop(name, None)
        if process.returncode == 0:
            self.log.add(type="login", engine=name, state="done", mode=mode)
        elif reason == "cancelled" or (reason is None and process.returncode < 0):
            self.log.add(type="login", engine=name, state="cancelled", mode=mode)
        else:
            message = f"{LOGIN_WAIT_SECONDS // 60}분 안에 끝나지 않아 멈췄다." if reason == "timeout" else " / ".join(tail)
            self.log.add(type="login", engine=name, state="failed", mode=mode, message=message)

    def code(self, name, code):
        with self.lock:
            process = self.running.get(name)
        if process is None or process.poll() is not None:
            raise ApiError(404, "진행 중인 로그인이 없습니다.")
        if not code.strip():
            raise ApiError(400, "코드가 비어 있습니다.")
        try:
            process.stdin.write(code.strip() + "\n")
            process.stdin.flush()
        except (OSError, ValueError):
            raise ApiError(404, "진행 중인 로그인이 없습니다.")
        self.log.add(type="login", engine=name, state="checking")

    def cancel(self, name):
        with self.lock:
            process = self.running.get(name)
        if process is None or process.poll() is not None:
            raise ApiError(404, "진행 중인 로그인이 없습니다.")
        self._stop(name, process, "cancelled")

    def logout(self, name):
        engine = self._engine(name)
        command = engine.logout
        if not command:
            raise ApiError(400, f"{name}은 화면에서 로그아웃하지 않습니다. 로그인이 컴퓨터 전체에 걸려 있기 때문입니다.")
        executable = shutil.which(command[0])
        if executable is None:
            raise ApiError(400, f"{command[0]}를 찾지 못했습니다.")
        result = subprocess.run([executable, *command[1:]], env=self.env_for(name, engine),
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        self.log.add(type="login", engine=name, state="logged_out" if result.returncode == 0 else "failed",
                     message=ANSI.sub("", result.stdout + result.stderr).strip()[-300:])


class Platform:
    """엔진 연결, 대화 하나, 허락 카드, 로그인을 맡는다.

    이 클래스는 엔진 이름을 몰라도 된다. 엔진마다 다른 것은 engines/가 맡는다.
    대화는 하나다(conversations.py의 가장 새 대화). 엔진을 바꾸면 플랫폼이 앞의 대화를 새 엔진에 넘긴다.
    """

    def __init__(self, root=ROOT, client_factory=engines.make, status_checker=check_login,
                 install_checker=lambda engine: engine.installed(), logins=None):
        self.workspace = pathlib.Path(root) / "workspace"
        self.custom = pathlib.Path(root) / "custom"
        self.store = ConversationStore(pathlib.Path(root) / "conversations")
        self.client_factory = client_factory
        self.status_checker = status_checker
        self.install_checker = install_checker
        self.log = EventLog()
        self.logins = logins or Logins(self.log)
        self.lock = threading.Lock()
        # 엔진 세션은 한 번에 하나만 열어 둔다. 아래는 그 세션의 것이다.
        self.client = None
        self.engine = None           # 열어 둔 세션의 엔진
        self.state = "idle"          # idle, starting, ready, busy, error
        self.partial = []            # 지금 차례에 받은 답 조각. 엔진이 중간에 끝나도 남기려고 모은다
        self.pending = {}            # 허락을 기다리는 요청: 번호 → {event, allow}
        self.next_permission = 0

    # ---- 엔진 ----

    def engines(self):
        configs = {name: engines.get(name) for name in engines.names()}
        results = {}

        def check(name):
            results[name] = self.status_checker(name) if self.install_checker(configs[name]) else None

        threads = [threading.Thread(target=check, args=(name,)) for name in configs]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return {"engines": [{"name": name,
                             "installed": self.install_checker(config),
                             "loggedIn": results.get(name),
                             "loginMode": config.login_mode,
                             "loginCommand": " ".join(config.login),
                             "canLogout": bool(config.logout)} for name, config in configs.items()]}

    def _known_engine(self, name):
        try:
            engines.get(name)
        except EngineError as error:
            raise ApiError(400, str(error))
        return name

    def _busy(self):
        """답을 쓰거나 연결하는 중인지 본다. self.lock 안에서 부른다."""
        return self.state in ("starting", "busy")

    def _detach(self):
        """열어 둔 엔진 세션을 떼어 낸다. self.lock 안에서 부르고, 돌려받은 세션은 lock 밖에서 닫는다."""
        old, self.client = self.client, None
        self.engine, self.state = None, "idle"
        return old

    # ---- 대화 ----

    def conversation(self):
        """지금 대화. 하나도 없으면 첫 엔진으로 새로 만든다."""
        try:
            return self.store.current(engines.names()[0])
        except ConversationError as error:
            raise ApiError(error.status, str(error))

    def new_conversation(self):
        """새 대화를 시작한다. 앞의 대화 파일은 지우지 않고 남긴다.

        엔진 세션도 닫는다. 엔진의 기억에 앞의 대화가 남아 있기 때문이다. 엔진은 앞의 대화와 같은 것을 쓴다.
        """
        current = self.conversation()
        with self.lock:
            if self._busy():
                raise ApiError(409, "답을 쓰는 중입니다. 끝난 뒤에 새 대화를 시작합니다.")
            old = self._detach()
        if old:
            old.close()
        fresh = current if not current["messages"] else self.store.create(current["engine"])
        self.log.add(type="conversation", id=fresh["id"])
        self._status()
        return fresh

    def connect(self, engine):
        """엔진 세션을 연다. 대화의 엔진과 다르면 대화의 엔진을 바꾸고, 앞의 대화를 플랫폼 안내에 넣어 넘긴다."""
        engine = self._known_engine(str(engine or ""))
        conversation = self.conversation()
        with self.lock:
            if self._busy():
                raise ApiError(409, "답을 쓰거나 연결하는 중입니다. 끝난 뒤에 연결합니다.")
            old = self._detach()
            self.engine, self.state = engine, "starting"
        if old:
            old.close()
        if engine != conversation["engine"]:
            note = (f"엔진을 {conversation['engine']}에서 {engine}로 바꿨다. "
                    "지금까지의 대화를 플랫폼 안내에 넣어 이어 간다.")
            try:
                conversation = self.store.change_engine(conversation["id"], engine, note)
            except (ConversationError, OSError) as error:
                self.log.add(type="record_error", message=f"대화 기록을 저장하지 못했다: {error}")
            self.log.add(type="note", text=note)
        self._status()
        threading.Thread(target=self._connect, args=(conversation, engine), daemon=True).start()

    def _connect(self, conversation, engine):
        try:
            self._open(conversation["id"], engine, conversation["messages"])
        except Exception as error:  # 엔진 오류든 코드의 버그든 기록하고, 다시 연결할 수 있게 한다
            return self._fail(conversation["id"], error)
        with self.lock:
            self.state = "ready"
        self._status()

    def prompt(self, text):
        """지금 대화에 질문을 보낸다. 답은 사건으로 오고, 끝나면 대화 기록에 남는다.

        연결한 세션이 없으면 대화의 엔진으로 세션을 새로 연다.
        """
        text = str(text or "").strip()
        if not text:
            raise ApiError(400, "보낼 내용이 없습니다.")
        conversation = self.conversation()
        engine = self._known_engine(conversation["engine"])
        with self.lock:
            if self._busy():
                raise ApiError(409, "답을 쓰거나 연결하는 중입니다. 끝난 뒤에 보냅니다.")
            reuse = self.client is not None and self.state == "ready" and self.engine == engine
            old = None if reuse else self._detach()
            self.engine, self.state, self.partial = engine, "busy" if reuse else "starting", []
        if old:
            old.close()
        history = conversation["messages"]
        self._record(conversation["id"], {"role": "user", "text": text})
        self.log.add(type="user", text=text)
        self._status()
        threading.Thread(target=self._turn, daemon=True,
                         args=(conversation["id"], engine, history, text, reuse)).start()

    def _turn(self, conversation_id, engine, history, text, reuse):
        """질문 하나를 엔진에 보낸다. 엔진이 어떤 꼴로 답하든 하나의 형식(TurnResult)으로 받아 기록과 화면에 쓴다."""
        try:
            client = self.client if reuse else self._open(conversation_id, engine, history)
            if not reuse:
                with self.lock:
                    self.state = "busy"
                self._status()
            result = client.send(text)
        except Exception as error:  # 엔진 오류든 코드의 버그든 기록하고, 다음 질문을 받을 수 있게 한다
            partial = "".join(self.partial).strip()
            if partial:
                self._record(conversation_id, {"role": "agent", "text": partial, "engine": engine,
                                               "stop": "error", "stopLabel": "오류로 멈춤"})
            return self._fail(conversation_id, error)
        self._record(conversation_id, {
            "role": "agent", "text": result.text, "engine": engine, "stop": result.stop,
            "stopLabel": result.stop_label, "usage": result.usage_text,
            "tools": [tool_line(t) for t in result.tools], "refused": [tool_line(t) for t in result.refused],
            "notices": result.notices})
        with self.lock:
            self.state = "ready"
        self.log.add(type="done", stop=result.stop, stopLabel=result.stop_label, usage=result.usage_text,
                     refused=len(result.refused))
        self._status()

    def _open(self, conversation_id, engine, history):
        """엔진 세션을 새로 연다. 첫 질문에 붙일 플랫폼 안내에 앞의 대화(history)를 넣는다."""
        preamble = custom_loader.preamble(self.custom, history)
        client = self.client_factory(engine, self.workspace, on_text=self._on_text, on_tool=self._on_tool,
                                     on_permission=self._ask, on_notice=self._on_notice, preamble=preamble)
        try:
            client.start()
        except Exception:
            client.close()
            raise
        with self.lock:
            self.client = client
        carried = len(custom_loader.history_lines(history))
        self._record(conversation_id, {"role": "preamble", "text": preamble, "engine": engine, "history": carried})
        self.log.add(type="preamble", engine=engine, text=preamble, history=carried)
        return client

    def _fail(self, conversation_id, error):
        self._record(conversation_id, {"role": "note", "text": f"오류: {error}", "error": True})
        with self.lock:
            self.state = "error"
        self._status(message=str(error))

    def _record(self, conversation_id, message):
        """대화 기록에 메시지를 더한다. 대화 파일이 없어졌거나 쓰지 못하면 기록을 건너뛰고 계속한다."""
        try:
            self.store.append(conversation_id, message)
        except (ConversationError, OSError) as error:
            self.log.add(type="record_error", message=f"대화 기록을 저장하지 못했다: {error}")

    def _status(self, **fields):
        with self.lock:
            state, engine = self.state, self.engine
        self.log.add(type="status", state=state, engine=engine, **fields)

    def snapshot(self):
        """지금 엔진 세션, 대화, 진행 중인 차례의 사건. 화면이 처음 열릴 때 부른다."""
        with self.lock:
            state, engine = self.state, self.engine
        with self.log.cond:
            events = list(self.log.events)
        live = []
        if state in ("starting", "busy"):
            asked = [i for i, e in enumerate(events) if e["type"] == "user"]
            if asked:
                live = events[asked[-1] + 1:]
        return {"state": state, "engine": engine, "conversation": self.conversation(),
                "live": live, "last": len(events), "epoch": self.log.epoch}

    def _on_text(self, text):
        self.partial.append(text)
        self.log.add(type="text", text=text)

    def _on_notice(self, text):
        self.log.add(type="notice", text=text)

    def _on_tool(self, request):
        self.log.add(type="tool", kind=request.kind, label=request.label, detail=request.detail)

    # ---- 허락 ----

    def _ask(self, request):
        """에이전트가 허락을 물으면 먼저 custom/rules.py에 묻고, "ask"이면 카드를 띄워 사람의 답을 기다린다."""
        decision, error = custom_loader.decide(request, self.custom)
        if error:
            self.log.add(type="rule_error", message=error)
        if decision != "ask":
            self.log.add(type="rule", kind=request.kind, label=request.label, detail=request.detail,
                         allow=decision == "allow")
            return decision == "allow"
        with self.lock:
            self.next_permission += 1
            number = self.next_permission
            waiter = {"event": threading.Event(), "allow": False}
            self.pending[number] = waiter
        self.log.add(type="permission", id=number, kind=request.kind, label=request.label,
                     detail=request.detail, title=request.title)
        answered = waiter["event"].wait(PERMISSION_WAIT_SECONDS)
        with self.lock:
            self.pending.pop(number, None)
        allow = waiter["allow"] if answered else False
        self.log.add(type="permission_result", id=number, allow=allow, timeout=not answered)
        return allow

    def answer(self, number, allow):
        with self.lock:
            waiter = self.pending.get(number)
        if waiter is None:
            raise ApiError(404, "기다리는 허락 요청이 없습니다.")
        waiter["allow"] = bool(allow)
        waiter["event"].set()


def make_handler(platform):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                raise ApiError(400, "JSON이 아닙니다.")
            if not isinstance(body, dict):
                raise ApiError(400, "JSON 객체를 보냅니다.")
            return body

        def send_file(self, path):
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", STATIC_TYPES.get(path.suffix, "text/plain") + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def parts(self):
            return [unquote(p) for p in urlparse(self.path).path.split("/") if p]

        def do_GET(self):
            parts = self.parts()
            try:
                if not parts:
                    return self.send_file(STATIC / "index.html")
                if len(parts) == 2 and parts[0] == "static" and SAFE_NAME.fullmatch(parts[1]) \
                        and (STATIC / parts[1]).is_file():
                    return self.send_file(STATIC / parts[1])
                if parts == ["api", "engines"]:
                    return self.send_json(200, platform.engines())
                if parts == ["api", "brand"]:
                    return self.send_json(200, custom_loader.brand(platform.custom))
                if parts == ["api", "state"]:
                    return self.send_json(200, platform.snapshot())
                if parts == ["api", "conversation"]:
                    return self.send_json(200, platform.conversation())
                if parts == ["api", "events"]:
                    query = parse_qs(urlparse(self.path).query)
                    after = int(query.get("after", ["0"])[0] or 0)
                    events = platform.log.since(after)
                    last = events[-1]["seq"] if events else after
                    return self.send_json(200, {"events": events, "last": last, "epoch": platform.log.epoch,
                                                "state": platform.state, "engine": platform.engine})
                raise ApiError(404, "없는 주소입니다.")
            except ValueError:
                self.send_json(400, {"error": "after는 숫자입니다."})
            except ApiError as error:
                self.send_json(error.status, {"error": str(error)})

        def do_POST(self):
            parts = self.parts()
            try:
                body = self.read_json()
                if parts == ["api", "conversation", "new"]:
                    return self.send_json(201, platform.new_conversation())
                if parts == ["api", "connect"]:
                    platform.connect(body.get("engine"))
                    return self.send_json(202, {"ok": True})
                if parts == ["api", "prompt"]:
                    platform.prompt(body.get("text"))
                    return self.send_json(202, {"ok": True})
                if len(parts) == 3 and parts[:2] == ["api", "permissions"] and parts[2].isdigit():
                    platform.answer(int(parts[2]), body.get("allow") is True)
                    return self.send_json(200, {"ok": True})
                if len(parts) == 3 and parts[:2] == ["api", "login"]:
                    platform.logins.start(parts[2])
                    return self.send_json(202, {"ok": True})
                if len(parts) == 4 and parts[:2] == ["api", "login"] and parts[3] == "code":
                    platform.logins.code(parts[2], str(body.get("code", "")))
                    return self.send_json(202, {"ok": True})
                if len(parts) == 3 and parts[:2] == ["api", "logout"]:
                    platform.logins.logout(parts[2])
                    return self.send_json(200, {"ok": True})
                raise ApiError(404, "없는 주소입니다.")
            except ApiError as error:
                self.send_json(error.status, {"error": str(error)})

        def do_DELETE(self):
            parts = self.parts()
            try:
                if len(parts) == 3 and parts[:2] == ["api", "login"]:
                    platform.logins.cancel(parts[2])
                    return self.send_json(200, {"ok": True})
                raise ApiError(404, "없는 주소입니다.")
            except ApiError as error:
                self.send_json(error.status, {"error": str(error)})

    return Handler


def serve(platform, host=HOST, port=PORT):
    return ThreadingHTTPServer((host, port), make_handler(platform))


def main():
    custom_loader.load_env()
    platform = Platform()
    server = serve(platform)
    url = f"http://{HOST}:{PORT}"
    print(f"대시보드: {url}  (끝내려면 Ctrl+C)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if platform.client:
            platform.client.close()


if __name__ == "__main__":
    main()
