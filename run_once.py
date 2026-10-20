"""사람 없이 한 번 실행하고, 결과를 workspace/outbox/에 파일로 남긴다.

실행: python run_once.py                    (Kiro에게 workspace/task.md를 맡긴다)
      python run_once.py claude             (Claude에게 workspace/task.md를 맡긴다)
      python run_once.py codex "질문"       (Codex에게 질문을 바로 맡긴다)

OS의 스케줄러(macOS·Linux는 cron, Windows는 작업 스케줄러)에 이 명령을 넣으면
정해진 때에 돈다. 사람이 없으므로 허락이 필요한 도구는 모두 거절한다.
"""

import datetime
import json
import pathlib
import sys
import threading

from acp_client import AGENTS_FILE, AcpClient, AcpError

WORKSPACE = pathlib.Path(__file__).parent / "workspace"
TIME_LIMIT_SECONDS = 300
AGENT_NAMES = json.loads(AGENTS_FILE.read_text(encoding="utf-8"))


def main():
    args = sys.argv[1:]
    agent = "kiro"
    if args and args[0] in AGENT_NAMES:
        agent = args.pop(0)
    if args:
        task = " ".join(args)
    else:
        task = (WORKSPACE / "task.md").read_text(encoding="utf-8")

    answer = []
    tools = []
    refused = []

    def on_tool(update):
        if update.get("sessionUpdate") == "tool_call":
            tools.append(update.get("title", ""))

    def on_permission(tool_call):
        refused.append(tool_call.get("title", ""))
        return False

    client = AcpClient(WORKSPACE, agent,
                       on_text=answer.append, on_tool=on_tool, on_permission=on_permission)
    timer = threading.Timer(TIME_LIMIT_SECONDS, client.close)
    timer.start()
    try:
        client.start()
        stop_reason = client.prompt(task)
    except AcpError as error:
        stop_reason = f"오류: {error}"
    finally:
        timer.cancel()
        client.close()

    now = datetime.datetime.now()
    outbox = WORKSPACE / "outbox"
    outbox.mkdir(exist_ok=True)
    path = outbox / f"{now:%Y-%m-%d_%H%M%S}_{agent}.md"
    lines = [
        f"# 실행 결과 {now:%Y-%m-%d %H:%M}",
        "",
        f"- 끝난 까닭: {stop_reason}",
        f"- 에이전트: {agent}",
        f"- 쓴 양: {client.usage_text()}",
        f"- 쓴 도구: {', '.join(tools) or '없음'}",
        f"- 거절한 도구: {', '.join(refused) or '없음'}",
        "",
        "## 답",
        "",
        "".join(answer).strip(),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
