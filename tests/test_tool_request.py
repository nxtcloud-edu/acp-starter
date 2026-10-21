"""엔진마다 다른 도구 요청을 같은 꼴(ToolRequest)로 맞추는지 확인한다.

아래 모양은 2026-10-21에 실제 엔진(Kiro CLI 2.29.1, claude-agent-acp 0.94.0, codex-acp 2.2.2)이
보낸 요청에서 가져왔다(내용은 줄였다). 엔진이 바뀌어도 허락 규칙이 같은 값을 보게 하는 것이 목적이다.

실행: python -m unittest discover tests
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from engines.claude import ClaudeEngine  # noqa: E402
from engines.codex import CodexEngine  # noqa: E402
from engines.kiro import KiroEngine  # noqa: E402

WS = "/Users/me/acp-starter/workspace"
ADAPTERS = {"kiro": KiroEngine(WS), "claude": ClaudeEngine(WS), "codex": CodexEngine(WS)}


def tool_request(tool_call, engine, workspace, known_kind=None):
    """엔진의 어댑터가 도구 요청을 플랫폼 형식으로 바꾼 결과."""
    return ADAPTERS[engine].tool_request(tool_call, known_kind)

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
# Codex는 여러 줄 명령을 감쌀 때 줄바꿈을 그대로 둔다(2026-10-21 실제 요청에서 줄임).
CODEX_MULTILINE = {"toolCallId": "x2", "title": "Run command", "kind": "execute",
                   "rawInput": {"command": '"python3 skills/x.py --out outbox/a.json <<\'JSON\'\n'
                                           '{\n  \\"메모 날짜\\": null\n}\nJSON"', "cwd": WS}}


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

    def test_codex_multiline_command_is_unquoted(self):
        request = tool_request(CODEX_MULTILINE, "codex", WS)
        self.assertEqual(request.command,
                         "python3 skills/x.py --out outbox/a.json <<'JSON'\n{\n  \"메모 날짜\": null\n}\nJSON")
        self.assertTrue(request.command.startswith("python3 skills/"))

    def test_internet_has_a_url_whatever_the_tool(self):
        kiro_curl = {"toolCallId": "k4", "title": "Running: curl -s https://example.com",
                     "rawInput": {"command": "curl -s https://example.com"}}
        codex_curl = {"toolCallId": "x3", "title": "Run command", "kind": "execute",
                      "rawInput": {"command": '"curl -L --fail --max-time 20 https://example.com"', "cwd": WS}}
        cases = [tool_request(KIRO_FETCH, "kiro", WS, known_kind="read"), tool_request(CLAUDE_FETCH, "claude", WS),
                 tool_request(kiro_curl, "kiro", WS, known_kind="execute"), tool_request(codex_curl, "codex", WS)]
        for request in cases:
            with self.subTest(engine=request.engine, kind=request.kind):
                self.assertEqual(request.url, "https://example.com")
        self.assertEqual(tool_request(CLAUDE_SHELL, "claude", WS).url, "")

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
        self.assertEqual(tool_request({"kind": "execute", "rawInput": {"command": ["ls", "-a"]}}, "kiro", WS).command,
                         "ls -a")


if __name__ == "__main__":
    unittest.main()
