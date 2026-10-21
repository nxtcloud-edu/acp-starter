"""터미널에서 에이전트와 대화한다. 도구 허락은 custom/rules.py가 정하고, "ask"이면 사람이 y/n으로 정한다.

실행: python chat.py              (Kiro)
      python chat.py claude       (Claude)
      python chat.py codex        (Codex)
"""

import sys

import custom_loader
from acp_client import AcpClient, AcpError


def show_text(text):
    print(text, end="", flush=True)


def show_tool(request):
    print(f"\n  [도구] {request.label} {request.detail}", flush=True)


def ask_permission(request):
    decision, error = custom_loader.decide(sys.argv[1] if len(sys.argv) > 1 else "kiro", request)
    if error:
        print(f"\n  [규칙 오류] {error}")
    if decision != "ask":
        print(f"\n  [규칙] {request.label} {request.detail} → {decision}")
        return decision == "allow"
    print(f"\n  [허락 요청] {request.label} {request.detail}")
    answer = input("  허락할까요? [y/N] ").strip().lower()
    return answer == "y"


def main():
    engine = sys.argv[1] if len(sys.argv) > 1 else "kiro"
    try:
        client = AcpClient("workspace", engine, on_text=show_text, on_tool=show_tool,
                           on_permission=ask_permission, preamble=custom_loader.preamble())
    except AcpError as error:
        print(error)
        return
    try:
        client.start()
    except AcpError as error:
        print(error)
        client.close()
        return
    print(f"{engine} 엔진과 대화를 시작합니다. 끝내려면 /exit 를 입력하세요.")
    try:
        while True:
            try:
                text = input("\n> ").strip()
            except EOFError:
                break
            if text == "/exit":
                break
            if not text:
                continue
            client.prompt(text)
            print(f"\n  (쓴 양: {client.usage_text()})")
    except AcpError as error:
        print(f"\n{error}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
