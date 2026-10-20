"""가짜 에이전트로 AcpClient를 확인한다. 실제 에이전트를 부르지 않으므로 사용량이 없다.

실행: python -m unittest discover tests
"""

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import acp_client  # noqa: E402
from acp_client import AcpClient, AcpError  # noqa: E402

FAKE = [sys.executable, str(pathlib.Path(__file__).parent / "fake_agent.py")]
WORKSPACE = pathlib.Path(__file__).parent
KIRO_LIKE = {"home_env": "KIRO_HOME", "expect_mode": "starter"}
CLAUDE_LIKE = {"home_env": "CLAUDE_CONFIG_DIR", "safe_mode": "default"}


class AcpClientTest(unittest.TestCase):
    def make(self, config=KIRO_LIKE, mode="starter", env=None, **callbacks):
        client = AcpClient(WORKSPACE, "fake", command=FAKE + [mode], config=config,
                           env=env if env is not None else dict(os.environ), **callbacks)
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
                           on_permission=lambda call: asked.append(call["title"]) or True)
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
        client = self.make(on_tool=lambda update: tools.append(update["title"]))
        client.start()
        client.prompt("도구 써 줘")
        self.assertEqual(tools, ["Running: date"])

    def test_usage_is_collected(self):
        client = self.make()
        client.start()
        client.prompt("안녕")
        self.assertAlmostEqual(client.credits, 0.75)
        self.assertEqual(client.context_tokens, 1234)

    def test_wrong_agent_raises(self):
        client = self.make(mode="kiro_default")
        with self.assertRaises(AcpError):
            client.start()

    def test_safe_mode_is_set_after_session_opens(self):
        chunks = []
        client = self.make(config=CLAUDE_LIKE, mode="auto", on_text=chunks.append)
        client.start()
        client.prompt("모드")
        self.assertEqual("".join(chunks), "받음: default")

    def test_session_meta_is_sent_with_new_session(self):
        chunks = []
        config = dict(CLAUDE_LIKE, session_meta={"claudeCode": {"options": {"settingSources": []}}})
        client = self.make(config=config, mode="auto", on_text=chunks.append)
        client.start()
        client.prompt("메타")
        self.assertEqual("".join(chunks), '받음: {"claudeCode": {"options": {"settingSources": []}}}')

    def test_no_meta_without_session_meta(self):
        chunks = []
        client = self.make(on_text=chunks.append)
        client.start()
        client.prompt("메타")
        self.assertEqual("".join(chunks), "받음: null")

    def test_sandbox_env_points_home_inside_repo(self):
        with tempfile.TemporaryDirectory() as root:
            original = acp_client.ROOT
            acp_client.ROOT = pathlib.Path(root)
            try:
                env = acp_client.sandbox_env("claude", {"home_env": "CLAUDE_CONFIG_DIR",
                                                        "env": {"EXTRA": "1"}})
            finally:
                acp_client.ROOT = original
            self.assertEqual(env["CLAUDE_CONFIG_DIR"], str(pathlib.Path(root) / ".homes" / "claude"))
            self.assertTrue((pathlib.Path(root) / ".homes" / "claude").is_dir())
            self.assertEqual(env["EXTRA"], "1")

    def test_unknown_agent_name_raises(self):
        with self.assertRaises(AcpError):
            acp_client.load_agent("없는에이전트")

    def test_agents_file_has_three_agents_with_homes(self):
        for name in ("kiro", "claude", "codex"):
            agent = acp_client.load_agent(name)
            self.assertIn("home_env", agent)
            self.assertIn("command", agent)
        self.assertEqual(acp_client.load_agent("claude")["safe_mode"], "default")
        self.assertEqual(acp_client.load_agent("codex")["safe_mode"], "read-only")
        self.assertEqual(acp_client.load_agent("claude")["session_meta"],
                         {"claudeCode": {"options": {"settingSources": []}}})


if __name__ == "__main__":
    unittest.main()
