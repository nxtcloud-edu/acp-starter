"""가짜 엔진으로 엔진 층(engines/)을 확인한다. 실제 엔진을 부르지 않으므로 사용량이 없다.

실행: python -m unittest discover tests
"""

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import engines  # noqa: E402
from engines import EngineError  # noqa: E402
from engines import base  # noqa: E402
from engines.claude import ClaudeEngine  # noqa: E402
from engines.codex import CodexEngine  # noqa: E402
from engines.kiro import KiroEngine  # noqa: E402

FAKE = [sys.executable, str(pathlib.Path(__file__).parent / "fake_agent.py")]
WORKSPACE = pathlib.Path(__file__).parent


class EngineSessionTest(unittest.TestCase):
    def make(self, engine=KiroEngine, mode="engine", **callbacks):
        client = engine(WORKSPACE, command=FAKE + [mode], env=dict(os.environ), **callbacks)
        self.addCleanup(client.close)
        return client

    def test_prompt_streams_text_and_ends_turn(self):
        chunks = []
        client = self.make(on_text=chunks.append)
        client.start()
        self.assertEqual(client.prompt("안녕"), "end_turn")
        self.assertEqual("".join(chunks), "받음: 안녕")

    def test_permission_allowed_by_callback(self):
        chunks, asked = [], []
        client = self.make(on_text=chunks.append,
                           on_permission=lambda request: asked.append(request.title) or True)
        client.start()
        client.prompt("도구 써 줘")
        self.assertEqual(asked, ["Running: date"])
        self.assertTrue("".join(chunks).endswith("/ allow-once"))

    def test_permission_rejected_without_callback(self):
        chunks = []
        client = self.make(on_text=chunks.append)
        client.start()
        client.prompt("도구 써 줘")
        self.assertTrue("".join(chunks).endswith("/ reject"))

    def test_tool_updates_reach_callback(self):
        tools = []
        client = self.make(on_tool=lambda request: tools.append((request.kind, request.title)))
        client.start()
        client.prompt("도구 써 줘")
        self.assertEqual(tools, [("execute", "Running: date")])

    def test_kiro_counts_credits_and_others_ignore_them(self):
        client = self.make()
        client.start()
        client.prompt("안녕")
        self.assertAlmostEqual(client.credits, 0.75)
        self.assertEqual(client.context_tokens, 1234)
        other = self.make(engine=ClaudeEngine, mode="auto")
        other.start()
        other.prompt("안녕")
        self.assertEqual(other.credits, 0)   # 크레딧 알림은 Kiro만의 확장이다

    def test_wrong_mode_raises(self):
        client = self.make(mode="kiro_default")
        with self.assertRaises(EngineError):
            client.start()

    def test_safe_mode_is_set_after_session_opens(self):
        chunks = []
        client = self.make(engine=ClaudeEngine, mode="auto", on_text=chunks.append)
        client.start()
        client.prompt("모드")
        self.assertEqual("".join(chunks), "받음: default")

    def test_claude_sends_session_meta_and_kiro_does_not(self):
        chunks = []
        client = self.make(engine=ClaudeEngine, mode="auto", on_text=chunks.append)
        client.start()
        client.prompt("메타")
        self.assertEqual("".join(chunks), '받음: {"claudeCode": {"options": {"settingSources": []}}}')
        chunks.clear()
        client = self.make(on_text=chunks.append)
        client.start()
        client.prompt("메타")
        self.assertEqual("".join(chunks), "받음: null")


class EngineHomeTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        patcher = mock.patch.object(base, "HOMES", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sandbox_env_points_home_inside_repo(self):
        env = ClaudeEngine.sandbox_env()
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], str(self.root / "claude"))
        self.assertTrue((self.root / "claude").is_dir())
        self.assertEqual(CodexEngine.sandbox_env()["INITIAL_AGENT_MODE"], "read-only")

    def test_kiro_home_gets_engine_spec_and_keeps_other_settings(self):
        settings = self.root / "kiro" / "settings" / "cli.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"chat.defaultModel": "x"}', encoding="utf-8")
        KiroEngine.sandbox_env()
        spec = json.loads((self.root / "kiro" / "agents" / "engine.json").read_text(encoding="utf-8"))
        self.assertEqual((spec["name"], spec["allowedTools"]), ("engine", ["read"]))
        self.assertNotIn("prompt", spec)
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(data, {"chat.defaultModel": "x", "chat.disableInheritingDefaultResources": True})

    def test_codex_home_gets_config(self):
        CodexEngine.sandbox_env()
        self.assertIn("project_doc_max_bytes = 0", (self.root / "codex" / "config.toml").read_text(encoding="utf-8"))


class EngineRegistryTest(unittest.TestCase):
    def test_three_engines_in_order(self):
        self.assertEqual(engines.names(), ["kiro", "claude", "codex"])
        self.assertIs(engines.get("codex"), CodexEngine)
        self.assertIsInstance(engines.make("claude", WORKSPACE), ClaudeEngine)
        with self.assertRaises(EngineError):
            engines.get("없는엔진")

    def test_login_status_is_read_per_engine(self):
        self.assertTrue(KiroEngine.logged_in(0, "Logged in with IAM Identity Center"))
        self.assertFalse(KiroEngine.logged_in(1, ""))
        self.assertFalse(ClaudeEngine.logged_in(0, '{"loggedIn": false}'))
        self.assertTrue(ClaudeEngine.logged_in(0, '{"loggedIn": true}'))
        self.assertFalse(CodexEngine.logged_in(0, "Not logged in"))
        self.assertTrue(CodexEngine.logged_in(0, "Logged in using ChatGPT"))


if __name__ == "__main__":
    unittest.main()
