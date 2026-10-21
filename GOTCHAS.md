# GOTCHAS

## Claude 샌드박스에 상위 폴더의 CLAUDE.md가 실림 (2026-10-20)

- 증상: `CLAUDE_CONFIG_DIR`을 레포 안의 `.homes/claude/`로 바꿨는데도, Claude의 답에 사용자 전역 지침(`~/.claude/CLAUDE.md`)의 말투와 문구가 나왔다. "지시문에 '작업 규격'이 있나"라고 물으면 "있음"이라고 답했다.
- 근본 원인: Claude Code는 작업 폴더에서 상위 폴더로 올라가며 각 폴더의 `CLAUDE.md`와 `.claude/CLAUDE.md`를 프로젝트 지침으로 읽는다. 작업 폴더가 홈 폴더 아래에 있으면 홈 폴더의 `.claude/CLAUDE.md`, 곧 전역 지침 파일이 그 경로에 걸린다. 설정 폴더를 바꾸는 것으로는 이 경로를 막지 못한다.
- 해결: `session/new`의 `_meta.claudeCode.options`로 `settingSources: []`를 넘긴다(`engines.json`의 `session_meta`). 같은 질문에 "없음"으로 답했다. 대신 작업 폴더의 `CLAUDE.md`도 읽지 않는다.
- 교훈: 샌드박스가 깨끗한지는 설정 폴더만 보고 판단하지 않는다. 지시문에만 있는 낱말을 물어서 실제로 실린 것을 확인한다. Kiro와 Codex는 같은 방법으로 확인했을 때 실리지 않았다(Codex는 세션 기록 파일로 확인).

## 로그인을 시작했다가 취소하면 Codex 샌드박스가 로그아웃된다 (2026-10-21)

- 증상: 로그인되어 있던 Codex 샌드박스에서 화면의 로그인을 시작했다가 취소했다. 그 뒤 `codex login status`가 `Not logged in`을 냈다.
- 근본 원인: `codex login --device-auth`는 시작하자마자 샌드박스 홈의 `auth.json`을 지운다. 새 로그인을 끝내지 않으면 로그인이 없는 상태로 남는다.
- 해결: 서버의 `POST /api/login/{agent}`가 로그인 상태를 먼저 보고, 로그인되어 있으면 `409`로 거부한다. 계정을 바꾸려면 로그아웃을 먼저 한다.
- 교훈: 로그인 명령은 "더하기"가 아니라 "바꾸기"일 수 있다. 상태를 바꾸는 명령은 실행 전에 지금 상태를 확인한다.

## Codex의 여러 줄 명령이 따옴표에 싸인 채 허락 카드와 규칙에 갔다 (2026-10-21)

- 증상: Codex가 스킬 스크립트를 heredoc으로 실행하려 할 때, 허락 카드의 명령이 `"python3 ... <<'JSON' {\"메모 날짜\": ...}"`처럼 바깥 따옴표와 `\"`가 붙은 채 나왔다. `request.command.startswith("python3")` 꼴의 규칙이 맞지 않았다.
- 근본 원인: codex-acp는 명령을 따옴표로 감싸 보낸다. 여러 줄 명령은 줄바꿈 문자를 이스케이프하지 않고 그대로 둔다. `json.loads`의 기본(strict) 모드는 문자열 안의 줄바꿈 문자를 받지 않아 실패했고, 실패하면 원래 글을 그대로 쓰게 되어 있었다. 테스트에는 한 줄 명령만 있어서 잡지 못했다.
- 해결: `engines/codex.py`의 `command_text`가 `json.loads(text, strict=False)`로 푼다. 실제 여러 줄 모양을 `tests/test_tool_request.py`에 더했다.
- 교훈: 엔진이 보내는 모양의 테스트 자료는 실제로 받은 것에서 가져오고, 한 줄짜리와 여러 줄짜리를 함께 넣는다.
