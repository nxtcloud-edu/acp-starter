"""터미널에서 에이전트와 대화한다. 도구 허락은 custom/rules.py가 정하고, "ask"이면 사람이 y/n으로 정한다.

실행: python chat.py                           (기본_도우미)
      python chat.py 메모_정리                  (메모_정리 에이전트)
      python chat.py 메모_정리 --engine codex   (에이전트는 그대로, 엔진만 바꿔 돌린다)
"""

import sys

import custom_loader
from acp_client import AcpClient, AcpError
from run_once import parse


def show_text(text):
    print(text, end="", flush=True)


def show_tool(request):
    print(f"\n  [도구] {request.label} {request.detail}", flush=True)


def main():
    agent, engine, _ = parse(sys.argv[1:])
    try:
        definition = custom_loader.agent(agent)
    except custom_loader.AgentError as error:
        print(error)
        return
    engine = engine or definition["engine"]

    def ask_permission(request):
        decision, error = custom_loader.decide(agent, request)
        if error:
            print(f"\n  [규칙 오류] {error}")
        if decision != "ask":
            print(f"\n  [규칙] {request.label} {request.detail} → {decision}")
            return decision == "allow"
        print(f"\n  [허락 요청] {request.label} {request.detail}")
        answer = input("  허락할까요? [y/N] ").strip().lower()
        return answer == "y"

    try:
        client = AcpClient("workspace", engine, on_text=show_text, on_tool=show_tool,
                           on_permission=ask_permission, preamble=custom_loader.preamble(agent=definition))
    except AcpError as error:
        print(error)
        return
    try:
        client.start()
    except AcpError as error:
        print(error)
        client.close()
        return
    print(f"{agent} 에이전트({engine} 엔진)와 대화를 시작합니다. 끝내려면 /exit 를 입력하세요.")
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
