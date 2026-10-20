"""사람 없이 일을 한 번 맡기고, 결과를 workspace/outbox/에 파일로 남긴다.

run_once.py와 dashboard.py가 함께 쓴다.
사람이 없으므로 허락이 필요한 도구는 모두 거절하고, 거절한 것을 결과 파일에 적는다.
"""

import datetime
import pathlib
import re
import threading

from acp_client import AcpClient, AcpError

ROOT = pathlib.Path(__file__).parent
WORKSPACE = ROOT / "workspace"
TASKS_DIR = ROOT / "tasks"
TIME_LIMIT_SECONDS = 300


def run_task(agent, prompt, name=None, workspace=WORKSPACE, client_factory=AcpClient):
    """일을 한 번 맡기고 결과 파일의 경로를 돌려준다."""
    answer, tools, refused = [], [], []

    def on_tool(update):
        if update.get("sessionUpdate") == "tool_call":
            tools.append(update.get("title", ""))

    def on_permission(tool_call):
        refused.append(tool_call.get("title", ""))
        return False

    client = client_factory(workspace, agent, on_text=answer.append,
                            on_tool=on_tool, on_permission=on_permission)
    timer = threading.Timer(TIME_LIMIT_SECONDS, client.close)
    timer.start()
    try:
        client.start()
        stop_reason = client.prompt(prompt)
    except AcpError as error:
        stop_reason = f"오류: {error}"
    finally:
        timer.cancel()
        client.close()

    now = datetime.datetime.now()
    outbox = pathlib.Path(workspace) / "outbox"
    outbox.mkdir(exist_ok=True)
    label = f"_{name}" if name else ""
    path = outbox / f"{now:%Y-%m-%d_%H%M%S}_{agent}{label}.md"
    lines = [
        f"# 실행 결과 {now:%Y-%m-%d %H:%M}",
        "",
        f"- 일: {name or '바로 맡긴 질문'}",
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
    return path


def load_tasks(tasks_dir=TASKS_DIR):
    """tasks/*.md를 읽는다. 첫머리의 --- 사이에 agent와 time(매일 HH:MM)을 적는다."""
    tasks = []
    for path in sorted(pathlib.Path(tasks_dir).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = {}, text
        match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
        if match:
            for line in match.group(1).splitlines():
                key, _, value = line.partition(":")
                if value:
                    meta[key.strip()] = value.strip()
            body = match.group(2)
        time = meta.get("time", "")
        if time and not re.fullmatch(r"\d{2}:\d{2}", time):
            time = ""
        tasks.append({"name": path.stem, "agent": meta.get("agent", "kiro"),
                      "time": time, "prompt": body.strip()})
    return tasks


def is_due(task, now, last_run_date):
    """정해진 시각이 된 일인지 본다. 하루에 한 번만 참이다."""
    if not task["time"] or last_run_date == now.date():
        return False
    return now.strftime("%H:%M") >= task["time"]
