"""내 에이전트 플랫폼의 대시보드. 브라우저로 여는 작은 웹 서버다.

실행: python dashboard.py      → http://127.0.0.1:8765 이 열린다
      python dashboard.py --no-browser   (브라우저를 열지 않는다)

서버는 JSON API만 낸다. 화면(app/static/)은 그 API를 부르는 클라이언트다.
API의 목록은 README의 '대시보드 API' 절에 있다.
대시보드가 켜져 있는 동안 tasks/의 일을 정해진 시각에 돌린다.
custom/의 파일(이름과 색, 업무, 허락 규칙, 결과 보내기)은 custom_loader.py가 읽어 잇는다.
대화 기록은 conversations.py가 conversations/에 파일로 남긴다.
"""

import datetime
import json
import mimetypes
import pathlib
import re
import secrets
import shutil
import sys
import subprocess
import threading
import unicodedata
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import custom_loader
import engines
import runner
from conversations import ConversationError, ConversationStore
from engines import EngineError

ROOT = pathlib.Path(__file__).parent
STATIC = ROOT / "app" / "static"
HOST, PORT = "127.0.0.1", 8765
PERMISSION_WAIT_SECONDS = 300
SCHEDULER_SECONDS = 20
LOGIN_WAIT_SECONDS = 900
SAFE_NAME = re.compile(r"[\w가-힣.\-]+")
OUTBOX_TYPES = {".md": "text/markdown", ".json": "application/json", ".html": "text/html",
                ".txt": "text/plain", ".csv": "text/csv"}
UPLOAD_BYTES = 20 * 1024 * 1024   # 올리는 파일 하나의 크기 상한
MAX_FILES = 10                    # 질문 하나에 붙이는 파일 수의 상한
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


def clean_name(name):
    """올린 파일의 이름을 작업 폴더에 둘 수 있는 이름으로 바꾼다. 폴더는 떼고, 쓸 수 없는 글자는 _로 바꾼다.

    macOS가 한글 이름을 풀어 쓴 꼴(NFD)로 보내도 붙여 쓴 꼴(NFC)로 맞춘다. 에이전트가 경로를 같게 쓰게 하려는 것이다.
    """
    name = unicodedata.normalize("NFC", re.split(r"[\\/]", str(name or ""))[-1])
    name = re.sub(r"[^\w.\-]+", "_", name).lstrip(".")
    stem, dot, suffix = name.rpartition(".")
    if dot and stem:
        name = f"{stem[:100]}.{suffix[:10]}"
    return name[:120] or "file"


def file_info(path):
    """올린 파일 하나의 정보. path는 작업 폴더 기준 경로다."""
    return {"name": path.name, "path": f"inbox/{path.name}", "url": f"/inbox/{path.name}",
            "type": mimetypes.guess_type(path.name)[0] or "application/octet-stream", "size": path.stat().st_size}


