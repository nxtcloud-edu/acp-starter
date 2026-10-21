"""안전 모드와 샌드박스를 지키는지 확인한다. 이 테스트가 깨지면 설정을 고치기 전에 까닭을 먼저 본다.

실행: python -m unittest discover tests
"""

import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import acp_client  # noqa: E402

ROOT = pathlib.Path(__file__).parent.parent
ENGINES = json.loads((ROOT / "engines.json").read_text(encoding="utf-8"))
# 모든 도구를 묻지 않고 허락하는 모드. 이 레포에서는 쓰지 않는다.
UNSAFE_MODES = {"bypassPermissions", "acceptEdits", "auto", "agent", "agent-full-access", "full-access"}


class SafetyTest(unittest.TestCase):
    def test_every_agent_starts_in_a_safe_mode(self):
        for name, engine in ENGINES.items():
            with self.subTest(engine=name):
                self.assertTrue(engine.get("safe_mode") or engine.get("expect_mode"))
                self.assertNotIn(engine.get("safe_mode"), UNSAFE_MODES)

    def test_kiro_agent_allows_only_read_without_asking(self):
        kiro = json.loads((ROOT / "workspace" / ".kiro" / "agents" / "engine.json").read_text(encoding="utf-8"))
        self.assertEqual(kiro["allowedTools"], ["read"])
        self.assertEqual(kiro["resources"], [])

    def test_codex_starts_read_only_and_skips_repo_agents_md(self):
        codex = ENGINES["codex"]
        self.assertEqual(codex["env"]["INITIAL_AGENT_MODE"], "read-only")
        self.assertIn("project_doc_max_bytes = 0", codex["home_files"]["config.toml"])

    def test_claude_reads_no_setting_files(self):
        self.assertEqual(ENGINES["claude"]["session_meta"]["claudeCode"]["options"]["settingSources"], [])

    def test_sandbox_writes_home_files_once(self):
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        engine = {"home_env": "CODEX_HOME", "home_files": {"config.toml": "x = 1\n"}}
        with mock.patch.object(acp_client, "ROOT", root):
            env = acp_client.sandbox_env("codex", engine)
            config = root / ".homes" / "codex" / "config.toml"
            self.assertEqual(env["CODEX_HOME"], str(root / ".homes" / "codex"))
            self.assertEqual(config.read_text(), "x = 1\n")
            config.write_text("x = 2\n")
            acp_client.sandbox_env("codex", engine)
            self.assertEqual(config.read_text(), "x = 2\n")

    def test_secrets_and_homes_are_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
        for entry in (".homes/", ".env", "workspace/outbox/"):
            self.assertIn(entry, ignored)


if __name__ == "__main__":
    unittest.main()
