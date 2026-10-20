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
CONFIG = {"home_env": "KIRO_HOME", "expect_mode": "starter"}


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
                                           status_checker=lambda name: True)
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