def tool_line(request):
    """대화 기록에 남길 도구 한 줄. 예: "명령 실행 python3 skills/memo-to-json/scripts/save_memo.py"."""
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
    """에이전트, 대화, 일 목록, 스케줄, 결과함, 로그인을 맡는다.

    에이전트(custom/agents/)는 플랫폼이 정하고, 엔진(engines/)은 그 에이전트를 돌리는 부품이다.
    이 클래스는 엔진 이름을 몰라도 된다. 엔진마다 다른 것은 engines/가 맡는다.
    """

    def __init__(self, root=ROOT, client_factory=engines.make, status_checker=check_login,
                 install_checker=lambda engine: engine.installed(), logins=None):
        self.workspace = pathlib.Path(root) / "workspace"
        self.tasks_dir = pathlib.Path(root) / "tasks"
        self.custom = pathlib.Path(root) / "custom"
        self.store = ConversationStore(pathlib.Path(root) / "conversations")
        self.client_factory = client_factory
        self.status_checker = status_checker
        self.install_checker = install_checker
        self.log = EventLog()
        self.logins = logins or Logins(self.log)
        self.lock = threading.Lock()
        # 엔진 세션은 한 번에 하나만 열어 둔다. 아래 넷은 그 세션의 것이다.
        self.client = None
        self.conversation_id = None  # 세션을 연 대화
        self.agent = None            # 그 대화의 에이전트
        self.engine = None           # 그 에이전트를 돌리는 엔진
        self.state = "idle"          # idle, starting, ready, busy, error
        self.partial = []            # 지금 차례에 받은 답 조각. 엔진이 중간에 끝나도 남기려고 모은다
        self.pending = {}            # 허락을 기다리는 요청: 번호 → {event, allow}
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
        configs = {name: engines.get(name) for name in engines.names()}
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
                             "loginMode": configs[name].login_mode,
                             "loginCommand": " ".join(configs[name].login),
                             "canLogout": bool(configs[name].logout)} for name in names]}

    # ---- 에이전트 ----

    def agents(self):
        return {"agents": custom_loader.agents(self.custom), "current": self.agent, "engine": self.engine,
                "state": self.state}

    def save_agent(self, body, create):
        try:
            return custom_loader.save_agent(body, self.custom, self.workspace, create=create)
        except custom_loader.AgentError as error:
            raise ApiError(error.status, str(error))

    def _agent_and_engine(self, agent, engine=None):
        """에이전트를 읽고 돌릴 엔진을 정한다. engine을 주면 에이전트 파일의 engine 대신 그 엔진으로 돌린다."""
        try:
            definition = custom_loader.agent(agent, self.custom)
            engine = engine or definition["engine"]
            engines.get(engine)
        except custom_loader.AgentError as error:
            raise ApiError(error.status, str(error))
        except EngineError as error:
            raise ApiError(400, str(error))
        return definition, engine

    # ---- 대화 ----
    #
    # 대화 하나는 conversations/<번호>.json 하나다(conversations.py). 대화마다 에이전트 하나와 이야기한다.
    # 질문을 받은 대화가 지금 열어 둔 엔진 세션의 대화가 아니거나 엔진이 바뀌었으면 세션을 새로 연다.
    # 새 세션의 첫 질문 앞에는 플랫폼 안내를 붙이고, 그 안내에 그 대화의 앞부분을 넣는다.
    # 그래서 대화를 바꿔도, 엔진을 바꿔도, 대시보드를 다시 켜도 대화가 이어진다.

    def conversations(self):
        return {"conversations": self.store.listing()}

    def conversation(self, conversation_id):
        try:
            return self.store.load(conversation_id)
        except ConversationError as error:
            raise ApiError(error.status, str(error))

    def create_conversation(self, agent, engine=None):
        definition, engine = self._agent_and_engine(str(agent or ""), engine or None)
        return self.store.create(definition["name"], engine)

    def _running(self, conversation_id):
        """그 대화가 답을 쓰는 중인지 본다. self.lock 안에서 부른다."""
        return self.conversation_id == conversation_id and self.state in ("starting", "busy")

    def _detach(self):
        """열어 둔 엔진 세션을 떼어 낸다. self.lock 안에서 부르고, 돌려받은 세션은 lock 밖에서 닫는다."""
        old, self.client = self.client, None
        self.conversation_id, self.agent, self.engine, self.state = None, None, None, "idle"
        return old

    def change_engine(self, conversation_id, engine):
        """대화의 엔진을 바꾼다. 다음 질문에서 새 엔진의 세션을 열고 지금까지의 대화를 넘긴다."""
        conversation = self.conversation(conversation_id)
        if not engine:
            raise ApiError(400, "바꿀 엔진이 없습니다.")
        _, engine = self._agent_and_engine(conversation["agent"], str(engine))
        if engine == conversation["engine"]:
            return conversation
        with self.lock:
            if self._running(conversation_id):
                raise ApiError(409, "이 대화의 답을 쓰는 중입니다. 끝난 뒤에 엔진을 바꿉니다.")
            old = self._detach() if self.conversation_id == conversation_id else None
        if old:
            old.close()
        note = (f"엔진을 {conversation['engine']}에서 {engine}로 바꿨다. "
                "다음 질문을 보낼 때 지금까지의 대화를 플랫폼 안내에 넣어 이어 간다.")
        try:
            return self.store.change_engine(conversation_id, engine, note)
        except ConversationError as error:
            raise ApiError(error.status, str(error))

    def delete_conversation(self, conversation_id):
        with self.lock:
            if self._running(conversation_id):
                raise ApiError(409, "이 대화의 답을 쓰는 중입니다. 끝난 뒤에 지웁니다.")
            try:
                self.store.delete(conversation_id)
            except ConversationError as error:
                raise ApiError(error.status, str(error))
            old = self._detach() if self.conversation_id == conversation_id else None
        if old:
            old.close()

    def prompt(self, conversation_id, text, files=None):
        """대화에 질문을 보낸다. 답은 사건으로 오고, 끝나면 대화 기록에 남는다.

        files: 올린 파일의 작업 폴더 기준 경로(inbox/<이름>). 엔진 층이 그 엔진에 맞는 꼴로 보낸다.
        """
        text = str(text or "").strip()
        files = self._attachments(files)
        if not text and not files:
            raise ApiError(400, "보낼 내용이 없습니다.")
        conversation = self.conversation(conversation_id)
        definition, engine = self._agent_and_engine(conversation["agent"], conversation["engine"])
        with self.lock:
            if self.state in ("starting", "busy"):
                raise ApiError(409, "다른 질문의 답을 쓰는 중입니다. 끝난 뒤에 보냅니다.")
            reuse = (self.client is not None and self.state == "ready"
                     and (self.conversation_id, self.engine) == (conversation_id, engine))
            old = None if reuse else self._detach()
            self.conversation_id, self.agent, self.engine = conversation_id, definition["name"], engine
            self.state = "busy" if reuse else "starting"
            self.partial = []
        if old:
            old.close()
        self._record(conversation_id, {"role": "user", "text": text, **({"files": files} if files else {})})
        self._event("user", text=text, files=files)
        self._event("status", state=self.state, agent=self.agent, engine=engine)
        threading.Thread(target=self._turn, daemon=True,
                         args=(conversation_id, definition, engine, conversation["messages"], text, files, reuse)).start()

    def _turn(self, conversation_id, definition, engine, history, text, files, reuse):
        """질문 하나를 엔진에 보낸다. 엔진이 어떤 꼴로 답하든 하나의 형식(TurnResult)으로 받아 기록과 화면에 쓴다."""
        client, result, error = self.client if reuse else None, None, None
        try:
            if client is None:
                client = self._open(conversation_id, definition, engine, history)
            result = client.send(custom_loader.with_files(text, files), [self.workspace / path for path in files])
        except Exception as failure:  # 엔진 오류든 코드의 버그든 기록하고, 다음 질문을 받을 수 있게 한다
            error = failure
        if result is not None:
            self._record(conversation_id, {
                "role": "agent", "text": result.text, "engine": engine, "stop": result.stop,
                "stopLabel": result.stop_label, "usage": result.usage_text,
                "tools": [tool_line(t) for t in result.tools], "refused": [tool_line(t) for t in result.refused],
                "notices": result.notices})
        else:
            partial = "".join(self.partial).strip()
            if partial:
                self._record(conversation_id, {"role": "agent", "text": partial, "engine": engine,
                                               "stop": "error", "stopLabel": "오류로 멈춤"})
            self._record(conversation_id, {"role": "note", "text": f"오류: {error}", "error": True})
        with self.lock:
            self.state = "ready" if result is not None else "error"
        if result is not None:
            self._event("done", stop=result.stop, stopLabel=result.stop_label, usage=result.usage_text,
                        refused=len(result.refused))
        else:
            self._event("status", state="error", agent=definition["name"], engine=engine, message=str(error))

    def _open(self, conversation_id, definition, engine, history):
        """엔진 세션을 새로 연다. 첫 질문에 붙일 플랫폼 안내에 그 대화의 앞부분(history)을 넣는다."""
        preamble = custom_loader.preamble(self.workspace, self.custom, definition, history)
        client = self.client_factory(engine, self.workspace, on_text=self._on_text, on_tool=self._on_tool,
                                     on_permission=self._ask, on_notice=self._on_notice, preamble=preamble)
        try:
            client.start()
        except EngineError:
            client.close()
            raise
        with self.lock:
            self.client, self.state = client, "busy"
        carried = len(custom_loader.history_lines(history))
        self._record(conversation_id, {"role": "preamble", "text": preamble, "engine": engine, "history": carried})
        self._event("status", state="busy", agent=definition["name"], engine=engine)
        self._event("preamble", agent=definition["name"], engine=engine, text=preamble, history=carried)
        return client

    def _record(self, conversation_id, message):
        """대화 기록에 메시지를 더한다. 대화 파일이 없어졌거나 쓰지 못하면 기록을 건너뛰고 계속한다."""
        try:
            self.store.append(conversation_id, message)
        except (ConversationError, OSError) as error:
            self.log.add(type="record_error", conversation=conversation_id, message=f"대화 기록을 저장하지 못했다: {error}")

    def _event(self, event_type, **fields):
        """대화의 사건. 어느 대화의 것인지 conversation 칸에 적는다."""
        return self.log.add(type=event_type, conversation=self.conversation_id, **fields)

    def snapshot(self):
        """지금 엔진 세션과 진행 중인 차례의 사건. 화면이 처음 열릴 때 부른다."""
        with self.lock:
            state, conversation_id, agent, engine = self.state, self.conversation_id, self.agent, self.engine
        with self.log.cond:
            events = list(self.log.events)
        live = []
        if state in ("starting", "busy"):
            asked = [i for i, e in enumerate(events) if e["type"] == "user" and e.get("conversation") == conversation_id]
            if asked:
                live = [e for e in events[asked[-1] + 1:] if e.get("conversation") == conversation_id]
        return {"state": state, "agent": agent, "engine": engine, "conversation": conversation_id,
                "live": live, "last": len(events), "epoch": self.log.epoch}

    def _on_text(self, text):
        self.partial.append(text)
        self._event("text", text=text)

    def _on_notice(self, text):
        self._event("notice", text=text)

    def _on_tool(self, request):
        self._event("tool", kind=request.kind, label=request.label, detail=request.detail)

    def _ask(self, request):
        """에이전트가 허락을 물으면 먼저 custom/rules.py에 묻고, "ask"이면 카드를 띄워 사람의 답을 기다린다."""
        decision, error = custom_loader.decide(self.agent, request, self.custom)
        if error:
            self._event("rule_error", message=error)
        if decision != "ask":
            self._event("rule", kind=request.kind, label=request.label, detail=request.detail,
                        allow=decision == "allow")
            return decision == "allow"
        with self.lock:
            self.next_permission += 1
            number = self.next_permission
            waiter = {"event": threading.Event(), "allow": False}
            self.pending[number] = waiter
        self._event("permission", id=number, kind=request.kind, label=request.label,
                    detail=request.detail, title=request.title)
        answered = waiter["event"].wait(PERMISSION_WAIT_SECONDS)
        with self.lock:
            self.pending.pop(number, None)
        allow = waiter["allow"] if answered else False
        self._event("permission_result", id=number, allow=allow, timeout=not answered)
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

    # ---- 올린 파일 ----
    #
    # 사람이 올린 파일은 workspace/inbox/에 둔다. 엔진이 일하는 폴더 안이라서 엔진도 경로로 읽을 수 있다.

    def upload(self, name, data):
        """파일 하나를 workspace/inbox/에 저장한다. 같은 이름이 있으면 덮어쓰지 않고 뒤에 -2, -3을 붙인다."""
        folder = self.workspace / "inbox"
        folder.mkdir(parents=True, exist_ok=True)
        clean = clean_name(name)
        stem, dot, suffix = clean.rpartition(".")
        if not stem:
            stem, dot, suffix = clean, "", ""
        path, number = folder / clean, 1
        while True:
            try:
                with open(path, "xb") as out:
                    out.write(data)
                return file_info(path)
            except FileExistsError:
                number += 1
                path = folder / f"{stem}-{number}{dot}{suffix}"

    def inbox_path(self, name):
        path = self.workspace / "inbox" / name
        if not SAFE_NAME.fullmatch(name) or name.startswith(".") or not path.is_file():
            raise ApiError(404, "그런 파일이 없습니다.")
        return path

    def _attachments(self, files):
        """질문에 붙인 파일(inbox/<이름>)이 실제로 올린 파일인지 확인한다."""
        if not files:
            return []
        if not isinstance(files, list) or len(files) > MAX_FILES:
            raise ApiError(400, f"파일은 질문 하나에 {MAX_FILES}개까지 붙입니다.")
        checked = []
        for item in files:
            folder, _, name = str(item).partition("/")
            if folder != "inbox":
                raise ApiError(400, f"올린 파일 '{item}'을 찾지 못했습니다. 먼저 올립니다.")
            try:
                self.inbox_path(name)
            except ApiError:
                raise ApiError(400, f"올린 파일 '{item}'을 찾지 못했습니다. 먼저 올립니다.")
            checked.append(f"inbox/{name}")
        return checked

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

    def skill(self, name):
        """스킬 하나의 SKILL.md와 그 스킬을 쓰는 에이전트."""
        found = next((s for s in custom_loader.skills(self.workspace) if s["name"] == name), None)
        if found is None:
            raise ApiError(404, f"스킬 '{name}'이 없습니다.")
        users = [a["name"] for a in custom_loader.agents(self.custom) if a["skills"] is None or name in a["skills"]]
        text = (self.workspace / found["path"]).read_text(encoding="utf-8")
        return {**found, "text": text, "agents": users}


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
                # 에이전트가 만든 파일과 사람이 올린 파일은 대시보드의 API를 부르지 못하게 따로 떼어 연다.
                self.send_header("Content-Security-Policy", "sandbox")
                self.send_header("X-Content-Type-Options", "nosniff")
            kind = types.get(path.suffix.lower())
            if kind:
                kind += "; charset=utf-8"
            else:
                kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_header("Content-Type", kind)
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
                if len(parts) == 2 and parts[0] == "inbox":
                    return self.send_file(platform.inbox_path(parts[1]), sandbox=True)
                if parts == ["api", "engines"]:
                    return self.send_json(200, platform.engines())
                if parts == ["api", "agents"]:
                    return self.send_json(200, platform.agents())
                if parts == ["api", "brand"]:
                    return self.send_json(200, platform.brand())
                if parts == ["api", "skills"]:
                    return self.send_json(200, platform.skills())
                if len(parts) == 3 and parts[:2] == ["api", "skills"]:
                    return self.send_json(200, platform.skill(parts[2]))
                if parts == ["api", "events"]:
                    after = int(parse_qs(url.query).get("after", ["0"])[0])
                    events = platform.log.since(after)
                    last = events[-1]["seq"] if events else after
                    return self.send_json(200, {"events": events, "last": last, "epoch": platform.log.epoch,
                                                "state": platform.state, "agent": platform.agent,
                                                "engine": platform.engine, "conversation": platform.conversation_id})
                if parts == ["api", "state"]:
                    return self.send_json(200, platform.snapshot())
                if parts == ["api", "conversations"]:
                    return self.send_json(200, platform.conversations())
                if len(parts) == 3 and parts[:2] == ["api", "conversations"]:
                    return self.send_json(200, platform.conversation(parts[2]))
                if parts == ["api", "tasks"]:
                    return self.send_json(200, platform.tasks())
                if parts == ["api", "outbox"]:
                    return self.send_json(200, platform.outbox())
                if len(parts) == 3 and parts[:2] == ["api", "outbox"]:
                    return self.send_json(200, platform.read_outbox(parts[2]))
                raise ApiError(404, "없는 주소입니다.")
            except ApiError as error:
                self.send_json(error.status, {"error": str(error)})

        def read_upload(self):
            """올리는 파일의 본문(파일 그대로)을 읽는다. 너무 크면 다 읽어 버린 뒤 413으로 거절한다."""
            length = int(self.headers.get("Content-Length") or 0)
            if length > UPLOAD_BYTES:
                while length > 0:
                    chunk = self.rfile.read(min(length, 1024 * 1024))
                    if not chunk:
                        break
                    length -= len(chunk)
                raise ApiError(413, f"파일이 너무 큽니다. {UPLOAD_BYTES // (1024 * 1024)}MB까지 올립니다.")
            return self.rfile.read(length)

        def do_POST(self):
            url = urlparse(self.path)
            parts = [unquote(p) for p in url.path.split("/") if p]
            try:
                if parts == ["api", "uploads"]:
                    name = parse_qs(url.query).get("name", [""])[0]
                    return self.send_json(201, platform.upload(name, self.read_upload()))
                body = self.read_json()
                if parts == ["api", "conversations"]:
                    return self.send_json(201, platform.create_conversation(body.get("agent"), body.get("engine")))
                if len(parts) == 4 and parts[:2] == ["api", "conversations"] and parts[3] == "prompt":
                    platform.prompt(parts[2], body.get("text"), body.get("files"))
                    return self.send_json(202, {"ok": True})
                if parts == ["api", "agents"]:
                    return self.send_json(201, platform.save_agent(body, create=True))
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

        def do_PATCH(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            try:
                body = self.read_json()
                if len(parts) == 3 and parts[:2] == ["api", "conversations"]:
                    return self.send_json(200, platform.change_engine(parts[2], body.get("engine")))
                raise ApiError(404, "없는 주소입니다.")
            except ApiError as error:
                self.send_json(error.status, {"error": str(error)})

        def do_DELETE(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            try:
                if len(parts) == 3 and parts[:2] == ["api", "conversations"]:
                    platform.delete_conversation(parts[2])
                    return self.send_json(200, {"ok": True})
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
