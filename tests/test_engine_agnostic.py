"""플랫폼 층이 특정 엔진에 기대지 않는지 확인한다.

규칙: 엔진(Kiro, Claude, Codex)마다 다른 것은 엔진 층(acp_client.py, engines.json,
workspace/.kiro/agents/engine.json, login.py)에만 둔다. 플랫폼 층과 내가 바꾸는 파일은
엔진 이름을 코드에 적지 않는다. 그래야 에이전트의 엔진을 바꿔도 플랫폼 기능이 그대로 돈다.

실행: python -m unittest discover tests
"""

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).parent.parent
PLATFORM_FILES = ["custom_loader.py", "dashboard.py", "runner.py", "run_once.py", "chat.py",
                  "app/static/app.js", "custom/rules.py", "custom/deliver.py"]


class EngineAgnosticTest(unittest.TestCase):
    def test_platform_files_do_not_name_an_engine(self):
        engines = list(json.loads((ROOT / "engines.json").read_text(encoding="utf-8")))
        pattern = re.compile(r"""["'](%s)["']""" % "|".join(map(re.escape, engines)))
        for name in PLATFORM_FILES:
            with self.subTest(file=name):
                code = "\n".join(line for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
                                 if not line.lstrip().startswith(("#", "//")))
                self.assertEqual(pattern.findall(code), [], f"{name}에 엔진 이름이 문자열로 들어 있다")

    def test_engine_specific_settings_live_in_engines_json(self):
        engines = json.loads((ROOT / "engines.json").read_text(encoding="utf-8"))
        for name, engine in engines.items():
            with self.subTest(engine=name):
                for key in ("command", "home_env", "login", "status", "login_mode"):
                    self.assertIn(key, engine)


if __name__ == "__main__":
    unittest.main()
