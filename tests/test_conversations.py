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
        self.store = conversations.ConversationStore(pathlib.Path(tempfile.mkdtemp()) / "conversations")

    def test_save_retries_while_another_program_holds_the_file(self):
        # Windows에서는 다른 프로그램(백신, 검색 색인)이 파일을 열고 있으면 바꿔 넣기가 잠깐 PermissionError로 실패한다.
        conversation = self.store.create("기본_도우미", "kiro")
        real_replace, failures = pathlib.Path.replace, []

        def replace(path, target):
            if len(failures) < 2:
                failures.append(path)
                raise PermissionError(13, "다른 프로그램이 파일을 쓰는 중")
            return real_replace(path, target)

        with mock.patch.object(pathlib.Path, "replace", replace):
            saved = self.store.append(conversation["id"], {"role": "user", "text": "안녕"})
        self.assertEqual(len(failures), 2)
        self.assertEqual(self.store.load(conversation["id"])["messages"][0]["text"], "안녕")
        self.assertEqual(saved["title"], "안녕")

    def test_title_comes_from_the_first_line_or_the_files(self):
        conversation = self.store.create("메모_정리", "claude")
        self.store.append(conversation["id"], {"role": "user", "text": "", "files": ["inbox/내준비메모.jpg"]})
        self.assertEqual(self.store.listing()[0]["title"], "내준비메모.jpg")
        self.assertEqual(conversations.title_of("\n  첫 줄\n둘째 줄"), "첫 줄")
        self.assertTrue(conversations.title_of("가" * 50).endswith("…"))


if __name__ == "__main__":
    unittest.main()
