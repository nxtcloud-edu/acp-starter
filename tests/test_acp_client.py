"""가짜 에이전트로 AcpClient를 확인한다. 실제 Kiro를 부르지 않으므로 크레딧을 쓰지 않는다.

실행: python -m unittest discover tests
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from acp_client import AcpClient, AcpError  # noqa: E402

FAKE = [sys.executable, str(pathlib.Path(__file__).parent / "fake_agent.py")]
WORKSPACE = pathlib.Path(__file__).parent


class AcpClientTest(unittest.TestCase):
    def make(self, agent="starter", **callbacks):
        client = AcpClient(WORKSPACE, agent, command=FAKE, **callbacks)
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
        self.assertTrue("".join(chunks).endswith("/ allow_once"))

    def test_permission_rejected_without_callback(self):
        chunks = []
        client = self.make(on_text=chunks.append)
        client.start()
        client.prompt("도구 써 줘")
        self.assertTrue("".join(chunks).endswith("/ reject_once"))

    def test_tool_updates_reach_callback(self):
        tools = []
        client = self.make(on_tool=lambda update: tools.append(update["title"]))
        client.start()
        client.prompt("도구 써 줘")
        self.assertEqual(tools, ["Running: date"])

    def test_credits_are_summed(self):
        client = self.make()
        client.start()
        client.prompt("안녕")
        self.assertAlmostEqual(client.credits, 0.75)

    def test_wrong_agent_raises(self):
        client = self.make(agent="missing")
        with self.assertRaises(AcpError):
            client.start()


if __name__ == "__main__":
    unittest.main()
