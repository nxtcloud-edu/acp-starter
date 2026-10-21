"""내 에이전트 플랫폼의 대시보드. 브라우저로 여는 작은 웹 서버다.

실행: python dashboard.py      → http://127.0.0.1:8765 이 열린다
      python dashboard.py --no-browser   (브라우저를 열지 않는다)

서버는 JSON API만 낸다. 화면(app/static/)은 그 API를 부르는 클라이언트다.
API의 목록은 README의 '대시보드 API' 절에 있다.
대시보드가 켜져 있는 동안 tasks/의 일을 정해진 시각에 돌린다.
custom/의 파일(이름과 색, 업무, 허락 규칙, 결과 보내기)은 custom_loader.py가 읽어 잇는다.
"""

import datetime
import json
import pathlib
import re
import shutil
import sys
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import acp_client
import custom_loader
import runner
from acp_client import AcpClient, AcpError

ROOT = pathlib.Path(__file__).parent
STATIC = ROOT / "app" / "static"
HOST, PORT = "127.0.0.1", 8765
PERMISSION_WAIT_SECONDS = 300
SCHEDULER_SECONDS = 20
LOGIN_WAIT_SECONDS = 900
SAFE_NAME = re.compile(r"[\w가-힣.\-]+")
OUTBOX_TYPES = {".md": "text/markdown", ".json": "application/json", ".html": "text/html",
                ".txt": "text/plain", ".csv": "text/csv"}
# 로그인 명령의 출력에서 색과 링크 표시(ANSI 이스케이프)를 지우고 주소와 기기 코드를 찾는다.
ANSI = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-z]")
URL = re.compile(r"https://[^\s\x07\x1b]+")
DEVICE_CODE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4,5}\b")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def installed(engine):
    """엔진을 실행하고 로그인하는 데 필요한 명령이 모두 있는지 본다."""
    commands = [engine["command"][0]] + [engine[k][0] for k in ("login", "status") if engine.get(k)]
    return all(shutil.which(command) for command in commands)


