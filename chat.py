"""터미널에서 에이전트와 대화한다. 도구 허락은 사람이 y/n으로 정한다.

실행: python chat.py
"""

from acp_client import AcpClient, AcpError


def show_text(text):
    print(text, end="", flush=True)


def show_tool(update):
    if update.get("sessionUpdate") == "tool_call":
        print(f"\n  [도구] {update.get('title')}", flush=True)


def ask_permission(tool_call):
    print(f"\n  [허락 요청] {tool_call.get('title')}")
    answer = input("  허락할까요? [y/N] ").strip().lower()
    return answer == "y"


def main():
    client = AcpClient("workspace", "starter",
                       on_text=show_text, on_tool=show_tool, on_permission=ask_permission)
    try:
        client.start()
    except AcpError as error:
        print(error)
        return
    print("대화를 시작합니다. 끝내려면 /exit 를 입력하세요.")
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
            print(f"\n  (지금까지 쓴 크레딧: {client.credits:.3f})")
    except AcpError as error:
        print(f"\n{error}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
