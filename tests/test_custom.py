"""custom/ 폴더와 스킬을 읽는 custom_loader를 확인한다.

실행: python -m unittest discover tests
"""

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import custom_loader  # noqa: E402

ROOT = pathlib.Path(__file__).parent.parent


class CustomLoaderTest(unittest.TestCase):
    def setUp(self):
        self.custom = pathlib.Path(tempfile.mkdtemp())
        self.workspace = pathlib.Path(tempfile.mkdtemp())

    def write(self, name, text):
        (self.custom / name).write_text(text, encoding="utf-8")

    def test_brand_defaults_and_overrides(self):
        self.assertEqual(custom_loader.brand(self.custom)["name"], "내 에이전트 플랫폼")
        self.write("brand.json", '{"_안내": "무시", "name": "마감지기", "accent": "#123456"}')
        brand = custom_loader.brand(self.custom)
        self.assertEqual((brand["name"], brand["accent"]), ("마감지기", "#123456"))
        self.assertNotIn("_안내", brand)
        self.write("brand.json", "{깨진 JSON")
        self.assertEqual(custom_loader.brand(self.custom)["name"], "내 에이전트 플랫폼")

    def test_preamble_has_business_without_comments_and_skills(self):
        self.write("업무.md", "<!-- 학생에게 하는 말 -->\n- 맡는 업무: 마감 정리\n")
        skill = self.workspace / "skills" / "deadline"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: deadline\ndescription: 마감 표\nexample: 표로 줘\n---\n본문",
                                        encoding="utf-8")
        text = custom_loader.preamble(self.workspace, self.custom)
        self.assertIn("맡는 업무: 마감 정리", text)
        self.assertNotIn("학생에게 하는 말", text)
        self.assertIn("- deadline: 마감 표 (`skills/deadline/SKILL.md`)", text)
        self.assertTrue(text.endswith(custom_loader.PREAMBLE_END))
        self.assertEqual(custom_loader.skills(self.workspace)[0]["example"], "표로 줘")

    def test_preamble_without_business_or_skills(self):
        text = custom_loader.preamble(self.workspace, self.custom)
        self.assertIn("아직 정하지 않았다", text)
        self.assertNotIn("쓸 수 있는 스킬", text)

    def test_decide_defaults_to_ask(self):
        self.assertEqual(custom_loader.decide("kiro", {}, self.custom), ("ask", None))
        self.assertEqual(custom_loader.decide("kiro", {}, ROOT / "custom"), ("ask", None))

    def test_decide_reads_file_each_time(self):
        self.write("rules.py", "def decide(agent, request):\n    return 'allow'\n")
        self.assertEqual(custom_loader.decide("kiro", {}, self.custom), ("allow", None))
        self.write("rules.py", "def decide(agent, request):\n    return 'deny'\n")
        self.assertEqual(custom_loader.decide("kiro", {}, self.custom), ("deny", None))

    def test_decide_errors_fall_back_to_ask(self):
        self.write("rules.py", "def decide(agent, request):\n    return 1 / 0\n")
        decision, error = custom_loader.decide("kiro", {}, self.custom)
        self.assertEqual(decision, "ask")
        self.assertIn("ZeroDivisionError", error)
        self.write("rules.py", "def decide(agent, request):\n    return 'yes'\n")
        decision, error = custom_loader.decide("kiro", {}, self.custom)
        self.assertEqual(decision, "ask")
        self.assertIn("'yes'", error)

    def test_deliver_errors_are_returned_not_raised(self):
        self.assertIsNone(custom_loader.deliver("일", "a.md", "답", self.custom))
        self.assertIsNone(custom_loader.deliver("일", "a.md", "답", ROOT / "custom"))
        self.write("deliver.py", "def deliver(task, path, text):\n    raise RuntimeError('웹훅 실패')\n")
        self.assertIn("웹훅 실패", custom_loader.deliver("일", "a.md", "답", self.custom))

    def test_load_env_does_not_override(self):
        env_file = self.custom / ".env"
        env_file.write_text("# 주석\nACP_TEST_A=1\nACP_TEST_B='둘'\n", encoding="utf-8")
        os.environ["ACP_TEST_A"] = "원래"
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("ACP_TEST_A", "ACP_TEST_B")])
        custom_loader.load_env(env_file)
        self.assertEqual((os.environ["ACP_TEST_A"], os.environ["ACP_TEST_B"]), ("원래", "둘"))

    def test_shipped_skills_point_inside_workspace(self):
        skills = {s["name"]: s for s in custom_loader.skills()}
        self.assertEqual(set(skills), {"memo-to-json", "data-to-html"})
        for name in skills:
            text = (ROOT / "workspace" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("~/.kiro", text)
            self.assertIn(f"python3 skills/{name}/scripts/", text)
            self.assertTrue(skills[name]["example"])


if __name__ == "__main__":
    unittest.main()