def check_login(name):
    """샌드박스 홈의 로그인 상태를 본다. 알 수 없으면 None."""
    engine = acp_client.load_engine(name)
    command = engine.get("status")
    if not command or shutil.which(command[0]) is None:
        return None
    try:
        result = subprocess.run([shutil.which(command[0]), *command[1:]],
                                env=acp_client.sandbox_env(name, engine),
                                capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = result.stdout + result.stderr
    return result.returncode == 0 and '"loggedIn": false' not in output and "Not logged in" not in output


class EventLog:
    """화면이 가져가는 사건 기록. 화면은 마지막으로 받은 번호 뒤의 사건만 묻는다."""

    def __init__(self):
        self.events = []
        self.cond = threading.Condition()

    def add(self, **event):
        with self.cond:
            event["seq"] = len(self.events) + 1
            event["at"] = datetime.datetime.now().strftime("%H:%M:%S")
            self.events.append(event)
            self.cond.notify_all()

    def since(self, after, timeout=15):
        with self.cond:
            if len(self.events) <= after:
                self.cond.wait(timeout)
            return self.events[after:]


class Logins:
    """화면에서 시작한 로그인. 로그인 명령을 실행하고 출력에서 주소와 코드를 꺼내 사건으로 알린다.

    login_mode: "device"는 주소와 기기 코드를 보여 준다(Codex).
                "code"는 주소를 보여 주고, 사람이 받은 코드를 표준 입력으로 넘긴다(Claude).
                "terminal"은 화면에서 하지 않고 터미널 명령을 알려 준다(Kiro. 로그인이 컴퓨터 전체에 걸린다).
    """

    def __init__(self, log, load_engine=acp_client.load_engine, env_for=acp_client.sandbox_env,
                 is_logged_in=check_login):
        self.log = log
        self.load_engine = load_engine
        self.env_for = env_for
        self.is_logged_in = is_logged_in
        self.lock = threading.Lock()
        self.running = {}            # 에이전트 이름 → 로그인 프로세스

    def _engine(self, name):
        try:
            return self.load_engine(name)
        except AcpError as error:
            raise ApiError(400, str(error))

    def start(self, name):
        engine = self._engine(name)
        mode = engine.get("login_mode", "terminal")
        if mode == "terminal":
            raise ApiError(400, f"{name}은 터미널에서 로그인합니다: {' '.join(engine['login'])}")
        executable = shutil.which(engine["login"][0])
        if executable is None:
            raise ApiError(400, f"{engine['login'][0]}를 찾지 못했습니다. README의 준비 절을 보세요.")
        # 로그인 명령은 시작하자마자 있던 로그인을 지울 수 있다(codex). 그래서 로그인된 상태에서는 시작하지 않는다.
        if self.is_logged_in(name) is True:
            raise ApiError(409, f"{name}은 이미 로그인되어 있습니다. 다른 계정으로 바꾸려면 먼저 로그아웃합니다.")
        with self.lock:
            old = self.running.get(name)
            if old and old.poll() is None:
                raise ApiError(409, "이미 로그인을 진행하는 중입니다.")
            process = subprocess.Popen([executable, *engine["login"][1:]], env=self.env_for(name, engine),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                       errors="replace", bufsize=1)
            self.running[name] = process
        self.log.add(type="login", engine=name, state="started", mode=mode)
        threading.Thread(target=self._watch, args=(name, process, mode), daemon=True).start()

    def _watch(self, name, process, mode):
        timer = threading.Timer(LOGIN_WAIT_SECONDS, process.kill)
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
        if process.returncode == 0:
            self.log.add(type="login", engine=name, state="done", mode=mode)
        elif process.returncode < 0:
            self.log.add(type="login", engine=name, state="cancelled", mode=mode)
        else:
            self.log.add(type="login", engine=name, state="failed", mode=mode, message=" / ".join(tail))

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
        process.kill()

    def logout(self, name):
        engine = self._engine(name)
        command = engine.get("logout")
        if not command:
            raise ApiError(400, f"{name}은 화면에서 로그아웃하지 않습니다. 로그인이 컴퓨터 전체에 걸려 있기 때문입니다.")
        executable = shutil.which(command[0])
        if executable is None:
            raise ApiError(400, f"{command[0]}를 찾지 못했습니다.")
        result = subprocess.run([executable, *command[1:]], env=self.env_for(name, engine),
                                capture_output=True, text=True, timeout=30)
        self.log.add(type="login", engine=name, state="logged_out" if result.returncode == 0 else "failed",
                     message=ANSI.sub("", result.stdout + result.stderr).strip()[-300:])


class Platform:
    """에이전트, 대화 하나, 일 목록, 스케줄, 결과함, 로그인을 맡는다.

    에이전트(custom/agents/)는 플랫폼이 정하고, 엔진(engines.json)은 그 에이전트를 돌리는 부품이다.
    이 클래스는 엔진 이름을 몰라도 된다. 엔진마다 다른 것은 acp_client.py가 맡는다.
    """

    def __init__(self, root=ROOT, client_factory=AcpClient, status_checker=check_login,
                 install_checker=installed, logins=None):
        self.workspace = pathlib.Path(root) / "workspace"
        self.tasks_dir = pathlib.Path(root) / "tasks"
        self.custom = pathlib.Path(root) / "custom"
        self.client_factory = client_factory
        self.status_checker = status_checker
        self.install_checker = install_checker
        self.log = EventLog()
        self.logins = logins or Logins(self.log)
        self.lock = threading.Lock()
        self.client = None
        self.agent = None            # 연결한 에이전트의 이름
        self.engine = None           # 그 에이전트를 돌리는 엔진
        self.state = "idle"          # idle, starting, ready, busy, error
        self.pending = {}            # 허락을 기다리는 요청: 번호 → {event, allow}
        self.history = {}            # 에이전트 이름 → 앞의 대화 [{role, text}]. 대시보드를 끄면 사라진다
        self.turn = []               # 지금 차례의 답 조각
        self.next_permission = 0
        self.last_run = {}           # 스케줄 판단용: 일 이름 → 오늘 돌렸거나 건너뛴 날짜
        self.ran_at = {}             # 화면 표시용: 일 이름 → 실제로 돌린 시각
        # 켜기 전에 이미 지난 오늘의 일은 돌리지 않는다. 놓친 실행을 몰아서 하지 않는다.
        now = datetime.datetime.now()
        for task in runner.load_tasks(self.tasks_dir):
            if task["time"] and now.strftime("%H:%M") >= task["time"]:
                self.last_run[task["name"]] = now.date()

    # ---- 엔진 ----

    def engines(self):
        configs = json.loads(acp_client.ENGINES_FILE.read_text(encoding="utf-8"))
        names = list(configs)
        results = {}

        def check(name):
            results[name] = self.status_checker(name) if self.install_checker(configs[name]) else None

        threads = [threading.Thread(target=check, args=(name,)) for name in names]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return {"engines": [{"name": name,
                             "installed": self.install_checker(configs[name]),
                             "loggedIn": results.get(name),
                             "loginMode": configs[name].get("login_mode", "terminal"),
                             "loginCommand": " ".join(configs[name].get("login", [])),
                             "canLogout": bool(configs[name].get("logout"))} for name in names]}

    # ---- 에이전트 ----

    def agents(self):
        items = custom_loader.agents(self.custom)
        for item in items:
            item["history"] = len(self.history.get(item["name"], []))
        return {"agents": items, "current": self.agent, "engine": self.engine, "state": self.state}

    def save_agent(self, body, create):
        try:
            return custom_loader.save_agent(body, self.custom, self.workspace, create=create)
        except custom_loader.AgentError as error:
            raise ApiError(error.status, str(error))

    # ---- 대화 ----

    def connect(self, agent, engine=None, fresh=False):
        """에이전트에 연결한다. engine을 주면 에이전트 파일의 engine 대신 그 엔진으로 돌린다.

        플랫폼이 가진 그 에이전트의 앞의 대화를 새 세션에 다시 보낸다. fresh=True이면 지우고 새로 시작한다.
        """
        try:
            definition = custom_loader.agent(agent, self.custom)
            engine = engine or definition["engine"]
            acp_client.load_engine(engine)
        except custom_loader.AgentError as error:
            raise ApiError(error.status, str(error))
        except AcpError as error:
            raise ApiError(400, str(error))
        with self.lock:
            if self.state in ("starting", "busy"):
                raise ApiError(409, "앞의 일이 끝난 뒤에 바꿀 수 있습니다.")
            old, self.client = self.client, None
            self.agent, self.engine, self.state = agent, engine, "starting"
            if fresh:
                self.history.pop(agent, None)
            history = list(self.history.get(agent, []))
        if old:
            old.close()
        self.log.add(type="status", state="starting", agent=agent, engine=engine)
        threading.Thread(target=self._start, args=(definition, engine, history), daemon=True).start()

    def _start(self, definition, engine, history):
        agent = definition["name"]
        preamble = custom_loader.preamble(self.workspace, self.custom, definition, history)
        client = None
        try:
            client = self.client_factory(self.workspace, engine, on_text=self._on_text, on_tool=self._on_tool,
                                         on_permission=self._ask, preamble=preamble)
            client.start()
        except AcpError as error:
            if client is not None:
                client.close()
            with self.lock:
                self.state = "error"
            self.log.add(type="status", state="error", agent=agent, engine=engine, message=str(error))
            return
        with self.lock:
            if (self.agent, self.engine) != (agent, engine):
                client.close()
                return
            self.client, self.state = client, "ready"
        self.log.add(type="status", state="ready", agent=agent, engine=engine)
        self.log.add(type="preamble", agent=agent, engine=engine, text=preamble, history=len(history))

    def send(self, text):
        if not text.strip():
            raise ApiError(400, "보낼 내용이 없습니다.")
        with self.lock:
            if self.state != "ready":
                raise ApiError(409, "에이전트가 준비되지 않았거나 앞의 답을 쓰는 중입니다.")
            self.state, client = "busy", self.client
            self.history.setdefault(self.agent, []).append({"role": "user", "text": text})
            self.turn = []
        self.log.add(type="user", text=text)
        threading.Thread(target=self._prompt, args=(client, text), daemon=True).start()

    def _prompt(self, client, text):
        agent = self.agent
        try:
            stop_reason = client.prompt(text)
            self.log.add(type="done", stopReason=stop_reason, usage=client.usage_text())
            state = "ready"
        except AcpError as error:
            self.log.add(type="status", state="error", agent=self.agent, engine=self.engine, message=str(error))
            state = "error"
        with self.lock:
            answer = "".join(self.turn).strip()
            if answer:
                self.history.setdefault(agent, []).append({"role": "agent", "text": answer})
            self.turn = []
            if self.client is client:
                self.state = state

    def _on_text(self, text):
        self.turn.append(text)
        self.log.add(type="text", text=text)

    def _on_tool(self, request):
        self.log.add(type="tool", kind=request.kind, label=request.label, detail=request.detail)

    def _ask(self, request):
        """에이전트가 허락을 물으면 먼저 custom/rules.py에 묻고, "ask"이면 카드를 띄워 사람의 답을 기다린다."""
        decision, error = custom_loader.decide(self.agent, request, self.custom)
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

    # ---- 일과 스케줄 ----

    def tasks(self):
        items = runner.load_tasks(self.tasks_dir)
        for task in items:
            task["lastRun"] = self.ran_at.get(task["name"])
        return {"tasks": items}

    def run_task(self, name):
        task = next((t for t in runner.load_tasks(self.tasks_dir) if t["name"] == name), None)
        if task is None:
            raise ApiError(404, f"일 '{name}'이 없습니다.")
        now = datetime.datetime.now()
        self.last_run[name] = now.date()
        self.ran_at[name] = now.strftime("%Y-%m-%d %H:%M")
        self.log.add(type="task", name=name, state="running", agent=task["agent"], engine=task["engine"])

        def work():
            result = runner.run_task(task["agent"], task["prompt"], name=name, workspace=self.workspace,
                                     client_factory=self.client_factory, custom=self.custom,
                                     engine=task["engine"] or None)
            self.log.add(type="task", name=name, state="done", file=result.path.name,
                         deliveryError=result.delivery_error)

        threading.Thread(target=work, daemon=True).start()

    def tick(self, now=None):
        """정해진 시각이 된 일을 돌린다. 스케줄러가 주기적으로 부른다."""
        now = now or datetime.datetime.now()
        for task in runner.load_tasks(self.tasks_dir):
            if runner.is_due(task, now, self.last_run.get(task["name"])):
                self.run_task(task["name"])

    def schedule_forever(self):
        stop = threading.Event()
        while not stop.wait(SCHEDULER_SECONDS):
            self.tick()

    # ---- 결과함 ----

    def outbox(self):
        """결과 파일 목록. 새로 바뀐 파일이 위에 온다."""
        folder = self.workspace / "outbox"
        files = [p for p in folder.iterdir() if p.is_file() and p.suffix in OUTBOX_TYPES] \
            if folder.exists() else []
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return {"files": [{"name": p.name, "type": p.suffix[1:], "url": f"/outbox/{p.name}"} for p in files]}

    def outbox_path(self, name):
        path = self.workspace / "outbox" / name
        if not SAFE_NAME.fullmatch(name) or path.suffix not in OUTBOX_TYPES or not path.is_file():
            raise ApiError(404, "그런 결과 파일이 없습니다.")
        return path

    def read_outbox(self, name):
        path = self.outbox_path(name)
        return {"name": name, "type": path.suffix[1:], "url": f"/outbox/{name}",
                "text": path.read_text(encoding="utf-8", errors="replace")}

    # ---- 이름과 색, 스킬 ----

    def brand(self):
        return custom_loader.brand(self.custom)

    def skills(self):
        return {"skills": custom_loader.skills(self.workspace)}


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
                return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                raise ApiError(400, "JSON이 아닙니다.")

        def send_file(self, path, sandbox=False):
            types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", **OUTBOX_TYPES}
            data = path.read_bytes()
            self.send_response(200)
            if sandbox:
                # 에이전트가 만든 파일은 대시보드의 API를 부르지 못하게 따로 떼어 연다.
                self.send_header("Content-Security-Policy", "sandbox")
            self.send_header("Content-Type", types.get(path.suffix, "application/octet-stream") + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            parts = [unquote(p) for p in url.path.split("/") if p]
            try:
                if not parts:
                    return self.send_file(STATIC / "index.html")
                if parts[0] == "static" and len(parts) == 2 and SAFE_NAME.fullmatch(parts[1]) \
                        and (STATIC / parts[1]).is_file():
                    return self.send_file(STATIC / parts[1])
                if len(parts) == 2 and parts[0] == "outbox":
                    return self.send_file(platform.outbox_path(parts[1]), sandbox=True)
                if parts == ["api", "engines"]:
                    return self.send_json(200, platform.engines())
                if parts == ["api", "agents"]:
                    return self.send_json(200, platform.agents())
                if parts == ["api", "brand"]:
                    return self.send_json(200, platform.brand())
                if parts == ["api", "skills"]:
                    return self.send_json(200, platform.skills())
                if parts == ["api", "events"]:
                    after = int(parse_qs(url.query).get("after", ["0"])[0])
                    events = platform.log.since(after)
                    last = events[-1]["seq"] if events else after
                    return self.send_json(200, {"events": events, "last": last, "state": platform.state,
                                                "agent": platform.agent, "engine": platform.engine})
                if parts == ["api", "tasks"]:
                    return self.send_json(200, platform.tasks())
                if parts == ["api", "outbox"]:
                    return self.send_json(200, platform.outbox())
                if len(parts) == 3 and parts[:2] == ["api", "outbox"]:
                    return self.send_json(200, platform.read_outbox(parts[2]))
                raise ApiError(404, "없는 주소입니다.")
            except ApiError as error:
                self.send_json(error.status, {"error": str(error)})

        def do_POST(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            try:
                body = self.read_json()
                if parts == ["api", "session"]:
                    platform.connect(str(body.get("agent", "")), body.get("engine") or None,
                                     fresh=body.get("fresh") is True)
                    return self.send_json(202, {"ok": True})
                if parts == ["api", "agents"]:
                    return self.send_json(201, platform.save_agent(body, create=True))
                if parts == ["api", "prompt"]:
                    platform.send(str(body.get("text", "")))
                    return self.send_json(202, {"ok": True})
                if len(parts) == 3 and parts[:2] == ["api", "permissions"] and parts[2].isdigit():
                    platform.answer(int(parts[2]), body.get("allow") is True)
                    return self.send_json(200, {"ok": True})
                if len(parts) == 4 and parts[:2] == ["api", "tasks"] and parts[3] == "run":
                    platform.run_task(parts[2])
                    return self.send_json(202, {"ok": True})
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

        def do_PUT(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            try:
                body = self.read_json()
                if len(parts) == 3 and parts[:2] == ["api", "agents"]:
                    return self.send_json(200, platform.save_agent({**body, "name": parts[2]}, create=False))
                raise ApiError(404, "없는 주소입니다.")
            except ApiError as error:
                self.send_json(error.status, {"error": str(error)})

        def do_DELETE(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
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
    threading.Thread(target=platform.schedule_forever, daemon=True).start()
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
