# acp-starter

내 일을 위한 AI 에이전트 플랫폼의 출발점이다. ACP(Agent Client Protocol)로 Kiro, Claude, Codex 가운데 하나를 부르고, 각자 가진 계정이나 구독으로 쓴다. 브라우저로 여는 작은 대시보드와 터미널 예제가 함께 들어 있다.

에이전트가 생각하고, 도구를 고르고, 자료를 읽는다. 이 레포의 코드는 질문을 보내고, 답을 받고, 도구를 써도 되는지 정한다. 화면, 실행 시각, 결과를 보낼 곳은 내가 만든다.

처음 열면 기본 기능만 있는 빈 플랫폼이다. 대화하고, 허락하고, 일을 정해진 시각에 돌리고, 결과를 모아 본다. 그다음에 화면과 코드를 바꿔 가며 내가 원하는 시스템으로 키운다.

## 샌드박스: 깨끗한 상태로 시작한다

에이전트마다 이 레포 안의 `.homes/<이름>/`을 설정 폴더로 쓴다. 그래서 내 컴퓨터에 원래 있던 전역 설정, 스킬, 플러그인, 기억, MCP 서버를 가져오지 않는다. `.homes/`는 `.gitignore`에 들어 있다.

Claude는 작업 폴더의 상위 폴더를 거슬러 올라가며 `CLAUDE.md`와 `.claude/CLAUDE.md`를 읽는다. 작업 폴더가 홈 폴더 아래에 있으면 `~/.claude/CLAUDE.md`까지 읽힌다. 그래서 Claude에는 `agents.json`의 `session_meta`로 `settingSources: []`를 넘겨 설정 파일을 읽지 않게 했다. 내 설정을 가져와 쓰는 기능은 나중에 더한다.

| 에이전트 | 샌드박스 홈을 가리키는 환경변수 | 로그인 |
|---|---|---|
| Kiro | `KIRO_HOME` | 평소 Kiro CLI 로그인을 그대로 쓴다 |
| Claude | `CLAUDE_CONFIG_DIR` | 샌드박스에 한 번 따로 로그인한다 |
| Codex | `CODEX_HOME` | 샌드박스에 한 번 따로 로그인한다 |

연결하면 바로 안전 모드로 바꾼다. Claude와 Codex는 기본 모드에서 명령을 묻지 않고 실행하기 때문이다.

| 에이전트 | 안전 모드 | 묻는 것 |
|---|---|---|
| Kiro | `starter.json`의 `allowedTools`에 `read`만 | `read` 밖의 도구 |
| Claude | `default` | 파일 고치기, 명령 실행. 단 `date` 같은 읽기 전용 명령은 묻지 않고 실행한다 |
| Codex | `read-only` | 파일 고치기, 인터넷 접근. 읽기 명령은 묻지 않고 읽기만 되는 샌드박스 안에서 실행한다 |

2026-10-20 macOS에서 확인한 결과: 세 에이전트 모두 안전 모드에서 `out.txt`를 쓰기 전에 허락을 물었고, 거절하자 파일이 생기지 않았다.

## 준비

- Python 3.10 이상. 설치할 Python 패키지는 없다.
- 쓸 에이전트 하나 이상:

