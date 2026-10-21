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

## Codex에서 거절하면 차례 전체가 멈췄다 (2026-10-21)

- 증상: 같은 요청에서 Kiro와 Claude는 거절된 단계를 건너뛰고 끝까지 보고했는데, Codex는 첫 거절 뒤 아무 말 없이 끝났다. 끝난 까닭(`stopReason`)이 `cancelled`였다. 사람 없는 일 실행의 결과도 엔진에 따라 달라졌다.
- 근본 원인: codex-acp 2.2.2의 거절 선택지는 `decline`("No, continue without running it")과 `cancel`("No, and tell Codex what to do differently") 둘이다. 그런데 명령 실행 요청과 파일 고치기 요청에는 `cancel`만 준다. 플랫폼은 종류(`reject_once`)로 골랐으므로 `cancel`을 골랐고, `cancel`은 차례를 멈춘다.
- 해결: `engines/codex.py`가 `decline`이 있으면 먼저 고른다. 없어서 차례가 멈추면 `engines/base.py`의 `send`가 거절된 도구를 알리고 "그 도구 없이 이어서 하라"고 한 번 더 보낸다. 플랫폼은 그 사실을 알림(`notice`)으로 남긴다.
- 교훈: 같은 이름의 선택(거절)이 엔진마다 다른 결과를 낼 수 있다. 엔진의 차이는 엔진 층에서 맞추고, 플랫폼이 받는 결과(TurnResult)는 같은 꼴로 만든다.

## Codex는 허락을 묻지 않고 웹을 검색했다 (2026-10-21)

- 증상: "인터넷은 거절" 규칙을 걸었는데 Codex가 웹 페이지의 제목을 가져왔다. 허락 요청은 오지 않았고, 쓴 도구에는 "Web search"만 있었다.
- 근본 원인: Codex는 모델 쪽 웹 검색 도구를 쓴다. Codex 도움말에도 "no per-call approval"이라고 적혀 있다. 이 도구는 ACP의 허락 요청을 거치지 않으므로 플랫폼의 규칙과 사람이 막을 수 없다.
- 해결: 샌드박스 `config.toml`의 관리 블록에 `web_search = "disabled"`를 넣는다(`engines/codex.py`). 그 뒤 Codex는 `curl` 같은 명령으로 인터넷에 가려 했고, 그 명령은 허락을 물었다. 명령에 든 주소는 `ToolRequest.url`에 넣어서, `request.url` 한 줄로 어느 엔진의 인터넷이든 막을 수 있게 했다.
- 교훈: 엔진이 허락 없이 쓰는 도구가 있는지 엔진마다 확인한다. 허락을 거치지 않는 도구는 엔진 설정에서 끈다.

## Codex 샌드박스에 개인 스킬, 계정 플러그인, Apps 도구가 실렸다 (2026-10-21)

- 증상: 플랫폼 안의 Codex 세션 기록에 이 컴퓨터의 개인 스킬(`~/.agents/skills`의 computer-use, orca-cli, unity-cli 같은 것)과 ChatGPT 계정의 플러그인(figma, higgsfield 같은 것)이 들어 있었다. 웹 검색을 끈 뒤에도 Codex는 `mcp.codex_apps.search_service.web_run` 도구로 허락 없이 웹 페이지를 가져왔다.
- 근본 원인: `CODEX_HOME`을 샌드박스로 바꿔도 Codex는 홈 폴더의 `~/.agents/skills`를 따로 읽는다. 계정 플러그인(`remote_plugin`), 플러그인(`plugins`), Apps(`apps`), 기억(`memories`) 기능이 기본으로 켜져 있다. `skip_host_skill_discovery`(개발 중 기능)를 켜도 개인 스킬은 빠지지 않았다.
- 해결: `engines/codex.py`가 Codex를 실행할 때 `HOME`을 샌드박스 홈으로 바꾼다(npx 캐시는 원래 자리). 관리 블록에 `features.apps`, `features.plugins`, `features.remote_plugin`, `features.memories`를 `false`로 넣는다. 세션 기록에서 개인 스킬, 계정 플러그인, Apps 도구가 0번 나오는 것을 확인했다. Kiro와 Claude의 기록에는 개인 스킬이 없었다.
- 교훈: 샌드박스가 깨끗한지는 설정 폴더 하나로 판단하지 않는다. 엔진이 읽는 모든 자리(홈 폴더, 계정, 기능 플래그)를 세션 기록으로 확인한다.
