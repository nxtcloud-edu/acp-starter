"""안전 모드와 샌드박스를 지키는지 확인한다. 이 테스트가 깨지면 설정을 고치기 전에 까닭을 먼저 본다.

실행: python -m unittest discover tests
"""

import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import engines  # noqa: E402
from engines import base  # noqa: E402
from engines.claude import ClaudeEngine  # noqa: E402
from engines.codex import CodexEngine  # noqa: E402
from engines.kiro import SPEC as KIRO_SPEC  # noqa: E402

ROOT = pathlib.Path(__file__).parent.parent
# 모든 도구를 묻지 않고 허락하는 모드. 이 레포에서는 쓰지 않는다.
UNSAFE_MODES = {"bypassPermissions", "acceptEdits", "auto", "agent", "agent-full-access", "full-access"}


class SafetyTest(unittest.TestCase):
    def test_every_engine_starts_in_a_safe_mode(self):
        for name in engines.names():
            engine = engines.get(name)
            with self.subTest(engine=name):
                self.assertTrue(engine.safe_mode or engine.expect_mode)
                self.assertNotIn(engine.safe_mode, UNSAFE_MODES)

    def test_kiro_engine_allows_only_read_without_asking(self):
        self.assertEqual(KIRO_SPEC["allowedTools"], ["read"])
        self.assertEqual(KIRO_SPEC["resources"], [])
        self.assertNotIn("prompt", KIRO_SPEC)

    def test_codex_starts_read_only_and_skips_repo_agents_md(self):
        self.assertEqual(CodexEngine.env["INITIAL_AGENT_MODE"], "read-only")
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        with mock.patch.object(base, "HOMES", root):
            CodexEngine.sandbox_env()
        config = (root / "codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("project_doc_max_bytes = 0", config)
        self.assertIn('web_search = "disabled"', config)   # 허락을 묻지 않는 웹 검색을 끈다

    def test_codex_sees_only_what_the_platform_gives(self):
        # 2026-10-21: Codex가 ~/.agents/skills의 개인 스킬과 계정 플러그인, Apps 웹 도구, 자기 기억을 썼다.
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        with mock.patch.object(base, "HOMES", root):
            env = CodexEngine.sandbox_env()
        config = (root / "codex" / "config.toml").read_text(encoding="utf-8")
        for line in ("features.apps = false", "features.plugins = false",
                     "features.remote_plugin = false", "features.memories = false"):
            with self.subTest(line=line):
                self.assertIn(line, config)
        self.assertEqual(env["HOME"], str(root / "codex"))           # ~/.agents/skills를 찾지 못하게
        self.assertTrue(env["npm_config_cache"].endswith(".npm"))   # 어댑터는 원래 캐시에서

    def test_claude_reads_no_setting_files(self):
        meta = ClaudeEngine(ROOT).session_meta()
        self.assertEqual(meta["claudeCode"]["options"]["settingSources"], [])

    def test_workspace_has_no_engine_files(self):
        # 엔진만의 지시 파일이 작업 폴더에 있으면 엔진마다 다르게 일한다.
        for name in (".kiro", ".claude", ".codex", "AGENTS.md", "CLAUDE.md"):
            with self.subTest(file=name):
                self.assertFalse((ROOT / "workspace" / name).exists())

    def test_secrets_and_homes_are_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
        for entry in (".homes/", ".env", "workspace/outbox/"):
            self.assertIn(entry, ignored)


if __name__ == "__main__":
    unittest.main()
