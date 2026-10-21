"""대화 기록을 파일로 남긴다. 대화 하나가 conversations/<번호>.json 하나다.

이 파일은 "플랫폼 층"이다. 대화 기록은 엔진이 아니라 플랫폼이 갖는다.
그래서 엔진을 바꿔도, 대시보드를 껐다 켜도 같은 대화를 이어 간다.
대화 하나는 에이전트 하나와 나눈다. 엔진은 대화 중간에 바꿀 수 있다.

대화 파일의 꼴:
  {"id", "title", "agent", "engine", "created", "updated", "messages": [메시지, ...]}

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

ROOT = pathlib.Path(__file__).parent
FOLDER = ROOT / "conversations"
ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")   # 만든 때와 무작위 네 글자. 예: 20261021-153012-a1b2
TITLE_CHARS = 40
TALK = ("user", "agent")                        # 사람과 에이전트가 나눈 말. 목록의 메시지 수와 앞의 대화에 쓴다


class ConversationError(Exception):
    """대화가 없거나 읽지 못할 때 낸다. status는 대시보드가 돌려줄 HTTP 코드다."""

    def __init__(self, message, status=404):
        super().__init__(message)
        self.status = status


def _now():
    """지금 시각. 같은 초에 바뀐 대화도 목록의 순서가 정해지게 밀리초까지 쓴다. 예: 2026-10-21 15:30:12.345"""
    return datetime.datetime.now().isoformat(sep=" ", timespec="milliseconds")


def title_of(text):
    """첫 질문의 첫 줄로 대화의 제목을 만든다."""
    line = next((l.strip() for l in (text or "").splitlines() if l.strip()), "")
    return line if len(line) <= TITLE_CHARS else line[:TITLE_CHARS] + "…"


def summary(conversation):
    """목록에 보일 칸만 고른다."""
    fields = ("id", "title", "agent", "engine", "created", "updated")
    talk = [m for m in conversation["messages"] if m["role"] in TALK]
    return {**{key: conversation[key] for key in fields}, "messages": len(talk)}


class ConversationStore:
    """conversations/ 폴더의 대화 파일을 읽고 쓴다."""

    def __init__(self, folder=FOLDER):
        self.folder = pathlib.Path(folder)
        self.lock = threading.Lock()

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
        temporary.replace(path)

    def load(self, conversation_id):
        path = self._path(conversation_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ConversationError("그런 대화가 없습니다.")
        except (OSError, json.JSONDecodeError) as error:
            raise ConversationError(f"대화 파일을 읽지 못했습니다: {error}", 500)

    def create(self, agent, engine):
        now = datetime.datetime.now()
        conversation = {"id": f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}", "title": "",
                        "agent": agent, "engine": engine, "created": _now(), "updated": _now(), "messages": []}
        with self.lock:
            self._save(conversation)
        return conversation

    def append(self, conversation_id, message):
        """메시지 하나를 더한다. 첫 질문이면 제목도 정한다."""
        with self.lock:
            conversation = self.load(conversation_id)
            message = {**message, "at": _now()}
            conversation["messages"].append(message)
            conversation["updated"] = message["at"]
            if not conversation["title"] and message["role"] == "user":
                conversation["title"] = title_of(message.get("text"))
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

    def delete(self, conversation_id):
        path = self._path(conversation_id)
        with self.lock:
            if not path.is_file():
                raise ConversationError("그런 대화가 없습니다.")
            path.unlink()

    def listing(self):
        """대화 목록. 최근에 바뀐 대화가 위에 온다. 읽지 못하는 파일은 건너뛴다."""
        found = []
        for path in self.folder.glob("*.json") if self.folder.is_dir() else []:
            try:
                found.append(summary(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                continue
        found.sort(key=lambda c: (c["updated"], c["id"]), reverse=True)
        return found
