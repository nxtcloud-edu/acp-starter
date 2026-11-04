"""가짜 엔진으로 대시보드의 API를 확인한다. 실제 엔진을 부르지 않는다.

실행: python -m unittest discover tests
"""

import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import dashboard  # noqa: E402
import engines  # noqa: E402
from engines import AcpEngine  # noqa: E402

FAKE = [sys.executable, str(pathlib.Path(__file__).parent / "fake_agent.py")]
FAKE_LOGIN = str(pathlib.Path(__file__).parent / "fake_login.py")


class TerminalLogin(AcpEngine):
    name, login, login_mode = "kiro", ["kiro-cli", "login"], "terminal"


class CodeLogin(AcpEngine):
    name, login, login_mode = "claude", [sys.executable, FAKE_LOGIN, "code"], "code"
    # UTF-8이 아닌 바이트를 내는 로그아웃 명령. Windows에서는 명령의 출력을 cp949로 읽으면 깨진다.
    logout = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe bye'); sys.exit(0)"]


class DeviceLogin(AcpEngine):
    name, login, login_mode = "codex", [sys.executable, FAKE_LOGIN, "device"], "device"


LOGIN_ENGINES = {e.name: e for e in (TerminalLogin, CodeLogin, DeviceLogin)}


def fake_login_engine(name):
    if name not in LOGIN_ENGINES:
        raise dashboard.EngineError("없는 엔진")
    return LOGIN_ENGINES[name]


ENGINES_USED = []   # 가짜 엔진을 만들 때 받은 엔진 이름. 엔진을 바꿔 끼웠는지 확인한다