| 에이전트 | 필요한 것 | 계정 |
|---|---|---|
| Kiro | [Kiro CLI](https://kiro.dev/docs/getting-started/installation/) | Kiro 계정 |
| Claude | Node.js(`npx` 포함), [Claude Code](https://code.claude.com/docs) (`claude` 명령) | Claude Pro·Max 구독 |
| Codex | Node.js(`npx` 포함), [Codex CLI](https://developers.openai.com/codex/cli) (`codex` 명령) | ChatGPT 구독 |

Claude와 Codex의 ACP 어댑터는 처음 실행할 때 `npx`가 내려받는다. 버전은 `agents.json`에 고정했다.

## 실행

```sh
git clone https://github.com/nxtcloud-edu/acp-starter.git
cd acp-starter

python login.py claude              # 샌드박스에 로그인 (claude, codex만. 처음 한 번)
python login.py claude --status     # 샌드박스의 로그인 상태

python dashboard.py                 # 대시보드. 브라우저에서 http://127.0.0.1:8765 이 열린다

python chat.py claude               # 대화. 에이전트 이름을 빼면 kiro
python run_once.py codex            # workspace/task.md를 한 번 맡기고 결과를 workspace/outbox/에 남긴다
python run_once.py kiro "질문"      # 질문을 바로 맡긴다
python -m unittest discover tests   # 가짜 에이전트로 확인한다. 사용량이 없다
```

macOS에서 `python`이 없으면 `python3`을 쓴다. Codex 로그인 창이 열리지 않으면 `CODEX_HOME=.homes/codex codex login --device-auth`로 기기 코드 로그인을 한다.

## 대시보드

`python dashboard.py`를 실행하면 브라우저에 대시보드가 열린다. 끝내려면 터미널에서 Ctrl+C를 누른다.

| 자리 | 하는 일 |
|---|---|
| 왼쪽 위 에이전트 | 에이전트를 고르고 연결한다. 이름 옆에 샌드박스의 로그인 상태가 나온다 |
| 가운데 대화 | 질문을 보내고 답을 받는다. 에이전트가 쓴 도구가 한 줄씩 나온다 |
| 허락 카드 | 에이전트가 허락을 물으면 카드가 뜬다. 허락이나 거절을 누른다. 5분 안에 누르지 않으면 거절한다 |
| 왼쪽 가운데 일 | `tasks/`의 일 목록. 실행을 누르면 바로 돌고, `time`이 있으면 대시보드가 켜져 있는 동안 매일 그 시각에 돈다 |
| 왼쪽 아래 결과함 | `workspace/outbox/`의 결과 파일. 누르면 가운데에 내용이 나온다 |

일을 돌릴 때는 사람이 없는 것으로 보고, 허락이 필요한 도구는 모두 거절하고 결과 파일에 적는다. 대시보드를 켜기 전에 이미 지난 오늘의 시각은 건너뛴다. 꺼져 있던 동안 놓친 실행은 나중에 몰아서 하지 않는다.

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
| `GET /api/agents` | 에이전트 목록과 로그인 상태 | `{"agents": [{"name", "loggedIn"}], "current", "state"}` |
| `POST /api/session` `{"agent"}` | 그 에이전트에 연결 | `202`. 연결 결과는 사건으로 온다 |
| `POST /api/prompt` `{"text"}` | 질문 보내기 | `202`. 준비되지 않았으면 `409` |
| `POST /api/permissions/{번호}` `{"allow": true}` | 허락 카드에 답하기 | `200`. 기다리는 요청이 없으면 `404` |
| `GET /api/events?after={번호}` | 그 번호 뒤의 사건. 새 사건이 없으면 15초까지 기다린다 | `{"events", "last", "state", "agent"}` |
| `GET /api/tasks` | 일 목록 | `{"tasks": [{"name", "agent", "time", "prompt", "lastRun"}]}` |
| `POST /api/tasks/{이름}/run` | 일을 바로 실행 | `202` |
| `GET /api/outbox` | 결과 파일 목록 | `{"files": [{"name"}]}` |
| `GET /api/outbox/{파일 이름}` | 결과 파일 내용 | `{"name", "text"}` |

사건의 종류(`type`): `status`(연결 상태), `user`(보낸 질문), `text`(답의 조각), `tool`(쓴 도구), `permission`(허락 요청), `permission_result`(허락 결과), `done`(차례 끝과 쓴 양), `task`(일의 시작과 끝).

## 연습 순서

| 단계 | 하는 일 | 바꾸는 곳 |
|---|---|---|
| 1. 챗봇 | 내 계정의 에이전트를 골라 대화한다 | 에이전트 이름만 |
| 2. 허락 | 파일 쓰기와 명령 실행을 y/n으로 정해 본다 | 없음. 안전 모드에서 체험한다 |
| 3. 규칙 | 허락 기준을 코드로 정한다 | `on_permission` |
| 4. 혼자 돌기 | 정해진 때에 돌고 결과를 받는다 | `tasks/`의 일 파일, 또는 `run_once.py`와 OS 스케줄러 |
| 5. 키우기 | 내 일에 맞게 화면, 자료, 연결을 바꾼다 | `app/static/`, `dashboard.py`, 어디든 |

2단계부터는 대시보드에서 해도 되고 터미널 예제로 해도 된다.

## 파일

| 파일 | 하는 일 |
|---|---|
| `acp_client.py` | ACP 클라이언트. 에이전트를 샌드박스 홈으로 실행하고, 안전 모드로 바꾸고, 메시지를 주고받는다 |
| `agents.json` | 에이전트마다 실행 명령, 샌드박스 홈 환경변수, 안전 모드, 로그인 명령 |
| `login.py` | 샌드박스 홈에 로그인하거나 로그인 상태를 본다 |
| `dashboard.py` | 대시보드의 서버. JSON API, 대화 하나, 일 실행, 스케줄, 결과함 |
| `app/static/` | 대시보드의 화면(`index.html`, `style.css`, `app.js`). 마음대로 바꾼다 |
| `runner.py` | 사람 없이 일을 한 번 돌리는 공용 코드. `run_once.py`와 대시보드가 함께 쓴다 |
| `tasks/` | 맡길 일 파일. 예: `마감_브리핑.md` |
| `chat.py` | 예제 1. 사람이 있는 대화. 허락이 필요한 도구는 사람에게 묻는다 |
| `run_once.py` | 예제 2. 사람이 없는 한 번 실행. 허락이 필요한 도구는 모두 거절하고 결과를 파일로 남긴다 |
| `workspace/` | 에이전트가 일하는 폴더 |
| `workspace/.kiro/agents/starter.json` | Kiro 에이전트 설정. 지시문, 쓸 수 있는 도구, 묻지 않고 쓰는 도구 |
| `workspace/notes.md`, `workspace/task.md` | 예제 자료와 예제 일 |
| `tests/` | 가짜 에이전트(`fake_agent.py`)와 테스트 |

## ACP 흐름

메시지는 JSON 한 줄씩 표준 입출력으로 주고받는다(JSON-RPC 2.0). 세 에이전트가 같은 흐름을 쓴다.

| 순서 | 메시지 | 보내는 쪽 | 뜻 |
|---|---|---|---|
| 1 | `initialize` | 내 코드 | 내 코드가 해 줄 수 있는 일을 알린다 |
| 2 | `session/new` | 내 코드 | 작업 폴더를 정하고 대화 하나를 연다 |
| 3 | `session/set_mode` | 내 코드 | 안전 모드로 바꾼다(Claude, Codex) |
| 4 | `session/prompt` | 내 코드 | 질문을 보낸다 |
| 5 | `session/update` | 에이전트 | 답의 조각(`agent_message_chunk`), 도구 사용(`tool_call`), 컨텍스트 사용량(`usage_update`)을 알린다 |
| 6 | `session/request_permission` | 에이전트 | 도구를 써도 되는지 묻는다. 내 코드가 허락하거나 거절한다 |
| 7 | `session/prompt`의 응답 | 에이전트 | 이번 차례가 끝났다(`stopReason`) |

허락 요청의 선택지 이름(`optionId`)은 에이전트마다 다르다. 종류(`kind`)는 같다. 그래서 이 예제는 `allow_once`와 `reject_once` 종류로 고른다.

## 바꿔 볼 곳

| 바꿀 것 | 고칠 곳 |
|---|---|
| 에이전트의 역할 | Kiro는 `starter.json`의 `prompt`. Codex는 `workspace/AGENTS.md`를 만들어 적는다. Claude는 설정 파일을 읽지 않게 해 두어서, 지금은 일 파일이나 질문에 역할을 적는다 |
| 화면 | `app/static/`. 예: 결과를 표로 보여 주기, 일 만들기 칸 더하기 |
| 새 기능 | `dashboard.py`에 API를 더하고 `app/static/app.js`에서 부른다 |
| 허락하는 기준 | `on_permission` 함수. 예: 특정 명령만 허락한다 |
| 안전 모드 | `agents.json`의 `safe_mode` |
| 결과를 받는 곳 | `runner.py`의 `run_task` 끝. 파일 대신 메일이나 메신저로 보낼 수 있다 |
| 정해진 때의 실행 | `tasks/`의 `time`. 대시보드를 켜 두지 않을 때는 OS 스케줄러에 `run_once.py`를 등록한다(macOS·Linux는 `cron`, Windows는 작업 스케줄러) |
| 근거 자료 | `workspace/`에 자료를 넣고 지시문에서 그 자료를 쓰게 한다 |

## 주의

- 이 레포는 공개다. 토큰, 비밀번호, 개인 정보를 커밋하지 않는다. `.homes/`와 `.env`는 `.gitignore`에 들어 있다.
- `.homes/`에는 로그인 정보가 들어 있을 수 있다. 다른 사람에게 이 폴더를 주지 않는다.
- `safe_mode`를 Claude의 `bypassPermissions`나 Codex의 `agent-full-access`로 바꾸지 않는다. 모든 도구를 묻지 않고 허락한다.
- 구독 계정의 사용 규칙은 바뀔 수 있다. 쓰기 전에 각 서비스의 안내를 확인한다. Claude는 2026-10-07 도움말 센터 기준으로 Agent SDK를 플랜 사용 한도 안에서 쓸 수 있다.
- 이 예제는 macOS에서 실행해 확인했다. Windows에서는 실행해 보지 않았다.
- 답을 기다리는 시간 제한과 중간에 멈추기(`session/cancel`)는 다루지 않는다. 일 실행만 300초가 지나면 연결을 끊는다.
- 대시보드는 내 컴퓨터(`127.0.0.1`)에서만 열린다. 대화는 한 번에 하나다.

## 참고

- Agent Client Protocol: https://agentclientprotocol.com/
- Kiro ACP 문서: https://kiro.dev/docs/cli/acp/
- Claude 어댑터: https://github.com/agentclientprotocol/claude-agent-acp
- Codex 어댑터: https://github.com/agentclientprotocol/codex-acp
