"""custom/ 폴더를 읽는 custom_loader를 확인한다.

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

    def test_shipped_brand_has_name_tagline_and_accent(self):
        brand = custom_loader.brand()
        for key in ("name", "tagline", "accent"):
            self.assertTrue(brand[key])

    def test_preamble_has_business_without_comments(self):
        self.write("업무.md", "<!-- 학생에게 하는 말 -->\n- 맡는 업무: 마감 정리\n")
        text = custom_loader.preamble(self.custom)
        self.assertIn("맡는 업무: 마감 정리", text)
        self.assertNotIn("학생에게 하는 말", text)
        self.assertTrue(text.endswith(custom_loader.PREAMBLE_END))

    def test_preamble_without_business(self):
        self.assertIn("아직 정하지 않았다", custom_loader.preamble(self.custom))

    def test_preamble_has_only_business_tool_rules_and_history(self):
        text = custom_loader.preamble(self.custom, [{"role": "user", "text": "앞의 질문"}])
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        self.assertEqual(headings, ["## 업무", "## 도구를 쓸 때", "## 지금까지의 대화"])
        for rule in custom_loader.TOOL_RULES:
            self.assertIn(f"- {rule}", text)
        self.assertLess(text.index("[사용자] 앞의 질문"), text.index(custom_loader.PREAMBLE_END))
        self.assertNotIn("지금까지의 대화", custom_loader.preamble(self.custom))

    def test_decide_defaults_to_ask(self):
        self.assertEqual(custom_loader.decide({}, self.custom), ("ask", None))
        self.assertEqual(custom_loader.decide({}, ROOT / "custom"), ("ask", None))

    def test_decide_reads_file_each_time(self):
        self.write("rules.py", "def decide(request):\n    return 'allow'\n")
        self.assertEqual(custom_loader.decide({}, self.custom), ("allow", None))
        self.write("rules.py", "def decide(request):\n    return 'deny'\n")
        self.assertEqual(custom_loader.decide({}, self.custom), ("deny", None))

    def test_decide_errors_fall_back_to_ask(self):
        self.write("rules.py", "def decide(request):\n    return 1 / 0\n")
        decision, error = custom_loader.decide({}, self.custom)
        self.assertEqual(decision, "ask")
        self.assertIn("ZeroDivisionError", error)
        self.write("rules.py", "def decide(request):\n    return 'yes'\n")
        decision, error = custom_loader.decide({}, self.custom)
        self.assertEqual(decision, "ask")
        self.assertIn("'yes'", error)

    def test_load_env_does_not_override(self):
        env_file = self.custom / ".env"
        env_file.write_text("# 주석\nACP_TEST_A=1\nACP_TEST_B='둘'\n", encoding="utf-8")
        os.environ["ACP_TEST_A"] = "원래"
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("ACP_TEST_A", "ACP_TEST_B")])
        custom_loader.load_env(env_file)
        self.assertEqual((os.environ["ACP_TEST_A"], os.environ["ACP_TEST_B"]), ("원래", "둘"))

    def test_history_is_cut_from_the_oldest(self):
        history = [{"role": "user" if i % 2 == 0 else "agent", "text": f"말{i} " + "가" * 10} for i in range(30)]
        text = "\n\n".join(custom_loader.history_lines(history))
        self.assertNotIn("말17 ", text)
        self.assertIn("[사용자] 말18 ", text)
        self.assertIn("[에이전트] 말29 ", text)
        long = custom_loader.history_lines([{"role": "agent", "text": "나" * 5000}])[0]
        self.assertTrue(long.endswith("…(줄임)"))
        self.assertLessEqual(len(long), custom_loader.MESSAGE_CHARS + 20)
        many = custom_loader.history_lines([{"role": "user", "text": "다" * 1400}] * 12)
        self.assertLessEqual(sum(map(len, many)), custom_loader.HISTORY_CHARS)

    def test_history_keeps_only_talk_between_user_and_agent(self):
        # 대화 기록에는 플랫폼의 알림과 앞서 보낸 플랫폼 안내도 있다. 앞의 대화에는 넣지 않는다.
        history = [{"role": "user", "text": "하나"}, {"role": "preamble", "text": "안내 전문"},
                   {"role": "agent", "text": "답 하나"}, {"role": "note", "text": "엔진을 바꿨다"},
                   {"role": "agent", "text": "  "}]
        self.assertEqual(custom_loader.history_lines(history), ["[사용자] 하나", "[에이전트] 답 하나"])


if __name__ == "__main__":
    unittest.main()
