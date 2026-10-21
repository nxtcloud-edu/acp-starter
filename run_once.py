"""사람 없이 한 번 실행하고, 결과를 workspace/outbox/에 파일로 남긴다.

실행: python run_once.py                    (Kiro에게 workspace/task.md를 맡긴다)
      python run_once.py claude             (Claude에게 workspace/task.md를 맡긴다)
      python run_once.py codex "질문"       (Codex에게 질문을 바로 맡긴다)

OS의 스케줄러(macOS·Linux는 cron, Windows는 작업 스케줄러)에 이 명령을 넣으면
정해진 때에 돈다. 허락 요청은 custom/rules.py가 정하고, 사람에게 물을 일("ask")은 거절한다.
대시보드(dashboard.py)를 켜 두면 tasks/의 시각에 맞춰 대시보드가 대신 돌린다.
"""

import json
import sys

import custom_loader
from acp_client import ENGINES_FILE
from runner import WORKSPACE, run_task

ENGINE_NAMES = json.loads(ENGINES_FILE.read_text(encoding="utf-8"))


def main():
    custom_loader.load_env()
    args = sys.argv[1:]
    engine = "kiro"
    if args and args[0] in ENGINE_NAMES:
        engine = args.pop(0)
    if args:
        prompt = " ".join(args)
    else:
        prompt = (WORKSPACE / "task.md").read_text(encoding="utf-8")
    result = run_task(engine, prompt)
    print(result.path)
    if result.delivery_error:
        print(result.delivery_error)


if __name__ == "__main__":
    main()
