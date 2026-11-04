"""허락 규칙. 에이전트가 도구를 쓰려고 허락을 물을 때마다 플랫폼이 decide()를 부른다.

돌려줄 값은 셋 중 하나다.
- "allow": 묻지 않고 허락한다.
- "deny":  묻지 않고 거절한다.
- "ask":   사람에게 묻는다. 대시보드에서는 허락 카드가 뜬다.

처음에는 늘 "ask"를 돌려준다. 그래서 파일 쓰기, 명령 실행, 인터넷은 모두 사람에게 묻는다.
고치면 대시보드를 다시 켜지 않아도 다음 요청부터 반영된다.
이 함수가 오류를 내거나 셋이 아닌 값을 돌려주면 플랫폼은 "ask"로 처리하고 화면에 오류를 보인다.

request는 엔진(Kiro, Claude, Codex)과 상관없이 같은 꼴이다. 그래서 엔진을 바꿔도 규칙은 그대로 쓴다.
    request.kind     종류: "execute"(명령 실행), "edit"(파일 쓰기), "fetch"(인터넷), "delete", "move", "read", "other"
    request.command  실행할 명령(kind가 "execute"일 때). 예: "ls"
    request.path     다룰 파일. 작업 폴더(workspace/) 안이면 작업 폴더 기준. 예: "메모/오늘.md"
    request.url      인터넷 주소. 웹 가져오기 도구든 명령(curl, wget)이든 인터넷에 가면 여기에 주소가 있다
    request.engine   요청을 보낸 엔진. 엔진마다 다르게 하고 싶을 때만 쓴다
    request.raw      엔진이 보낸 원래 모양

엔진이 스스로 묻지 않고 하는 일(파일 읽기, 일부 엔진의 읽기 전용 명령)은 이 함수까지 오지 않는다.

Kiro Crew에서 비슷한 곳: src/kiro_crew/acp/client_permissions.py, src/kiro_crew/tool_permission.py
"""


def decide(request):
    return "ask"


# 예 1) 작업 폴더의 메모/ 안에 쓰는 파일은 묻지 않고 허락한다. 다른 곳에 쓰면 묻는다.
#
# def decide(request):
#     if request.kind == "edit" and request.path.startswith("메모/"):
#         return "allow"
#     return "ask"
#
# 예 2) 인터넷은 묻지도 않고 거절한다.
#     request.url은 엔진과 도구가 달라도 인터넷 주소가 들어 있어서, 이 한 줄로 모든 엔진의 인터넷을 막는다.
#
# def decide(request):
#     if request.url:
#         return "deny"
#     return "ask"
#
# 예 3) 파일 목록을 보는 명령(ls)만 허락한다.
#     명령을 글자로 고르는 규칙은 느슨하다는 것도 기억한다(명령 뒤에 다른 명령을 붙일 수 있다).
#     그래서 명령 전체가 정확히 같을 때만 허락한다.
#
# def decide(request):
#     if request.kind == "execute" and request.command in ("ls", "ls -la", "pwd"):
#         return "allow"
#     return "ask"