def fake_factory(engine, workspace, **callbacks):
    """엔진의 어댑터는 그대로 쓰고, 실행하는 프로그램만 가짜 엔진으로 바꾼다."""
    ENGINES_USED.append(engine)
    mode = "engine" if engines.get(engine).expect_mode else "auto"
    return engines.make(engine, workspace, command=FAKE + [mode], env=dict(os.environ), **callbacks)


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        (self.root / "workspace").mkdir()
        ENGINES_USED.clear()
        self.platform = dashboard.Platform(self.root, client_factory=fake_factory,
                                           status_checker=lambda name: True,
                                           install_checker=lambda engine: True)
        self.logged_in = set()
        self.platform.logins = dashboard.Logins(self.platform.log, load_engine=fake_login_engine,
                                                env_for=lambda name, agent: dict(os.environ),
                                                is_logged_in=lambda name: name in self.logged_in)
        self.server = dashboard.serve(self.platform, port=0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        if self.platform.client:
            self.platform.client.close()

    def call(self, method, path, body=None, raw=None):
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def wait_for(self, check, timeout=15, log=None, after=0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            events = (log or self.platform.log).events
            found = [e for e in events if e["seq"] > after and check(e)]
            if found:
                return found[0]
            time.sleep(0.05)
        self.fail("기다린 사건이 오지 않았습니다.")

    def send(self, text):
        """질문을 보내고, 보내기 전의 사건 수를 돌려준다. 그 뒤의 사건이 이 질문의 것이다."""
        start = len(self.platform.log.events)
        status, body = self.call("POST", "/api/prompt", {"text": text})
        self.assertEqual(status, 202, body)
        return start

    def ask(self, text):
        """질문을 보내고 차례가 끝날 때까지 기다린 뒤 받은 답 조각을 이어 돌려준다."""
        start = self.send(text)
        self.wait_for(lambda e: e["type"] == "done", after=start)
        return "".join(e["text"] for e in self.platform.log.events[start:] if e["type"] == "text")

    def connect(self, engine):
        """엔진을 연결하고 준비될 때까지 기다린다."""
        start = len(self.platform.log.events)
        status, body = self.call("POST", "/api/connect", {"engine": engine})
        self.assertEqual(status, 202, body)
        self.wait_for(lambda e: e["type"] == "status" and e["state"] == "ready", after=start)
        return start

    def text_so_far(self):
        return "".join(e["text"] for e in self.platform.log.events if e["type"] == "text")

    def last_preamble(self):
        return [e for e in self.platform.log.events if e["type"] == "preamble"][-1]

    def conversation(self):
        return self.call("GET", "/api/conversation")[1]

    def write_custom(self, name, text):
        (self.root / "custom").mkdir(exist_ok=True)
        (self.root / "custom" / name).write_text(text, encoding="utf-8")

    # ---- 화면과 읽기 API ----

    def test_page_and_static_files_are_served(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as response:
            self.assertIn("text/html", response.headers["Content-Type"])
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/static/app.js") as response:
            self.assertIn("text/javascript", response.headers["Content-Type"])
        self.assertEqual(self.call("GET", "/static/..%2F..%2Fdashboard.py")[0], 404)
        self.assertEqual(self.call("GET", "/api/" + urllib.request.quote("없는것"))[0], 404)

    def test_state_has_the_current_conversation(self):
        status, state = self.call("GET", "/api/state")
        self.assertEqual((status, state["state"], state["engine"], state["live"]), (200, "idle", None, []))
        self.assertEqual(state["conversation"]["messages"], [])
        self.assertEqual(state["conversation"]["engine"], engines.names()[0])
        self.assertEqual(self.conversation()["id"], state["conversation"]["id"])

    def test_engines_list_login_state(self):
        status, body = self.call("GET", "/api/engines")
        self.assertEqual(status, 200)
        self.assertEqual({e["name"] for e in body["engines"]}, set(engines.names()))
        self.assertTrue(all(e["loggedIn"] is True for e in body["engines"]))

    def test_brand(self):
        self.write_custom("brand.json", '{"name": "마감지기", "tagline": "마감만 본다", "accent": "#123456"}')
        status, body = self.call("GET", "/api/brand")
        self.assertEqual((status, body["name"], body["tagline"], body["accent"]), (200, "마감지기", "마감만 본다", "#123456"))

    def test_events_tell_a_stale_page_to_start_over(self):
        status, body = self.call("GET", "/api/events?after=500")   # 서버를 다시 켜기 전의 번호
        self.assertEqual((status, body["events"]), (200, []))
        self.assertEqual(body["epoch"], self.platform.log.epoch)
        self.assertEqual(self.call("GET", "/api/events?after=x")[0], 400)

    # ---- 대화 ----

    def test_chat_streams_answer_through_events(self):
        self.assertEqual(self.ask("안녕"), "받음: 안녕")
        status, body = self.call("GET", "/api/events?after=0")
        self.assertEqual(status, 200)
        self.assertEqual([e["type"] for e in body["events"]][:4], ["user", "status", "preamble", "status"])
        self.assertEqual(body["last"], body["events"][-1]["seq"])
        roles = [m["role"] for m in self.conversation()["messages"]]
        self.assertEqual(roles, ["user", "preamble", "agent"])

    def test_prompt_needs_text_and_json(self):
        status, body = self.call("POST", "/api/prompt", {"text": "  "})
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        self.assertEqual(self.call("POST", "/api/prompt", raw=b"{")[0], 400)
        self.assertEqual(self.call("POST", "/api/prompt", raw=b"[1]")[0], 400)

    def test_preamble_goes_with_first_prompt_only(self):
        self.write_custom("업무.md", "- 맡는 업무: 마감 정리\n")
        self.assertEqual(self.ask("안내"), "받음: 있음")
        self.assertIn("마감 정리", self.last_preamble()["text"])
        self.assertEqual(self.ask("안내"), "받음: 없음")
        self.assertEqual(len(ENGINES_USED), 1)                # 같은 세션을 그대로 쓴다

    def test_tools_and_refusals_are_kept_in_the_record(self):
        self.send("도구 써 줘")
        card = self.wait_for(lambda e: e["type"] == "permission")
        self.call("POST", f"/api/permissions/{card['id']}", {"allow": False})
        self.wait_for(lambda e: e["type"] == "done")
        agent = self.conversation()["messages"][-1]
        # 가짜 엔진은 Kiro처럼 시작 알림에 제목만 보내고, 명령은 허락 요청에 담는다.
        self.assertEqual((agent["tools"], agent["refused"]), (["명령 실행 Running: date"], ["명령 실행 date"]))

    def test_platform_keeps_working_when_the_record_cannot_be_saved(self):
        # Windows에서는 다른 프로그램이 파일을 잡고 있으면 저장이 실패할 수 있다. 그래도 답을 끝내고 다음 질문을 받는다.
        real_append = self.platform.store.append

        def append(conversation_id, message):
            if message["role"] == "agent":
                raise PermissionError(13, "다른 프로그램이 파일을 쓰는 중")
            return real_append(conversation_id, message)

        with mock.patch.object(self.platform.store, "append", append):
            self.assertEqual(self.ask("하나"), "받음: 하나")
        self.wait_for(lambda e: e["type"] == "record_error")
        self.assertEqual(self.platform.state, "ready")
        self.assertEqual(self.ask("둘"), "받음: 둘")

    def test_conversation_continues_after_restart(self):
        self.ask("어제 한 이야기")
        # 대시보드를 껐다 켠 것과 같다: 같은 폴더로 플랫폼을 새로 만든다.
        restarted = dashboard.Platform(self.root, client_factory=fake_factory, status_checker=lambda name: True,
                                       install_checker=lambda engine: True)
        self.addCleanup(lambda: restarted.client and restarted.client.close())
        restarted.prompt("오늘 이어서")
        self.wait_for(lambda e: e["type"] == "done", log=restarted.log)
        note = self.wait_for(lambda e: e["type"] == "preamble", log=restarted.log)
        self.assertEqual(note["history"], 2)
        self.assertIn("[사용자] 어제 한 이야기", note["text"])

    def test_new_conversation_starts_without_history_and_keeps_the_old_file(self):
        old = self.conversation()["id"]
        self.ask("하나")
        self.assertIsNotNone(self.platform.client)
        status, fresh = self.call("POST", "/api/conversation/new")
        self.assertEqual((status, fresh["messages"]), (201, []))
        self.assertNotEqual(fresh["id"], old)
        self.assertIsNone(self.platform.client)               # 엔진의 기억에 앞의 대화가 남아 있어서 닫는다
        self.assertEqual(self.conversation()["id"], fresh["id"])
        self.assertTrue((self.root / "conversations" / f"{old}.json").is_file())   # 앞의 대화는 지우지 않는다
        self.wait_for(lambda e: e["type"] == "conversation" and e["id"] == fresh["id"])
        self.ask("둘")
        self.assertEqual(self.last_preamble()["history"], 0)
        self.assertNotIn("지금까지의 대화", self.last_preamble()["text"])

    def test_new_conversation_reuses_an_empty_one(self):
        first = self.call("POST", "/api/conversation/new")[1]["id"]
        self.assertEqual(self.call("POST", "/api/conversation/new")[1]["id"], first)
        self.assertEqual(len(list((self.root / "conversations").glob("*.json"))), 1)

    def test_state_has_the_live_turn_for_a_page_opened_midway(self):
        self.send("도구 써 줘")
        card = self.wait_for(lambda e: e["type"] == "permission")
        status, state = self.call("GET", "/api/state")
        self.assertEqual(state["state"], "busy")
        types = [e["type"] for e in state["live"]]
        self.assertIn("permission", types)
        self.assertNotIn("user", types)                    # 질문은 대화 기록에 이미 있다
        self.assertEqual(state["conversation"]["messages"][0]["text"], "도구 써 줘")
        self.assertEqual(state["last"], len(self.platform.log.events))
        self.call("POST", f"/api/permissions/{card['id']}", {"allow": True})
        self.wait_for(lambda e: e["type"] == "done")
        self.assertEqual(self.call("GET", "/api/state")[1]["live"], [])

    def test_busy_session_refuses_new_conversation_connect_and_prompt(self):
        self.send("도구 써 줘")
        card = self.wait_for(lambda e: e["type"] == "permission")
        self.assertEqual(self.call("POST", "/api/conversation/new")[0], 409)
        self.assertEqual(self.call("POST", "/api/connect", {"engine": engines.names()[1]})[0], 409)
        self.assertEqual(self.call("POST", "/api/prompt", {"text": "끼어들기"})[0], 409)
        self.call("POST", f"/api/permissions/{card['id']}", {"allow": True})
        self.wait_for(lambda e: e["type"] == "done")
        self.assertEqual(self.call("POST", "/api/conversation/new")[0], 201)

    # ---- 허락 ----

    def test_permission_card_is_answered_through_api(self):
        self.send("도구 써 줘")
        card = self.wait_for(lambda e: e["type"] == "permission")
        self.assertEqual(card["title"], "Running: date")
        self.assertEqual(self.call("POST", f"/api/permissions/{card['id']}", {"allow": True})[0], 200)
        self.wait_for(lambda e: e["type"] == "done")
        self.assertTrue(self.text_so_far().endswith("/ allow-once"))
        self.assertEqual(self.call("POST", f"/api/permissions/{card['id']}", {"allow": True})[0], 404)

    def test_rule_allows_without_card(self):
        self.write_custom("rules.py", "def decide(request):\n"
                                      "    return 'allow' if request.command == 'date' else 'ask'\n")
        self.assertTrue(self.ask("도구 써 줘").endswith("/ allow-once"))
        rule = self.wait_for(lambda e: e["type"] == "rule")
        self.assertEqual((rule["allow"], rule["detail"]), (True, "date"))
        self.assertFalse([e for e in self.platform.log.events if e["type"] == "permission"])

    def test_broken_rule_falls_back_to_card(self):
        self.write_custom("rules.py", "def decide(request):\n    return 1 / 0\n")
        self.send("도구 써 줘")
        card = self.wait_for(lambda e: e["type"] == "permission")
        self.wait_for(lambda e: e["type"] == "rule_error")
        self.call("POST", f"/api/permissions/{card['id']}", {"allow": False})
        self.wait_for(lambda e: e["type"] == "done")

    def test_refusal_on_codex_style_engine_still_ends_as_done(self):
        with mock.patch.dict(os.environ, {"FAKE_STYLE": "codex"}):
            self.connect("codex")
            self.send("도구 써 줘")
            card = self.wait_for(lambda e: e["type"] == "permission")
            self.call("POST", f"/api/permissions/{card['id']}", {"allow": False})
            done = self.wait_for(lambda e: e["type"] == "done")
        notice = self.wait_for(lambda e: e["type"] == "notice")
        self.assertIn("이어서 하게 했다", notice["text"])
        self.assertEqual((done["stop"], done["stopLabel"], done["refused"]), ("done", "끝", 1))

    # ---- 엔진 연결과 바꾸기 ----

    def test_connect_opens_the_session_before_the_first_question(self):
        self.connect("claude")
        self.assertEqual((self.platform.state, self.platform.engine, ENGINES_USED), ("ready", "claude", ["claude"]))
        conversation = self.conversation()
        self.assertEqual(conversation["engine"], "claude")
        self.assertEqual([m["role"] for m in conversation["messages"]], ["note", "preamble"])
        self.assertEqual(self.ask("안내"), "받음: 있음")    # 안내는 연결 뒤 첫 질문에 붙는다
        self.assertEqual(ENGINES_USED, ["claude"])

    def test_unknown_engine_is_refused(self):
        self.assertEqual(self.call("POST", "/api/connect", {"engine": "없는엔진"})[0], 400)
        self.assertEqual(self.call("POST", "/api/connect", {})[0], 400)

    def test_failed_connect_is_reported_and_can_be_tried_again(self):
        def broken(engine, workspace, **callbacks):
            raise dashboard.EngineError("엔진을 찾지 못했습니다")

        with mock.patch.object(self.platform, "client_factory", broken):
            self.call("POST", "/api/connect", {"engine": "claude"})
            failed = self.wait_for(lambda e: e["type"] == "status" and e["state"] == "error")
        self.assertIn("찾지 못했습니다", failed["message"])
        self.assertTrue(self.conversation()["messages"][-1]["error"])
        self.connect("claude")
        self.assertEqual(self.ask("안녕"), "받음: 안녕")

    def test_conversation_continues_on_another_engine(self):
        first, second = engines.names()[:2]
        self.assertEqual(self.ask("발표안내.md를 기억해"), "받음: 발표안내.md를 기억해")
        start = self.connect(second)
        note = self.wait_for(lambda e: e["type"] == "note", after=start)
        self.assertIn(f"엔진을 {first}에서 {second}로 바꿨다", note["text"])
        preamble = self.last_preamble()
        self.assertEqual(preamble["history"], 2)
        self.assertIn("[사용자] 발표안내.md를 기억해", preamble["text"])
        self.assertIn("[에이전트] 받음: 발표안내.md를 기억해", preamble["text"])
        self.assertNotIn("바꿨다", preamble["text"])         # 플랫폼의 알림은 앞의 대화에 넣지 않는다
        self.assertEqual(self.ask("이어서"), "받음: 이어서")
        self.assertEqual(ENGINES_USED, [first, second])

    def test_same_preamble_on_any_engine(self):
        texts = []
        for engine in engines.names():
            self.call("POST", "/api/conversation/new")         # 앞의 대화가 없을 때 안내는 엔진과 상관없이 같다
            self.connect(engine)
            self.assertEqual(self.ask("안내"), "받음: 있음")
            texts.append(self.last_preamble()["text"])
        self.assertEqual(len(set(texts)), 1)
        for name in engines.names():
            self.assertNotIn(name, texts[0])

    # ---- 로그인 ----

    def login_events(self, agent):
        return [e for e in self.platform.log.events if e["type"] == "login" and e["engine"] == agent]

    def test_code_login_shows_url_and_takes_code(self):
        status, _ = self.call("POST", "/api/login/claude")
        self.assertEqual(status, 202)
        waiting = self.wait_for(lambda e: e["type"] == "login" and e["state"] == "waiting")
        self.assertEqual(waiting["url"], "https://example.com/oauth/authorize?code=true&state=AbCd-EfGhI")
        self.assertIsNone(waiting["userCode"])
        status, _ = self.call("POST", "/api/login/claude/code", {"code": "good"})
        self.assertEqual(status, 202)
        self.wait_for(lambda e: e["type"] == "login" and e["state"] == "done")

    def test_wrong_code_fails_with_message(self):
        self.call("POST", "/api/login/claude")
        self.wait_for(lambda e: e["type"] == "login" and e["state"] == "waiting")
        self.call("POST", "/api/login/claude/code", {"code": "bad"})
        failed = self.wait_for(lambda e: e["type"] == "login" and e["state"] == "failed")
        self.assertIn("400", failed["message"])

    def test_device_login_shows_code(self):
        self.call("POST", "/api/login/codex")
        self.wait_for(lambda e: e["type"] == "login" and e["state"] == "done")
        codes = [e.get("userCode") for e in self.login_events("codex") if e["state"] == "waiting"]
        self.assertIn("ABCD-EFGHI", codes)

    def test_login_can_be_cancelled(self):
        self.call("POST", "/api/login/claude")
        self.wait_for(lambda e: e["type"] == "login" and e["state"] == "waiting")
        status, _ = self.call("DELETE", "/api/login/claude")
        self.assertEqual(status, 200)
        self.wait_for(lambda e: e["type"] == "login" and e["state"] == "cancelled")
        status, _ = self.call("POST", "/api/login/claude/code", {"code": "good"})
        self.assertEqual(status, 404)

    def test_cancel_reads_as_cancelled_even_when_the_exit_code_is_1(self):
        # Windows에서 강제로 끝낸 프로세스의 종료 코드는 음수가 아니라 1이다. 그 모양을 흉내 낸다.
        self.call("POST", "/api/login/claude")
        self.wait_for(lambda e: e["type"] == "login" and e["state"] == "waiting")
        process = self.platform.logins.running["claude"]
        process.kill = lambda: (process.stdin.write("끝\n"), process.stdin.flush())   # 가짜 로그인이 1로 끝난다
        self.assertEqual(self.call("DELETE", "/api/login/claude")[0], 200)
        final = self.wait_for(lambda e: e["type"] == "login" and e["state"] in ("cancelled", "failed"))
        self.assertEqual(final["state"], "cancelled")

    def test_logout_output_that_is_not_utf8_still_answers(self):
        status, _ = self.call("POST", "/api/logout/claude")
        self.assertEqual(status, 200)
        self.wait_for(lambda e: e["type"] == "login" and e["state"] == "logged_out")

    def test_login_is_refused_when_already_logged_in(self):
        # codex login은 시작하자마자 있던 로그인을 지운다. 취소하면 로그아웃된 상태로 남는다.
        self.logged_in.add("codex")
        status, body = self.call("POST", "/api/login/codex")
        self.assertEqual(status, 409)
        self.assertIn("로그아웃", body["error"])
        self.assertFalse(self.login_events("codex"))

    def test_terminal_login_and_logout_are_refused(self):
        status, body = self.call("POST", "/api/login/kiro")
        self.assertEqual(status, 400)
        self.assertIn("kiro-cli login", body["error"])
        status, _ = self.call("POST", "/api/logout/kiro")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
