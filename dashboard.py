"""내 에이전트 플랫폼의 대시보드. 브라우저로 여는 작은 웹 서버다.

실행: python dashboard.py      → http://127.0.0.1:8765 이 열린다
      python dashboard.py --no-browser   (브라우저를 열지 않는다)

서버는 JSON API만 낸다. 화면(app/static/)은 그 API를 부르는 클라이언트다.
API의 목록은 README의 '대시보드 API' 절에 있다.
대시보드가 켜져 있는 동안 tasks/의 일을 정해진 시각에 돌린다.
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
import runner
from acp_client import AcpClient, AcpError

ROOT = pathlib.Path(__file__).parent
STATIC = ROOT / "app" / "static"
HOST, PORT = "127.0.0.1", 8765
PERMISSION_WAIT_SECONDS = 300
SCHEDULER_SECONDS = 20
SAFE_NAME = re.compile(r"[\w가-힣.\-]+")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def check_login(name):
    """샌드박스 홈의 로그인 상태를 본다. 알 수 없으면 None."""
    agent = acp_client.load_agent(name)
    command = agent.get("status")
    if not command or shutil.which(command[0]) is None:
        return None
    try:
        result = subprocess.run([shutil.which(command[0]), *command[1:]],
                                env=acp_client.sandbox_env(name, agent),
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


class Platform:
    """대화 하나, 일 목록, 스케줄, 결과함을 맡는다."""

    def __init__(self, root=ROOT, client_factory=AcpClient, status_checker=check_login):
        self.workspace = pathlib.Path(root) / "workspace"
        self.tasks_dir = pathlib.Path(root) / "tasks"
        self.client_factory = client_factory
        self.status_checker = status_checker
        self.log = EventLog()
        self.lock = threading.Lock()
        self.client = None
        self.agent = None
        self.state = "idle"          # idle, starting, ready, busy, error
        self.pending = {}            # 허락을 기다리는 요청: 번호 → {event, allow}
        self.next_permission = 0
        self.last_run = {}           # 스케줄 판단용: 일 이름 → 오늘 돌렸거나 건너뛴 날짜
        self.ran_at = {}             # 화면 표시용: 일 이름 → 실제로 돌린 시각
        # 켜기 전에 이미 지난 오늘의 일은 돌리지 않는다. 놓친 실행을 몰아서 하지 않는다.
        now = datetime.datetime.now()
        for task in runner.load_tasks(self.tasks_dir):
            if task["time"] and now.strftime("%H:%M") >= task["time"]:
                self.last_run[task["name"]] = now.date()

    # ---- 에이전트와 대화 ----

    def agents(self):
        names = list(json.loads(acp_client.AGENTS_FILE.read_text(encoding="utf-8")))
        results = {}

        def check(name):
            results[name] = self.status_checker(name)

        threads = [threading.Thread(target=check, args=(name,)) for name in names]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return {"agents": [{"name": name, "loggedIn": results.get(name)} for name in names],
                "current": self.agent, "state": self.state}

    def connect(self, agent):
        try:
            acp_client.load_agent(agent)
        except AcpError as error:
            raise ApiError(400, str(error))
        with self.lock:
            if self.state in ("starting", "busy"):
                raise ApiError(409, "앞의 일이 끝난 뒤에 바꿀 수 있습니다.")
            old, self.client = self.client, None
            self.agent, self.state = agent, "starting"
        if old:
            old.close()
        self.log.add(type="status", state="starting", agent=agent)
        threading.Thread(target=self._start, args=(agent,), daemon=True).start()

    def _start(self, agent):
        client = self.client_factory(self.workspace, agent, on_text=self._on_text,
                                     on_tool=self._on_tool, on_permission=self._ask)
        try:
            client.start()
        except AcpError as error:
            client.close()
            with self.lock:
                self.state = "error"
            self.log.add(type="status", state="error", agent=agent, message=str(error))
            return
        with self.lock:
            if self.agent != agent:
                client.close()
                return
            self.client, self.state = client, "ready"
        self.log.add(type="status", state="ready", agent=agent)

    def send(self, text):
        if not text.strip():
            raise ApiError(400, "보낼 내용이 없습니다.")
        with self.lock:
            if self.state != "ready":
                raise ApiError(409, "에이전트가 준비되지 않았거나 앞의 답을 쓰는 중입니다.")
            self.state, client = "busy", self.client
        self.log.add(type="user", text=text)
        threading.Thread(target=self._prompt, args=(client, text), daemon=True).start()

    def _prompt(self, client, text):
        try:
            stop_reason = client.prompt(text)
            self.log.add(type="done", stopReason=stop_reason, usage=client.usage_text())
            state = "ready"
        except AcpError as error:
            self.log.add(type="status", state="error", agent=self.agent, message=str(error))
            state = "error"
        with self.lock:
            if self.client is client:
                self.state = state

    def _on_text(self, text):
        self.log.add(type="text", text=text)

    def _on_tool(self, update):
        if update.get("sessionUpdate") == "tool_call":
            self.log.add(type="tool", title=update.get("title", ""))

    def _ask(self, tool_call):
        """에이전트가 허락을 물으면 화면에 카드를 띄우고 사람의 답을 기다린다."""
        with self.lock:
            self.next_permission += 1
            number = self.next_permission
            waiter = {"event": threading.Event(), "allow": False}
            self.pending[number] = waiter
        raw = tool_call.get("rawInput") or {}
        detail = raw.get("command") or raw.get("file_path") or raw.get("path") or ""
        self.log.add(type="permission", id=number, title=tool_call.get("title", ""),
                     detail=str(detail))
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
        self.log.add(type="task", name=name, state="running", agent=task["agent"])

        def work():
            path = runner.run_task(task["agent"], task["prompt"], name=name,
                                   workspace=self.workspace, client_factory=self.client_factory)
            self.log.add(type="task", name=name, state="done", file=path.name)

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
        folder = self.workspace / "outbox"
        files = sorted(folder.glob("*.md"), reverse=True) if folder.exists() else []
        return {"files": [{"name": path.name} for path in files]}

    def read_outbox(self, name):
        path = self.workspace / "outbox" / name
        if not SAFE_NAME.fullmatch(name) or not path.is_file():
            raise ApiError(404, "그런 결과 파일이 없습니다.")
        return {"name": name, "text": path.read_text(encoding="utf-8")}


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

        def send_file(self, path):
            types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}
            data = path.read_bytes()
            self.send_response(200)
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
                if parts == ["api", "agents"]:
                    return self.send_json(200, platform.agents())
                if parts == ["api", "events"]:
                    after = int(parse_qs(url.query).get("after", ["0"])[0])
                    events = platform.log.since(after)
                    last = events[-1]["seq"] if events else after
                    return self.send_json(200, {"events": events, "last": last,
                                                "state": platform.state, "agent": platform.agent})
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
                    platform.connect(str(body.get("agent", "")))
                    return self.send_json(202, {"ok": True})
                if parts == ["api", "prompt"]:
                    platform.send(str(body.get("text", "")))
                    return self.send_json(202, {"ok": True})
                if len(parts) == 3 and parts[:2] == ["api", "permissions"] and parts[2].isdigit():
                    platform.answer(int(parts[2]), body.get("allow") is True)
                    return self.send_json(200, {"ok": True})
                if len(parts) == 4 and parts[:2] == ["api", "tasks"] and parts[3] == "run":
                    platform.run_task(parts[2])
                    return self.send_json(202, {"ok": True})
                raise ApiError(404, "없는 주소입니다.")
            except ApiError as error:
                self.send_json(error.status, {"error": str(error)})

    return Handler


def serve(platform, host=HOST, port=PORT):
    return ThreadingHTTPServer((host, port), make_handler(platform))


def main():
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
