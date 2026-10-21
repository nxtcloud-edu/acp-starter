"""사람 없이 한 번 실행하고, 결과를 workspace/outbox/에 파일로 남긴다.

실행: python run_once.py                              (기본_도우미에게 workspace/task.md를 맡긴다)
      python run_once.py 메모_정리                     (메모_정리 에이전트에게 workspace/task.md를 맡긴다)
      python run_once.py 기본_도우미 "질문"            (질문을 바로 맡긴다)
      python run_once.py 기본_도우미 --engine claude "질문"   (에이전트는 그대로, 엔진만 바꿔 돌린다)

OS의 스케줄러(macOS·Linux는 cron, Windows는 작업 스케줄러)에 이 명령을 넣으면
정해진 때에 돈다. 허락 요청은 custom/rules.py가 정하고, 사람에게 물을 일("ask")은 거절한다.
대시보드(dashboard.py)를 켜 두면 tasks/의 시각에 맞춰 대시보드가 대신 돌린다.
"""

import sys

import custom_loader
from runner import WORKSPACE, run_task


def parse(args):
    """명령줄을 (에이전트, 엔진, 질문)으로 나눈다."""
    args = list(args)
    engine = None
    if "--engine" in args:
        at = args.index("--engine")
        if at + 1 >= len(args):
            raise SystemExit("--engine 뒤에 엔진 이름을 적는다. 예: --engine claude")
        engine = args[at + 1]
        del args[at:at + 2]
    agent = custom_loader.DEFAULT_AGENT
    names = {a["name"] for a in custom_loader.agents()}
    if args and args[0] in names:
        agent = args.pop(0)
    return agent, engine, " ".join(args)


def main():
    custom_loader.load_env()
    agent, engine, prompt = parse(sys.argv[1:])
    if not prompt:
        prompt = (WORKSPACE / "task.md").read_text(encoding="utf-8")
    result = run_task(agent, prompt, engine=engine)
    print(result.path)
    if result.delivery_error:
        print(result.delivery_error)


if __name__ == "__main__":
    main()
