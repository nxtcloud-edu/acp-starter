"""허락 규칙. 에이전트가 도구를 쓰려고 허락을 물을 때마다 플랫폼이 decide()를 부른다.

돌려줄 값은 셋 중 하나다.
- "allow": 묻지 않고 허락한다.
- "deny":  묻지 않고 거절한다.
- "ask":   사람에게 묻는다. 대시보드에서는 허락 카드가 뜬다.
           사람이 없는 일 실행(tasks/, run_once.py)에서는 거절한다.

처음에는 늘 "ask"를 돌려준다. 고치면 대시보드를 다시 켜지 않아도 다음 요청부터 반영된다.
이 함수가 오류를 내거나 셋이 아닌 값을 돌려주면 플랫폼은 "ask"로 처리하고 화면에 오류를 보인다.

request는 엔진(Kiro, Claude, Codex)과 상관없이 같은 꼴이다. 그래서 엔진을 바꿔도 규칙은 그대로 쓴다.
    request.kind     종류: "execute"(명령 실행), "edit"(파일 쓰기), "fetch"(인터넷), "delete", "move", "read", "other"
    request.command  실행할 명령(kind가 "execute"일 때). 예: "python3 skills/memo-to-json/scripts/save_memo.py --out outbox/a.json"
    request.path     다룰 파일. 작업 폴더 안이면 작업 폴더 기준. 예: "outbox/a.json"
    request.url      가져올 주소(kind가 "fetch"일 때)
    request.engine   요청을 보낸 엔진. 엔진마다 다르게 하고 싶을 때만 쓴다
    request.raw      엔진이 보낸 원래 모양
agent는 요청을 보낸 에이전트의 이름이다(custom/agents/의 파일 이름).

엔진이 스스로 묻지 않고 하는 일(파일 읽기, 일부 엔진의 읽기 전용 명령)은 이 함수까지 오지 않는다.

Kiro Crew에서 비슷한 곳: src/kiro_crew/acp/client_permissions.py, src/kiro_crew/tool_permission.py
"""


def decide(agent, request):
    return "ask"


# 예 1) 스킬 스크립트가 outbox/에 저장하는 명령은 묻지 않고 허락한다.
#     사람이 없는 일 실행에서도 스킬을 쓰게 하려면 이런 규칙이 필요하다.
#     명령을 글자로 고르는 규칙은 느슨하다는 것도 기억한다(명령 뒤에 다른 명령을 붙일 수 있다).
#
# def decide(agent, request):
#     if request.kind == "execute" and "python3 skills/" in request.command and "--out outbox/" in request.command:
#         return "allow"
#     return "ask"
#
# 예 2) outbox/ 안에 쓰는 파일은 허락하고, 인터넷은 묻지도 않고 거절한다.
#
# def decide(agent, request):
#     if request.kind == "edit" and request.path.startswith("outbox/"):
#         return "allow"
#     if request.kind == "fetch":
#         return "deny"
#     return "ask"
