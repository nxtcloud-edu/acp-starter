"""대화 기록 파일(conversations.py)을 확인한다.

실행: python -m unittest discover tests
"""

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import conversations  # noqa: E402


class ConversationStoreTest(unittest.TestCase):
    def setUp(self):
        self.folder = pathlib.Path(tempfile.mkdtemp()) / "conversations"
        self.store = conversations.ConversationStore(self.folder)

    def test_save_retries_while_another_program_holds_the_file(self):
        # Windows에서는 다른 프로그램(백신, 검색 색인)이 파일을 열고 있으면 바꿔 넣기가 잠깐 PermissionError로 실패한다.
        conversation = self.store.create("kiro")
        real_replace, failures = pathlib.Path.replace, []

        def replace(path, target):
            if len(failures) < 2:
                failures.append(path)
                raise PermissionError(13, "다른 프로그램이 파일을 쓰는 중")
            return real_replace(path, target)

        with mock.patch.object(pathlib.Path, "replace", replace):
            self.store.append(conversation["id"], {"role": "user", "text": "안녕"})
        self.assertEqual(len(failures), 2)
        self.assertEqual(self.store.load(conversation["id"])["messages"][0]["text"], "안녕")

    def test_current_is_the_newest_and_is_made_when_none(self):
        self.assertIsNone(self.store.latest())
        first = self.store.current("kiro")                        # 하나도 없으면 만든다
        self.assertEqual(self.store.current("codex")["id"], first["id"])   # 있으면 그것을 쓴다
        older = {**first, "id": "20200101-000000-0000"}
        (self.folder / f"{older['id']}.json").write_text("{}", encoding="utf-8")
        (self.folder / "20990101-000000-ffff.json").write_text("{깨진", encoding="utf-8")   # 깨진 파일은 건너뛴다
        (self.folder / "메모.json").write_text("{}", encoding="utf-8")                     # 번호가 아닌 파일도
        self.assertEqual(self.store.latest()["id"], first["id"])

    def test_conversation_made_in_the_same_moment_is_still_newer(self):
        ids = [self.store.create("kiro")["id"] for _ in range(5)]
        self.assertEqual(sorted(ids), ids)
        self.assertEqual(self.store.latest()["id"], ids[-1])
        old = "20261021-162805-aee8"   # 밀리초가 없는 앞의 꼴
        self.assertTrue(conversations.ID.fullmatch(old))
        self.assertLess(old, self.store.create("kiro")["id"])

    def test_change_engine_leaves_a_note(self):
        conversation = self.store.create("kiro")
        changed = self.store.change_engine(conversation["id"], "claude", "바꿨다")
        self.assertEqual((changed["engine"], changed["messages"][-1]["role"]), ("claude", "note"))

    def test_unknown_or_unsafe_id_is_refused(self):
        for bad in ("20261021-000000-abcd", "../../engines/base"):
            with self.subTest(id=bad), self.assertRaises(conversations.ConversationError):
                self.store.load(bad)


if __name__ == "__main__":
    unittest.main()
