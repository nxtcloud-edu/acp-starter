"""엔진 층. 플랫폼은 이 패키지를 거쳐서만 엔진을 쓴다.

엔진 하나는 engines/<이름>.py 하나다. 엔진마다 다른 실행 명령, 샌드박스, 안전 모드, 로그인,
메시지의 모양은 그 파일이 맞추고, 플랫폼에는 같은 꼴(ToolRequest 등)로 넘긴다.
새 엔진을 더하려면 AcpEngine을 이어받은 파일을 만들고 아래 ENGINES에 더한다.
"""

from engines.base import AcpEngine, EngineError, KIND_LABELS, ToolRequest  # noqa: F401
from engines.claude import ClaudeEngine
from engines.codex import CodexEngine
from engines.kiro import KiroEngine

ENGINES = {engine.name: engine for engine in (KiroEngine, ClaudeEngine, CodexEngine)}


def names():
    """엔진 이름들. 처음 것이 기본 엔진이다."""
    return list(ENGINES)


def get(name):
    """엔진 클래스 하나. 없으면 EngineError."""
    if name not in ENGINES:
        raise EngineError(f"엔진 '{name}'이 없습니다. 고를 수 있는 것: {', '.join(ENGINES)}")
    return ENGINES[name]


def make(name, workspace, **options):
    """엔진 세션 하나를 만든다. options는 AcpEngine의 인자(on_text, on_tool, on_permission, preamble)."""
    return get(name)(workspace, **options)
