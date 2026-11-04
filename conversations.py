"""대화 기록을 파일로 남긴다. 대화 하나가 conversations/<번호>.json 하나다.

이 파일은 "플랫폼 층"이다. 대화 기록은 엔진이 아니라 플랫폼이 갖는다.
그래서 엔진을 바꿔도, 대시보드를 껐다 켜도 같은 대화를 이어 간다.
화면은 늘 가장 새 대화 하나를 보인다. "새 대화"를 누르면 새 파일을 만든다. 앞의 파일은 지우지 않는다.

대화 파일의 꼴:
  {"id", "engine", "created", "updated", "messages": [메시지, ...]}

메시지의 role과 칸(모두 text와 at이 있다):
  user      사람의 질문
  agent     에이전트의 답. engine, stop, stopLabel, usage, tools, refused, notices
  note      플랫폼이 남긴 알림. 예: 엔진을 바꿨다. error가 true이면 오류
  preamble  엔진 세션을 새로 열 때 첫 질문 앞에 붙인 플랫폼 안내. engine, history(넣은 앞의 대화 수)
"""

import datetime
import json
import pathlib
import re
import secrets
import threading
import time

ROOT = pathlib.Path(__file__).parent
FOLDER = ROOT / "conversations"
# 만든 때(밀리초까지)와 무작위 네 글자. 예: 20261021-153012345-a1b2. 밀리초가 없는 앞의 꼴도 읽는다
ID = re.compile(r"\d{8}-\d{6}(\d{3})?-[0-9a-f]{4}")
REPLACE_TRIES = 5                               # 바꿔 넣기를 해 보는 횟수. Windows에서는 다른 프로그램이 파일을 잡으면 잠깐 실패한다


class ConversationError(Exception):
    """대화가 없거나 읽지 못할 때 낸다. status는 대시보드가 돌려줄 HTTP 코드다."""

    def __init__(self, message, status=404):
        super().__init__(message)
        self.status = status


def _now():
    """지금 시각. 예: 2026-10-21 15:30:12.345"""
    return datetime.datetime.now().isoformat(sep=" ", timespec="milliseconds")


class ConversationStore:
    """conversations/ 폴더의 대화 파일을 읽고 쓴다."""

    def __init__(self, folder=FOLDER):
        self.folder = pathlib.Path(folder)
        # 읽기와 쓰기를 같은 잠금 안에서 한다. Windows는 열려 있는 파일을 바꿔 넣지 못하기 때문이다.
        self.lock = threading.RLock()

    def _path(self, conversation_id):
        if not ID.fullmatch(str(conversation_id or "")):
            raise ConversationError("그런 대화가 없습니다.")
        return self.folder / f"{conversation_id}.json"

    def _save(self, conversation):
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self._path(conversation["id"])
        temporary = path.with_suffix(".tmp")
        # 다 쓴 뒤에 바꿔 넣는다. 쓰는 도중에 꺼져도 앞의 파일이 깨지지 않는다.
        temporary.write_text(json.dumps(conversation, ensure_ascii=False, indent=1), encoding="utf-8")
        for attempt in range(REPLACE_TRIES):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt == REPLACE_TRIES - 1:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def load(self, conversation_id):
        path = self._path(conversation_id)
        with self.lock:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                raise ConversationError("그런 대화가 없습니다.")
            except (OSError, json.JSONDecodeError) as error:
                raise ConversationError(f"대화 파일을 읽지 못했습니다: {error}", 500)

    def _new_id(self):
        """새 번호. 이름 순서가 만든 순서가 되게, 가장 새 번호보다 뒤에 오는 번호를 만든다."""
        newest = max((p.stem for p in self.folder.glob("*.json") if ID.fullmatch(p.stem)), default="")
        for _ in range(100):
            now = datetime.datetime.now()
            stamp = f"{now:%Y%m%d-%H%M%S}{now.microsecond // 1000:03d}"
            if stamp > newest[:len(stamp)]:
                break
            time.sleep(0.002)   # 같은 밀리초에 만든 대화가 있다
        return f"{stamp}-{secrets.token_hex(2)}"

    def create(self, engine):
        with self.lock:
            conversation = {"id": self._new_id(), "engine": engine,
                            "created": _now(), "updated": _now(), "messages": []}
            self._save(conversation)
        return conversation

    def latest(self):
        """가장 새로 만든 대화. 번호가 만든 때로 시작하므로 이름 순서가 만든 순서다. 없으면 None."""
        with self.lock:
            paths = sorted(self.folder.glob("*.json")) if self.folder.is_dir() else []
            for path in reversed(paths):
                if not ID.fullmatch(path.stem):
                    continue
                try:
                    return self.load(path.stem)
                except ConversationError:
                    continue   # 깨진 파일은 건너뛴다
        return None

    def current(self, engine):
        """지금 대화. 대화가 하나도 없으면 그 엔진으로 새로 만든다."""
        with self.lock:
            return self.latest() or self.create(engine)

    def append(self, conversation_id, message):
        """메시지 하나를 더한다."""
        with self.lock:
            conversation = self.load(conversation_id)
            message = {**message, "at": _now()}
            conversation["messages"].append(message)
            conversation["updated"] = message["at"]
            self._save(conversation)
            return conversation

    def change_engine(self, conversation_id, engine, note):
        """대화의 엔진을 바꾸고 알림을 남긴다."""
        with self.lock:
            conversation = self.load(conversation_id)
            conversation["engine"] = engine
            conversation["messages"].append({"role": "note", "text": note, "at": _now()})
            conversation["updated"] = _now()
            self._save(conversation)
            return conversation
