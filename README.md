# acp-starter

내 일을 위한 AI 에이전트 플랫폼의 출발점이다. ACP(Agent Client Protocol)로 Kiro, Claude, Codex 가운데 하나를 부르고, 각자 가진 계정이나 구독으로 쓴다. 브라우저로 여는 작은 대시보드와 터미널 예제가 함께 들어 있다.

에이전트가 생각하고, 도구를 고르고, 자료를 읽는다. 이 레포의 코드는 질문을 보내고, 답을 받고, 도구를 써도 되는지 정한다. 이름, 업무, 화면, 실행 시각, 결과를 보낼 곳은 내가 만든다.

처음 열면 기본 기능만 있는 빈 플랫폼이다. 로그인하고, 대화하고, 스킬을 쓰고, 허락하고, 일을 정해진 시각에 돌리고, 결과를 모아 본다. 그다음에 이 레포를 포크해서 내 업무 전용 플랫폼으로 키운다. 어디를 바꿀 수 있는지는 [만들_곳.md](만들_곳.md)에 있다. 최종 과제 안내는 [안내/](안내/)에 있다.

## 샌드박스: 깨끗한 상태로 시작한다

에이전트마다 이 레포 안의 `.homes/<이름>/`을 설정 폴더로 쓴다. 그래서 내 컴퓨터에 원래 있던 전역 설정, 스킬, 플러그인, 기억, MCP 서버를 가져오지 않는다. `.homes/`는 `.gitignore`에 들어 있다.

| 에이전트 | 샌드박스 홈을 가리키는 환경변수 | 로그인 | 지침 파일을 막는 방법 |
|---|---|---|---|
| Kiro | `KIRO_HOME` | 평소 Kiro CLI 로그인을 그대로 쓴다 | Kiro 엔진 설정(`engine.json`)의 `resources`가 비어 있다 |
| Claude | `CLAUDE_CONFIG_DIR` | 샌드박스에 한 번 따로 로그인한다 | `settingSources: []`(설정 파일과 `CLAUDE.md`를 읽지 않는다) |
| Codex | `CODEX_HOME` | 샌드박스에 한 번 따로 로그인한다 | 샌드박스의 `config.toml`에 `project_doc_max_bytes = 0` |

Claude는 작업 폴더의 상위 폴더를 거슬러 올라가며 `CLAUDE.md`를 읽는다. 그래서 `settingSources: []`가 없으면 홈 폴더의 전역 지침까지 실린다([GOTCHAS.md](GOTCHAS.md)). 2026-10-21 확인에서 codex-acp 2.2.2는 `AGENTS.md`를 읽지 않았다. 어댑터가 바뀌어도 레포의 개발 안내(`AGENTS.md`)를 읽지 않게 `config.toml`로 한 번 더 막아 두었다. 세 에이전트 모두 개발 안내에 넣은 표시 낱말을 보지 못했다.

에이전트의 역할과 규칙은 지침 파일이 아니라 플랫폼이 직접 보낸다. 대화를 시작할 때 `custom/업무.md`와 스킬 목록을 "플랫폼 안내"로 만들어 첫 질문 앞에 붙인다. ACP에는 시스템 프롬프트 칸이 없기 때문이다. 세 에이전트가 같은 방법으로 안내를 받는다.

연결하면 바로 안전 모드로 바꾼다. Claude와 Codex는 기본 모드에서 명령을 묻지 않고 실행하기 때문이다.

| 에이전트 | 안전 모드 | 묻는 것 |
|---|---|---|
| Kiro | `engine.json`의 `allowedTools`에 `read`만 | `read` 밖의 도구 |
| Claude | `default` | 파일 고치기, 명령 실행. 단 `date` 같은 읽기 전용 명령은 묻지 않고 실행한다 |
| Codex | `read-only` | 파일 고치기, 인터넷 접근. 읽기 명령은 묻지 않고 읽기만 되는 샌드박스 안에서 실행한다 |

허락을 물으면 플랫폼은 먼저 `custom/rules.py`에 묻는다. 규칙이 `"ask"`를 돌려주면 대시보드에 허락 카드가 뜬다.

## 준비

- Python 3.10 이상. 설치할 Python 패키지는 없다.
- 쓸 에이전트 하나 이상:

