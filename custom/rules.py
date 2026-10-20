"""허락 규칙. 에이전트가 도구를 쓰려고 허락을 물을 때마다 플랫폼이 decide()를 부른다.

돌려줄 값은 셋 중 하나다.
- "allow": 묻지 않고 허락한다.
- "deny":  묻지 않고 거절한다.
- "ask":   사람에게 묻는다. 대시보드에서는 허락 카드가 뜬다.
           사람이 없는 일 실행(tasks/, run_once.py)에서는 거절한다.

처음에는 늘 "ask"를 돌려준다. 고치면 대시보드를 다시 켜지 않아도 다음 요청부터 반영된다.
이 함수가 오류를 내거나 셋이 아닌 값을 돌려주면 플랫폼은 "ask"로 처리하고 화면에 오류를 보인다.

tool_call의 모양(에이전트마다 조금 다르다. 2026-10-21 확인):
    Kiro:   {"title": "Running: python3 skills/...", "rawInput": {"command": "python3 skills/..."}}
    Codex:  {"title": "Run command", "kind": "execute", "rawInput": {"command": "\"python3 skills/...\""}}
    Claude: {"title": "python3 skills/...", "kind": "execute", "rawInput": {"command": "python3 skills/..."}}
detail(tool_call)은 그 가운데 명령이나 파일 경로를 꺼내 준다(Codex의 바깥 따옴표도 벗긴다).

Kiro Crew에서 비슷한 곳: src/kiro_crew/acp/client_permissions.py, src/kiro_crew/tool_permission.py
"""

from custom_loader import tool_detail as detail  # noqa: F401  (아래 예에서 쓴다)


def decide(agent, tool_call):
    return "ask"


# 예 1) 수업 스킬의 스크립트가 outbox/에 저장하는 명령은 묻지 않고 허락한다.
#     사람이 없는 일 실행에서도 스킬을 쓰게 하려면 이런 규칙이 필요하다.
#     에이전트마다 명령을 쓰는 꼴이 다르다(Codex는 printf ... | python3 ... 꼴을 자주 쓴다).
#     그래서 시작 글자가 아니라 들어 있는 글자로 고른다. 글자로 고르는 규칙은 느슨하다는 것도 기억한다.
#
# def decide(agent, tool_call):
#     command = detail(tool_call)
#     if "python3 skills/" in command and "--out outbox/" in command:
#         return "allow"
#     return "ask"
#
# 예 2) 지우는 명령과 인터넷 접근은 묻지도 않고 거절한다.
#
# def decide(agent, tool_call):
#     command = detail(tool_call)
#     if command.startswith(("rm ", "curl ", "wget ")):
#         return "deny"
#     return "ask"
