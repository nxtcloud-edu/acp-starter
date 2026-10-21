"""엔진마다 다른 도구 요청을 같은 꼴(ToolRequest)로 맞추는지 확인한다.

아래 모양은 2026-10-21에 실제 엔진(Kiro CLI 2.29.1, claude-agent-acp 0.94.0, codex-acp 2.2.2)이
보낸 요청에서 가져왔다(내용은 줄였다). 엔진이 바뀌어도 허락 규칙이 같은 값을 보게 하는 것이 목적이다.

실행: python -m unittest discover tests
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from acp_client import tool_request  # noqa: E402

WS = "/Users/me/acp-starter/workspace"

KIRO_SHELL = {"toolCallId": "k1", "title": "Running: python3 skills/x.py --out outbox/a.json", "kind": None,
              "rawInput": {"__tool_use_purpose": "저장", "command": "python3 skills/x.py --out outbox/a.json",
                           "working_dir": WS}}
KIRO_WRITE = {"toolCallId": "k2", "title": "Creating a.txt", "kind": None,
              "rawInput": {"command": "create", "path": f"{WS}/outbox/a.txt", "content": "시험"}}
KIRO_FETCH = {"toolCallId": "k3", "title": "Fetching web content", "kind": None,
              "rawInput": {"url": "https://example.com", "mode": "truncated"}}
CLAUDE_SHELL = {"toolCallId": "c1", "title": "python3 skills/x.py --out outbox/a.json", "kind": "execute",
                "rawInput": {"command": "python3 skills/x.py --out outbox/a.json"}}
CLAUDE_WRITE = {"toolCallId": "c2", "title": "Write outbox/a.txt", "kind": "edit",
                "rawInput": {"file_path": f"{WS}/outbox/a.txt", "content": "시험"},
                "locations": [{"path": f"{WS}/outbox/a.txt"}]}
CLAUDE_FETCH = {"toolCallId": "c3", "title": "Fetch https://example.com", "kind": "fetch",
                "rawInput": {"url": "https://example.com", "prompt": "요약"}}
CODEX_SHELL = {"toolCallId": "x1", "title": "Run command", "kind": "execute",
               "rawInput": {"command": '"python3 skills/x.py --out outbox/a.json"', "cwd": WS}}


class ToolRequestTest(unittest.TestCase):
    def test_same_command_looks_the_same_from_every_engine(self):
        requests = [tool_request(KIRO_SHELL, "kiro", WS, known_kind="execute"),
                    tool_request(CLAUDE_SHELL, "claude", WS),
                    tool_request(CODEX_SHELL, "codex", WS)]
        for request in requests:
            with self.subTest(engine=request.engine):
                self.assertEqual(request.kind, "execute")
                self.assertEqual(request.label, "명령 실행")
                self.assertEqual(request.command, "python3 skills/x.py --out outbox/a.json")

    def test_same_write_looks_the_same(self):
        for request in [tool_request(KIRO_WRITE, "kiro", WS, known_kind="edit"),
                        tool_request(CLAUDE_WRITE, "claude", WS)]:
            with self.subTest(engine=request.engine):
                self.assertEqual((request.kind, request.path, request.command), ("edit", "outbox/a.txt", ""))

    def test_same_fetch_looks_the_same(self):
        # Kiro는 웹 가져오기를 kind "read"로 알린다.
        for request in [tool_request(KIRO_FETCH, "kiro", WS, known_kind="read"),
                        tool_request(CLAUDE_FETCH, "claude", WS)]:
            with self.subTest(engine=request.engine):
                self.assertEqual((request.kind, request.url), ("fetch", "https://example.com"))
                self.assertEqual(request.label, "인터넷")

    def test_kind_is_guessed_when_missing(self):
        self.assertEqual(tool_request(KIRO_SHELL, "kiro", WS).kind, "execute")
        self.assertEqual(tool_request(KIRO_WRITE, "kiro", WS).kind, "edit")
        self.assertEqual(tool_request({"title": "?"}, "kiro", WS).kind, "other")

    def test_kiro_write_subcommand_is_not_a_command(self):
        self.assertEqual(tool_request(KIRO_WRITE, "kiro", WS).command, "")

    def test_path_outside_workspace_stays_absolute(self):
        request = tool_request({"kind": "edit", "rawInput": {"file_path": "/etc/hosts", "content": "x"}}, "claude", WS)
        self.assertEqual(request.path, "/etc/hosts")

    def test_detail_falls_back_in_order(self):
        self.assertEqual(tool_request(CLAUDE_WRITE, "claude", WS).detail, "outbox/a.txt")
        self.assertEqual(tool_request({"title": "Terminal", "kind": "execute", "rawInput": {}}, "claude", WS).detail,
                         "Terminal")
        self.assertEqual(tool_request({"kind": "execute", "rawInput": {"command": ["ls", "-a"]}}, "x", WS).command,
                         "ls -a")


if __name__ == "__main__":
    unittest.main()
