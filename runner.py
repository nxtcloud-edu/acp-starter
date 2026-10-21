"""사람 없이 일을 한 번 맡기고, 결과를 workspace/outbox/에 파일로 남긴다.

run_once.py와 dashboard.py가 함께 쓴다.
허락 요청은 custom/rules.py가 정한다. 사람이 없으므로 "ask"는 거절로 처리하고, 거절한 것을 결과 파일에 적는다.
결과 파일을 만든 뒤 custom/deliver.py의 deliver()를 부른다.
"""

import collections
import datetime
import pathlib
import re
import threading

import custom_loader
from acp_client import AcpClient, AcpError

ROOT = pathlib.Path(__file__).parent
WORKSPACE = ROOT / "workspace"
TASKS_DIR = ROOT / "tasks"
TIME_LIMIT_SECONDS = 300

# path: 결과 파일, delivery_error: deliver()의 오류 글(없으면 None)
Result = collections.namedtuple("Result", "path delivery_error")


def run_task(engine, prompt, name=None, workspace=WORKSPACE, client_factory=AcpClient,
             custom=custom_loader.CUSTOM):
    """일을 한 번 맡기고 Result(결과 파일 경로, 보내기 오류)를 돌려준다."""
    answer, tools, refused, notes = [], [], [], []

    def on_tool(request):
        tools.append(f"{request.label} {request.detail}".strip())

    def on_permission(request):
        decision, error = custom_loader.decide(engine, request, custom)
        if error:
            notes.append(error)
        if decision == "allow":
            return True
        refused.append(f"{request.label} {request.detail}".strip())
        return False

    client = client_factory(workspace, engine, on_text=answer.append, on_tool=on_tool,
                            on_permission=on_permission,
                            preamble=custom_loader.preamble(workspace, custom))
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
    path = outbox / f"{now:%Y-%m-%d_%H%M%S}_{engine}{label}.md"
    text = "".join(answer).strip()
    lines = [
        f"# 실행 결과 {now:%Y-%m-%d %H:%M}",
        "",
        f"- 일: {name or '바로 맡긴 질문'}",
        f"- 끝난 까닭: {stop_reason}",
        f"- 에이전트: {engine}",
        f"- 쓴 양: {client.usage_text()}",
        f"- 쓴 도구: {', '.join(tools) or '없음'}",
        f"- 거절한 도구: {', '.join(refused) or '없음'}",
    ]
    lines += [f"- 규칙 오류: {note}" for note in notes]
    lines += ["", "## 답", "", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")

    delivery_error = custom_loader.deliver(name, path, text, custom)
    if delivery_error:
        with path.open("a", encoding="utf-8") as file:
            file.write(f"\n- 보내기 오류: {delivery_error}\n")
    return Result(path, delivery_error)


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
