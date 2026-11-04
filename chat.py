"""터미널에서 엔진과 대화한다. 도구 허락은 custom/rules.py가 정하고, "ask"이면 사람이 y/n으로 정한다.

실행: python chat.py            (첫 엔진)
      python chat.py <엔진>      (그 엔진. 이름은 engines/의 파일 이름이다)

대시보드와 같은 플랫폼 안내(custom/업무.md와 도구 규칙)를 보낸다.
터미널 대화는 대화 기록(conversations/)에 남지 않는다. 기록이 남는 대화는 대시보드에서 한다.
"""

import sys

import custom_loader
import engines
from engines import EngineError


def show_text(text):
    print(text, end="", flush=True)


def show_tool(request):
    print(f"\n  [도구] {request.label} {request.detail}", flush=True)


def ask_permission(request):
    decision, error = custom_loader.decide(request)
    if error:
        print(f"\n  [규칙 오류] {error}")
    if decision != "ask":
        print(f"\n  [규칙] {request.label} {request.detail} → {decision}")
        return decision == "allow"
    print(f"\n  [허락 요청] {request.label} {request.detail}")
    answer = input("  허락할까요? [y/N] ").strip().lower()
    return answer == "y"


def talk(client):
    """한 줄씩 받아 보낸다. /exit 이나 입력 끝(Ctrl+D)에서 멈춘다."""
    while True:
        try:
            text = input("\n> ").strip()
        except EOFError:
            return
        if text == "/exit":
            return
        if text:
            result = client.send(text)
            print(f"\n  ({result.stop_label} · 쓴 양: {result.usage_text})")


def main():
    custom_loader.load_env()
    engine = sys.argv[1] if len(sys.argv) > 1 else engines.names()[0]
    try:
        client = engines.make(engine, "workspace", on_text=show_text, on_tool=show_tool,
                              on_permission=ask_permission, on_notice=lambda t: print(f"\n  [플랫폼] {t}"),
                              preamble=custom_loader.preamble())
    except EngineError as error:
        print(error)
        return
    try:
        client.start()
    except EngineError as error:
        print(error)
        client.close()
        return
    print(f"{engine} 엔진과 대화를 시작합니다. 끝내려면 /exit 를 입력하세요.")
    try:
        talk(client)
    except EngineError as error:
        print(f"\n{error}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
