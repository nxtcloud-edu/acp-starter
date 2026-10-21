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
        result = client.send("안녕")
        self.assertEqual((result.stop, result.stop_label, result.text), ("done", "끝", "받음: 안녕"))
        self.assertEqual("".join(chunks), "받음: 안녕")

    def test_permission_allowed_by_callback(self):
        chunks, asked = [], []
        client = self.make(on_text=chunks.append,
                           on_permission=lambda request: asked.append(request.title) or True)
        client.start()
        client.send("도구 써 줘")
        self.assertEqual(asked, ["Running: date"])
        self.assertTrue("".join(chunks).endswith("/ allow-once"))

    def test_permission_rejected_without_callback(self):
        chunks = []
        client = self.make(on_text=chunks.append)
        client.start()
        client.send("도구 써 줘")
        self.assertTrue("".join(chunks).endswith("/ reject"))

    def test_tool_updates_reach_callback(self):
        tools = []
        client = self.make(on_tool=lambda request: tools.append((request.kind, request.title)))
        client.start()
        client.send("도구 써 줘")
        self.assertEqual(tools, [("execute", "Running: date")])

    def test_kiro_counts_credits_and_others_ignore_them(self):
        client = self.make()
        client.start()
        client.send("안녕")
        self.assertAlmostEqual(client.credits, 0.75)
        self.assertEqual(client.context_tokens, 1234)
        other = self.make(engine=ClaudeEngine, mode="auto")
        other.start()
        other.send("안녕")
        self.assertEqual(other.credits, 0)   # 크레딧 알림은 Kiro만의 확장이다

    def test_wrong_mode_raises(self):
        client = self.make(mode="kiro_default")
        with self.assertRaises(EngineError):
            client.start()

    def test_safe_mode_is_set_after_session_opens(self):
        chunks = []
        client = self.make(engine=ClaudeEngine, mode="auto", on_text=chunks.append)
        client.start()
        client.send("모드")
        self.assertEqual("".join(chunks), "받음: default")

    def test_claude_sends_session_meta_and_kiro_does_not(self):
        chunks = []
        client = self.make(engine=ClaudeEngine, mode="auto", on_text=chunks.append)
        client.start()
        client.send("메타")
        self.assertEqual("".join(chunks), '받음: {"claudeCode": {"options": {"settingSources": []}}}')
        chunks.clear()
        client = self.make(on_text=chunks.append)
        client.start()
        client.send("메타")
        self.assertEqual("".join(chunks), "받음: null")


class TurnResultTest(unittest.TestCase):
    """엔진마다 다르게 끝나도, 플랫폼은 같은 꼴의 TurnResult를 받는다."""

    def make(self, engine, style="", **callbacks):
        env = dict(os.environ, FAKE_STYLE=style)
        client = engine(WORKSPACE, command=FAKE + ["engine" if engine.expect_mode else "auto"], env=env, **callbacks)
        self.addCleanup(client.close)
        client.start()
        return client

    def test_tools_refusals_and_segments_are_packed(self):
        result = self.make(KiroEngine).send("도구 써 줘")
        self.assertEqual(result.stop, "done")
        self.assertEqual(result.segments, ["받음: 도구 써 줘", "/ reject"])
        self.assertEqual(result.text, "받음: 도구 써 줘\n\n/ reject")
        self.assertEqual([(r.kind, r.command) for r in result.tools], [("execute", "")])
        self.assertEqual([(r.kind, r.command) for r in result.refused], [("execute", "date")])
        self.assertEqual(result.notices, [])
        self.assertEqual(result.usage, {"credits": 0.75, "contextTokens": 1234})
        self.assertEqual(result.usage_text, "크레딧 0.750, 컨텍스트 1,234토큰")

    def test_engine_that_stops_on_refusal_is_asked_to_continue(self):
        notices = []
        result = self.make(CodexEngine, "codex", on_notice=notices.append).send("도구 써 줘")
        self.assertEqual(result.stop, "done")           # 멈춘 차례를 플랫폼이 이어 가게 했다
        self.assertEqual(len(result.notices), 1)
        self.assertEqual(notices, result.notices)
        self.assertEqual([r.command for r in result.refused], ["date"])
        self.assertIn("[플랫폼 알림] 방금 요청한 도구는 허락되지 않았다: 명령 실행 date", result.text)
        self.assertIsNone(result.usage["credits"])      # 크레딧은 Kiro만 알린다

    def test_engine_is_asked_to_continue_after_each_new_refusal(self):
        result = self.make(CodexEngine, "codex_twice").send("도구 써 줘")
        self.assertEqual(result.stop, "done")
        self.assertEqual(len(result.notices), 2)
        self.assertEqual(len(result.refused), 2)

    def test_codex_prefers_decline_over_cancel(self):
        result = self.make(CodexEngine, "codex_decline").send("도구 써 줘")
        self.assertEqual((result.stop, result.notices), ("done", []))
        self.assertTrue(result.text.endswith("/ decline"))

    def test_other_engines_keep_first_reject_option(self):
        result = self.make(ClaudeEngine, "codex").send("도구 써 줘")   # decline이 없는 선택지
        self.assertEqual(result.notices, ["엔진이 거절 뒤 차례를 멈춰서, 플랫폼이 거절을 알리고 이어서 하게 했다."])


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

    def test_codex_home_gets_managed_config_on_top(self):
        config = self.root / "codex" / "config.toml"
        config.parent.mkdir(parents=True)
        # 옛 판이 남긴 줄(같은 키)과 사용자가 쓴 줄이 섞인 파일
        config.write_text('# acp-starter: 옛 안내\nproject_doc_max_bytes = 0\nmodel = "gpt-x"\n'
                          '[mcp_servers.x]\nweb_search = "keep"\n', encoding="utf-8")
        CodexEngine.sandbox_env()
        first = config.read_text(encoding="utf-8")
        CodexEngine.sandbox_env()
        self.assertEqual(config.read_text(encoding="utf-8"), first)      # 몇 번을 실행해도 같다
        lines = first.splitlines()
        self.assertEqual(lines[1:3], ["project_doc_max_bytes = 0", 'web_search = "disabled"'])
        self.assertEqual([l for l in lines if l.startswith("project_doc_max_bytes")], ["project_doc_max_bytes = 0"])
        self.assertIn('model = "gpt-x"', lines)
        self.assertEqual(lines[-2:], ["[mcp_servers.x]", 'web_search = "keep"'])


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
