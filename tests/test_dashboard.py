"""가짜 에이전트로 대시보드의 API를 확인한다. 실제 에이전트를 부르지 않는다.

실행: python -m unittest discover tests
"""

import datetime
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import dashboard  # noqa: E402
import runner  # noqa: E402
from acp_client import AcpClient  # noqa: E402

FAKE = [sys.executable, str(pathlib.Path(__file__).parent / "fake_agent.py"), "starter"]
FAKE_LOGIN = str(pathlib.Path(__file__).parent / "fake_login.py")
CONFIG = {"home_env": "KIRO_HOME", "expect_mode": "starter"}
LOGIN_AGENTS = {
    "kiro": {"login": ["kiro-cli", "login"], "login_mode": "terminal"},
    "claude": {"login": [sys.executable, FAKE_LOGIN, "code"], "login_mode": "code"},
    "codex": {"login": [sys.executable, FAKE_LOGIN, "device"], "login_mode": "device"},
}


def fake_login_agent(name):
    if name not in LOGIN_AGENTS:
        raise dashboard.AcpError("없는 에이전트")
    return LOGIN_AGENTS[name]


def fake_factory(workspace, agent, **callbacks):
    return AcpClient(workspace, agent, command=FAKE, config=CONFIG, env=dict(os.environ), **callbacks)


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        (self.root / "workspace").mkdir()
        (self.root / "tasks").mkdir()
        (self.root / "tasks" / "아침_브리핑.md").write_text(
            "---\nagent: kiro\ntime: 23:59\n---\n오늘 할 일을 정리해 줘\n", encoding="utf-8")
        self.platform = dashboard.Platform(self.root, client_factory=fake_factory,
                                           status_checker=lambda name: True,
                                           install_checker=lambda agent: True)
        self.logged_in = set()
        self.platform.logins = dashboard.Logins(self.platform.log, load_agent=fake_login_agent,
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

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def wait_for(self, check, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            events = self.platform.log.events
            found = [e for e in events if check(e)]
            if found:
                return found[0]
            time.sleep(0.05)
        self.fail("기다린 사건이 오지 않았습니다.")

    def connect(self):
        status, _ = self.call("POST", "/api/session", {"agent": "kiro"})
        self.assertEqual(status, 202)
        self.wait_for(lambda e: e["type"] == "status" and e["state"] == "ready")

    def text_so_far(self):
        return "".join(e["text"] for e in self.platform.log.events if e["type"] == "text")

    def test_chat_streams_answer_through_events(self):
        self.connect()
        status, _ = self.call("POST", "/api/prompt", {"text": "안녕"})
        self.assertEqual(status, 202)
        self.wait_for(lambda e: e["type"] == "done")
        self.assertEqual(self.text_so_far(), "받음: 안녕")
        status, body = self.call("GET", "/api/events?after=0")
        self.assertEqual(status, 200)
        self.assertEqual([e["type"] for e in body["events"]][:2], ["status", "status"])
        self.assertEqual(body["last"], body["events"][-1]["seq"])

    def test_permission_card_is_answered_through_api(self):
        self.connect()
        self.call("POST", "/api/prompt", {"text": "도구 써 줘"})
        card = self.wait_for(lambda e: e["type"] == "permission")
        self.assertEqual(card["title"], "Running: date")
        status, _ = self.call("POST", f"/api/permissions/{card['id']}", {"allow": True})
        self.assertEqual(status, 200)
        self.wait_for(lambda e: e["type"] == "done")
        self.assertTrue(self.text_so_far().endswith("/ allow-once"))

    def test_prompt_before_connect_is_refused(self):
        status, body = self.call("POST", "/api/prompt", {"text": "안녕"})
        self.assertEqual(status, 409)
        self.assertIn("error", body)

    def test_unknown_agent_is_refused(self):
        status, _ = self.call("POST", "/api/session", {"agent": "없는에이전트"})
        self.assertEqual(status, 400)

    def test_task_runs_and_result_appears_in_outbox(self):
        status, body = self.call("GET", "/api/tasks")
        self.assertEqual(body["tasks"][0]["name"], "아침_브리핑")
        self.assertIsNone(body["tasks"][0]["lastRun"])
        self.assertEqual(body["tasks"][0]["time"], "23:59")
        status, _ = self.call("POST", "/api/tasks/%EC%95%84%EC%B9%A8_%EB%B8%8C%EB%A6%AC%ED%95%91/run")
        self.assertEqual(status, 202)
        done = self.wait_for(lambda e: e["type"] == "task" and e["state"] == "done")
        status, body = self.call("GET", "/api/outbox")
        self.assertEqual(body["files"][0]["name"], done["file"])
        status, body = self.call("GET", "/api/tasks")
        self.assertIsNotNone(body["tasks"][0]["lastRun"])
        status, body = self.call("GET", "/api/outbox/" + urllib.request.quote(done["file"]))
        self.assertIn("받음: 오늘 할 일을 정리해 줘", body["text"])

    def test_outbox_rejects_paths_outside(self):
        status, _ = self.call("GET", "/api/outbox/..%2F..%2Fagents.json")
        self.assertEqual(status, 404)

    def test_agents_lists_login_state(self):
        status, body = self.call("GET", "/api/agents")
        self.assertEqual(status, 200)
        self.assertEqual({a["name"] for a in body["agents"]}, {"kiro", "claude", "codex"})
        self.assertTrue(all(a["loggedIn"] is True for a in body["agents"]))

    def test_tick_runs_due_task_once_a_day(self):
        now = datetime.datetime.combine(datetime.date.today(), datetime.time(23, 59))
        self.platform.last_run.pop("아침_브리핑", None)
        self.platform.tick(now)
        self.wait_for(lambda e: e["type"] == "task" and e["state"] == "done")
        self.platform.tick(now)
        runs = [e for e in self.platform.log.events if e["type"] == "task" and e["state"] == "running"]
        self.assertEqual(len(runs), 1)


    # ---- 플랫폼 안내, 규칙, 보내기 ----

    def write_custom(self, name, text):
        (self.root / "custom").mkdir(exist_ok=True)
        (self.root / "custom" / name).write_text(text, encoding="utf-8")

    def ask(self, text):
        start = len(self.platform.log.events)
        self.call("POST", "/api/prompt", {"text": text})
        self.wait_for(lambda e: e["type"] == "done" and e["seq"] > start)
        return "".join(e["text"] for e in self.platform.log.events[start:] if e["type"] == "text")

    def test_preamble_goes_with_first_prompt_only(self):
        self.write_custom("업무.md", "- 맡는 업무: 마감 정리\n")
        self.connect()
        note = self.wait_for(lambda e: e["type"] == "preamble")
        self.assertIn("마감 정리", note["text"])
        self.assertEqual(self.ask("안내"), "받음: 있음")
        self.assertEqual(self.ask("안내"), "받음: 없음")

    def test_rule_allows_without_card(self):
        self.write_custom("rules.py", "def decide(agent, tool_call):\n"
                                      "    return 'allow' if tool_call['rawInput']['command'] == 'date' else 'ask'\n")
        self.connect()
        self.assertTrue(self.ask("도구 써 줘").endswith("/ allow-once"))
        rule = self.wait_for(lambda e: e["type"] == "rule")
        self.assertEqual((rule["allow"], rule["detail"]), (True, "date"))
        self.assertFalse([e for e in self.platform.log.events if e["type"] == "permission"])

    def test_broken_rule_falls_back_to_card(self):
        self.write_custom("rules.py", "def decide(agent, tool_call):\n    return 1 / 0\n")
        self.connect()
        self.call("POST", "/api/prompt", {"text": "도구 써 줘"})
        card = self.wait_for(lambda e: e["type"] == "permission")
        self.wait_for(lambda e: e["type"] == "rule_error")
        self.call("POST", f"/api/permissions/{card['id']}", {"allow": False})
        self.wait_for(lambda e: e["type"] == "done")

    def test_unattended_task_refuses_ask_and_delivers(self):
        self.write_custom("deliver.py", "def deliver(task, path, text):\n"
                                        "    path.with_suffix('.sent').write_text(task + '|' + text, encoding='utf-8')\n")
        result = runner.run_task("kiro", "도구 써 줘", name="일", workspace=self.root / "workspace",
                                 client_factory=fake_factory, custom=self.root / "custom")
        self.assertIsNone(result.delivery_error)
        text = result.path.read_text(encoding="utf-8")
        self.assertIn("- 거절한 도구: Running: date", text)
        self.assertIn("/ reject", text)
        self.assertTrue(result.path.with_suffix(".sent").read_text(encoding="utf-8").startswith("일|받음: 도구 써 줘"))

    def test_delivery_error_is_reported(self):
        self.write_custom("deliver.py", "def deliver(task, path, text):\n    raise RuntimeError('웹훅 실패')\n")
        self.call("POST", "/api/tasks/%EC%95%84%EC%B9%A8_%EB%B8%8C%EB%A6%AC%ED%95%91/run")
        done = self.wait_for(lambda e: e["type"] == "task" and e["state"] == "done")
        self.assertIn("웹훅 실패", done["deliveryError"])

    # ---- 이름과 색, 스킬, 결과함 ----

    def test_brand_and_skills(self):
        self.write_custom("brand.json", '{"name": "마감지기", "accent": "#123456"}')
        status, body = self.call("GET", "/api/brand")
        self.assertEqual((status, body["name"]), (200, "마감지기"))
        skill = self.root / "workspace" / "skills" / "deadline"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: deadline\ndescription: 마감 표\n---\n", encoding="utf-8")
        status, body = self.call("GET", "/api/skills")
        self.assertEqual(body["skills"][0]["name"], "deadline")

    def test_outbox_lists_html_and_serves_it_sandboxed(self):
        outbox = self.root / "workspace" / "outbox"
        outbox.mkdir()
        (outbox / "리포트.html").write_text("<h1>보고</h1>", encoding="utf-8")
        (outbox / "메모.json").write_text('{"a": 1}', encoding="utf-8")
        (outbox / "비밀.sh").write_text("echo", encoding="utf-8")
        status, body = self.call("GET", "/api/outbox")
        self.assertEqual({f["name"] for f in body["files"]}, {"리포트.html", "메모.json"})
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/outbox/"
                                    + urllib.request.quote("리포트.html")) as response:
            self.assertEqual(response.headers["Content-Security-Policy"], "sandbox")
            self.assertIn("text/html", response.headers["Content-Type"])
            self.assertEqual(response.read().decode(), "<h1>보고</h1>")
        status, _ = self.call("GET", "/outbox/" + urllib.request.quote("비밀.sh"))
        self.assertEqual(status, 404)

    # ---- 로그인 ----

    def login_events(self, agent):
        return [e for e in self.platform.log.events if e["type"] == "login" and e["agent"] == agent]

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


class TaskFileTest(unittest.TestCase):
    def test_load_tasks_reads_header_and_body(self):
        folder = pathlib.Path(tempfile.mkdtemp())
        (folder / "a.md").write_text("---\nagent: codex\ntime: 07:30\n---\n할 일\n", encoding="utf-8")
        (folder / "b.md").write_text("머리 없는 일\n", encoding="utf-8")
        (folder / "c.md").write_text("---\ntime: 7시\n---\n시각이 틀린 일\n", encoding="utf-8")
        tasks = {t["name"]: t for t in runner.load_tasks(folder)}
        self.assertEqual(tasks["a"], {"name": "a", "agent": "codex", "time": "07:30", "prompt": "할 일"})
        self.assertEqual(tasks["b"]["agent"], "kiro")
        self.assertEqual(tasks["b"]["time"], "")
        self.assertEqual(tasks["c"]["time"], "")

    def test_is_due(self):
        task = {"time": "07:30"}
        today = datetime.date(2026, 10, 21)
        at = lambda h, m: datetime.datetime(2026, 10, 21, h, m)
        self.assertFalse(runner.is_due(task, at(7, 29), None))
        self.assertTrue(runner.is_due(task, at(7, 30), None))
        self.assertFalse(runner.is_due(task, at(7, 31), today))
        self.assertFalse(runner.is_due({"time": ""}, at(7, 30), None))


if __name__ == "__main__":
    unittest.main()