| 에이전트 | 필요한 것 | 계정 |
|---|---|---|
| Kiro | [Kiro CLI](https://kiro.dev/docs/getting-started/installation/) | Kiro 계정 |
| Claude | Node.js(`npx` 포함), [Claude Code](https://code.claude.com/docs) (`claude` 명령) | Claude Pro·Max 구독 |
| Codex | Node.js(`npx` 포함), [Codex CLI](https://developers.openai.com/codex/cli) (`codex` 명령) | ChatGPT 구독 |

Claude와 Codex의 ACP 어댑터는 처음 실행할 때 `npx`가 내려받는다. 버전은 `engines.json`에 고정했다.

## 실행

```sh
git clone https://github.com/<내 GitHub ID>/acp-starter.git   # 포크한 내 레포
cd acp-starter
python dashboard.py                 # 대시보드. 브라우저에서 http://127.0.0.1:8765 이 열린다
```

macOS에서 `python`이 없으면 `python3`을 쓴다. 끝내려면 터미널에서 Ctrl+C를 누른다.

### 로그인

대시보드 왼쪽 위에 에이전트마다 로그인 상태가 나온다. "로그인 필요"이면 "로그인"을 누른다. 대화 칸에 로그인 카드가 뜬다.

| 에이전트 | 로그인 카드 |
|---|---|
| Codex | 주소와 기기 코드가 나온다. 주소를 열고 ChatGPT 계정으로 로그인한 뒤 코드를 넣는다 |
| Claude | 주소가 나온다(브라우저가 저절로 열리기도 한다). Claude 계정으로 로그인한 뒤 화면에 나온 코드를 복사해 카드의 칸에 붙여 넣는다 |
| Kiro | 화면에서 로그인하지 않는다. Kiro 로그인은 컴퓨터 전체에 걸리므로 터미널에서 `kiro-cli login`을 실행한다 |

이미 로그인된 에이전트는 로그인을 다시 시작할 수 없다. Codex는 로그인을 시작하자마자 있던 로그인을 지우기 때문이다. 다른 계정으로 바꾸려면 "로그아웃"을 먼저 누른다.

터미널로도 할 수 있다: `python login.py claude`(로그인), `python login.py codex --status`(상태).

### 터미널 예제

```sh
python chat.py claude               # 대화. 에이전트 이름을 빼면 kiro
python run_once.py codex            # workspace/task.md를 한 번 맡기고 결과를 workspace/outbox/에 남긴다
python run_once.py kiro "질문"      # 질문을 바로 맡긴다
python -m unittest discover tests   # 가짜 에이전트로 확인한다. 사용량이 없다
```

## 대시보드

| 자리 | 하는 일 |
|---|---|
| 맨 위 | 이름과 한 줄 소개. `custom/brand.json`에서 바꾼다 |
| 에이전트 | 로그인 상태와 로그인·로그아웃. 에이전트를 골라 "연결"을 누른다 |
| 스킬 | `workspace/skills/`의 스킬. "해 보기"를 누르면 예시 요청이 입력칸에 들어간다 |
| 일 | `tasks/`의 일. "실행"을 누르면 바로 돌고, `time`이 있으면 대시보드가 켜져 있는 동안 매일 그 시각에 돈다 |
| 결과함 | `workspace/outbox/`의 md, json, html. 누르면 가운데에 내용이 나오고, html은 새 탭에서 열린다 |
| 가운데 대화 | 질문과 답, 쓴 도구, "플랫폼이 보낸 안내", 허락 카드, 로그인 카드 |

허락 카드는 5분 안에 누르지 않으면 거절한다. 일을 돌릴 때는 사람이 없는 것으로 본다. 그래서 `custom/rules.py`가 `"ask"`를 돌려주면 거절하고 결과 파일에 적는다. 대시보드를 켜기 전에 이미 지난 오늘의 시각은 건너뛴다. 꺼져 있던 동안 놓친 실행은 나중에 몰아서 하지 않는다.

### 처음 해 볼 것: 스킬로 도구 호출 보기

1. 에이전트에 연결한다.
2. 스킬 `memo-to-json`의 "해 보기"를 누르고 보낸다. 에이전트가 `SKILL.md`와 메모 사진(`workspace/자료/발표준비/내준비메모.jpg`)을 읽는다.
3. 에이전트가 검사 스크립트를 실행하려 하면 허락 카드가 뜬다. 명령을 읽고 "허락"을 누른다.
4. 결과함에 `.json`이 생긴다. `data-to-html`도 같은 순서로 해 보면 `.html` 리포트가 생긴다.

AI가 읽고 정리하는 일과, 코드가 검사하고 저장하는 일이 나뉘어 있다. 에이전트는 도구를 고르고, 플랫폼은 허락을 묻고, 사람이 정한다.

### 일 파일

`tasks/` 아래에 `.md` 파일 하나가 일 하나다. 파일 이름이 일의 이름이다. 첫머리의 `---` 사이에 에이전트와 매일 실행할 시각을 적고, 그 아래에 맡길 내용을 적는다.

```
---
agent: kiro
time: 07:30
---
notes.md를 읽고, 마감이 있는 일만 날짜 순서로 표로 정리해 줘.
```

`agent`를 빼면 `kiro`, `time`을 빼면 직접 실행할 때만 돈다.

### 대시보드 API

서버(`dashboard.py`)는 JSON만 낸다. 화면(`app/static/`)은 이 API를 부르는 클라이언트다. 새 기능은 먼저 API를 더하고, 그다음에 화면에서 그 API를 부른다.

| 요청 | 하는 일 | 응답 |
|---|---|---|
| `GET /api/agents` | 에이전트 목록, 설치·로그인 상태, 로그인 방식 | `{"agents": [{"name", "installed", "loggedIn", "loginMode", "loginCommand", "canLogout"}], "current", "state"}` |
| `POST /api/login/{이름}` | 로그인 시작. 진행은 사건 `login`으로 온다 | `202`. 이미 로그인되어 있으면 `409`, Kiro는 `400` |
| `POST /api/login/{이름}/code` `{"code"}` | Claude 로그인 코드 넘기기 | `202`. 진행 중인 로그인이 없으면 `404` |
| `DELETE /api/login/{이름}` | 진행 중인 로그인 멈추기 | `200` |
| `POST /api/logout/{이름}` | 로그아웃(Claude, Codex) | `200`. Kiro는 `400` |
| `POST /api/session` `{"agent"}` | 그 에이전트에 연결 | `202`. 연결 결과는 사건으로 온다 |
| `POST /api/prompt` `{"text"}` | 질문 보내기 | `202`. 준비되지 않았으면 `409` |
| `POST /api/permissions/{번호}` `{"allow": true}` | 허락 카드에 답하기 | `200`. 기다리는 요청이 없으면 `404` |
| `GET /api/events?after={번호}` | 그 번호 뒤의 사건. 새 사건이 없으면 15초까지 기다린다 | `{"events", "last", "state", "agent"}` |
| `GET /api/brand` | 이름, 한 줄 소개, 색 | `{"name", "tagline", "accent"}` |
| `GET /api/skills` | 스킬 목록 | `{"skills": [{"name", "description", "example", "path"}]}` |
| `GET /api/tasks` | 일 목록 | `{"tasks": [{"name", "agent", "time", "prompt", "lastRun"}]}` |
| `POST /api/tasks/{이름}/run` | 일을 바로 실행 | `202` |
| `GET /api/outbox` | 결과 파일 목록(새것부터) | `{"files": [{"name", "type", "url"}]}` |
| `GET /api/outbox/{파일 이름}` | 결과 파일 내용 | `{"name", "type", "url", "text"}` |
| `GET /outbox/{파일 이름}` | 결과 파일 그대로. 대시보드 API를 부르지 못하게 따로 떼어 연다 | 파일 |

사건의 종류(`type`): `status`(연결 상태), `preamble`(플랫폼 안내), `user`(보낸 질문), `text`(답의 조각), `tool`(쓴 도구), `permission`(허락 요청), `permission_result`(허락 결과), `rule`(규칙이 정한 허락·거절), `rule_error`(규칙 오류), `done`(차례 끝과 쓴 양), `task`(일의 시작과 끝, 보내기 오류), `login`(로그인 진행: `started`, `waiting`, `checking`, `done`, `failed`, `cancelled`, `logged_out`).

## 파일

| 파일 | 하는 일 |
|---|---|
| `custom/` | 내가 먼저 바꾸는 곳. `brand.json`(이름과 색), `업무.md`(업무와 역할), `rules.py`(허락 규칙), `deliver.py`(결과 보내기) |
| `만들_곳.md` | 바꾸거나 더할 수 있는 곳의 지도와 Kiro Crew의 비슷한 위치 |
| `AGENTS.md`, `CLAUDE.md` | 이 레포를 고치는 코딩 에이전트용 개발 안내 |
| `안내/` | 최종 과제 안내와 계획서·기록 틀 |
| `acp_client.py` | ACP 클라이언트. 에이전트를 샌드박스 홈으로 실행하고, 안전 모드로 바꾸고, 메시지를 주고받는다 |
| `custom_loader.py` | `custom/`와 스킬을 읽어 플랫폼에 잇는다. 플랫폼 안내를 만든다 |
| `engines.json` | 에이전트마다 실행 명령, 샌드박스 홈, 안전 모드, 로그인 방식 |
| `dashboard.py` | 대시보드의 서버. JSON API, 대화 하나, 로그인, 일 실행, 스케줄, 결과함 |
| `app/static/` | 대시보드의 화면(`index.html`, `style.css`, `app.js`) |
| `runner.py` | 사람 없이 일을 한 번 돌리는 공용 코드. `run_once.py`와 대시보드가 함께 쓴다 |
| `tasks/` | 맡길 일 파일. 예: `마감_브리핑.md` |
| `login.py`, `chat.py`, `run_once.py` | 터미널 예제: 로그인, 대화, 한 번 실행 |
| `workspace/` | 플랫폼 안 에이전트의 작업 폴더 |
| `workspace/skills/` | 스킬. 수업 스킬 `memo-to-json`, `data-to-html` |
| `workspace/자료/발표준비/` | 스킬을 해 볼 예시 자료(메모 사진, md, csv) |
| `workspace/.kiro/agents/engine.json` | Kiro 에이전트 설정 |
| `tests/` | 가짜 에이전트와 가짜 로그인으로 도는 테스트. `test_safety.py`는 안전 모드를 지킨다 |

## ACP 흐름

메시지는 JSON 한 줄씩 표준 입출력으로 주고받는다(JSON-RPC 2.0). 세 에이전트가 같은 흐름을 쓴다.

| 순서 | 메시지 | 보내는 쪽 | 뜻 |
|---|---|---|---|
| 1 | `initialize` | 내 코드 | 내 코드가 해 줄 수 있는 일을 알린다 |
| 2 | `session/new` | 내 코드 | 작업 폴더를 정하고 대화 하나를 연다 |
| 3 | `session/set_mode` | 내 코드 | 안전 모드로 바꾼다(Claude, Codex) |
| 4 | `session/prompt` | 내 코드 | 질문을 보낸다. 첫 질문에는 플랫폼 안내가 앞에 붙는다 |
| 5 | `session/update` | 에이전트 | 답의 조각(`agent_message_chunk`), 도구 사용(`tool_call`), 컨텍스트 사용량(`usage_update`)을 알린다 |
| 6 | `session/request_permission` | 에이전트 | 도구를 써도 되는지 묻는다. `custom/rules.py`와 사람이 정한다 |
| 7 | `session/prompt`의 응답 | 에이전트 | 이번 차례가 끝났다(`stopReason`) |

허락 요청의 선택지 이름(`optionId`)은 에이전트마다 다르다. 종류(`kind`)는 같다. 그래서 이 예제는 `allow_once`와 `reject_once` 종류로 고른다. 명령이 담긴 자리도 조금씩 다르다. `custom/rules.py`의 머리말에 세 에이전트의 모양을 적어 두었다.

## 주의

- 이 레포는 공개다. 토큰, 비밀번호, 개인 정보, 회사 자료를 커밋하지 않는다. `.homes/`와 `.env`는 `.gitignore`에 들어 있다.
- `.homes/`에는 로그인 정보가 들어 있다. 다른 사람에게 이 폴더를 주지 않는다.
- `safe_mode`를 Claude의 `bypassPermissions`나 Codex의 `agent-full-access`로 바꾸지 않는다. 모든 도구를 묻지 않고 허락한다. 허락을 넓히려면 `custom/rules.py`로 한다.
- 구독 계정의 사용 규칙은 바뀔 수 있다. 쓰기 전에 각 서비스의 안내를 확인한다. Claude는 2026-10-07 도움말 센터 기준으로 Agent SDK를 플랜 사용 한도 안에서 쓸 수 있다.
- 이 예제는 macOS에서 실행해 확인했다. Windows에서는 실행해 보지 않았다.
- 답을 기다리는 시간 제한과 중간에 멈추기(`session/cancel`)는 다루지 않는다. 일 실행만 300초가 지나면 연결을 끊는다.
- 대시보드는 내 컴퓨터(`127.0.0.1`)에서만 열린다. 인증이 없으므로 밖으로 열지 않는다. 대화는 한 번에 하나다.

## 참고

- Agent Client Protocol: https://agentclientprotocol.com/
- Kiro ACP 문서: https://kiro.dev/docs/cli/acp/
- Claude 어댑터: https://github.com/agentclientprotocol/claude-agent-acp
- Codex 어댑터: https://github.com/agentclientprotocol/codex-acp
- Kiro Crew: https://github.com/kirodotdev/KiroCrew
