# acp-starter

내 프로그램에서 AI 에이전트를 부르는 가장 작은 Python 예제다. ACP(Agent Client Protocol)로 Kiro, Claude, Codex 가운데 하나와 대화한다. 각자 가진 계정이나 구독으로 쓴다.

에이전트가 생각하고, 도구를 고르고, 자료를 읽는다. 이 레포의 코드는 질문을 보내고, 답을 받고, 도구를 써도 되는지 정한다. 화면, 실행 시각, 결과를 보낼 곳은 내가 만든다.

처음에는 이 예제로 간단한 챗봇을 돌려 본다. 그다음에 코드를 바꿔 가며 내가 원하는 시스템으로 키운다.

## 샌드박스: 깨끗한 상태로 시작한다

에이전트마다 이 레포 안의 `.homes/<이름>/`을 설정 폴더로 쓴다. 그래서 내 컴퓨터에 원래 있던 전역 설정, 스킬, 플러그인, 기억, MCP 서버를 가져오지 않는다. `.homes/`는 `.gitignore`에 들어 있다.

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

python chat.py claude               # 대화. 에이전트 이름을 빼면 kiro
python run_once.py codex            # workspace/task.md를 한 번 맡기고 결과를 workspace/outbox/에 남긴다
python run_once.py kiro "질문"      # 질문을 바로 맡긴다
python -m unittest discover tests   # 가짜 에이전트로 확인한다. 사용량이 없다
```

macOS에서 `python`이 없으면 `python3`을 쓴다.

## 연습 순서

| 단계 | 하는 일 | 바꾸는 곳 |
|---|---|---|
| 1. 챗봇 | 내 계정의 에이전트를 골라 대화한다 | 에이전트 이름만 |
| 2. 허락 | 파일 쓰기와 명령 실행을 y/n으로 정해 본다 | 없음. 안전 모드에서 체험한다 |
| 3. 규칙 | 허락 기준을 코드로 정한다 | `on_permission` |
| 4. 혼자 돌기 | 정해진 때에 돌고 결과를 받는다 | `run_once.py`, OS 스케줄러 |
| 5. 키우기 | 내 일에 맞게 화면, 자료, 연결을 바꾼다 | 어디든 |

## 파일

| 파일 | 하는 일 |
|---|---|
| `acp_client.py` | ACP 클라이언트. 에이전트를 샌드박스 홈으로 실행하고, 안전 모드로 바꾸고, 메시지를 주고받는다 |
| `agents.json` | 에이전트마다 실행 명령, 샌드박스 홈 환경변수, 안전 모드, 로그인 명령 |
| `login.py` | 샌드박스 홈에 로그인하거나 로그인 상태를 본다 |
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
| 에이전트의 역할 | Kiro는 `starter.json`의 `prompt`. Claude는 `workspace/CLAUDE.md`, Codex는 `workspace/AGENTS.md`를 만들어 적는다 |
| 허락하는 기준 | `on_permission` 함수. 예: 특정 명령만 허락한다 |
| 안전 모드 | `agents.json`의 `safe_mode` |
| 결과를 받는 곳 | `run_once.py`의 끝. 파일 대신 메일이나 메신저로 보낼 수 있다 |
| 정해진 때의 실행 | OS 스케줄러에 `run_once.py`를 등록한다. macOS·Linux는 `cron`, Windows는 작업 스케줄러 |
| 근거 자료 | `workspace/`에 자료를 넣고 지시문에서 그 자료를 쓰게 한다 |

## 주의

- 이 레포는 공개다. 토큰, 비밀번호, 개인 정보를 커밋하지 않는다. `.homes/`와 `.env`는 `.gitignore`에 들어 있다.
- `.homes/`에는 로그인 정보가 들어 있을 수 있다. 다른 사람에게 이 폴더를 주지 않는다.
- `safe_mode`를 Claude의 `bypassPermissions`나 Codex의 `agent-full-access`로 바꾸지 않는다. 모든 도구를 묻지 않고 허락한다.
- 구독 계정의 사용 규칙은 바뀔 수 있다. 쓰기 전에 각 서비스의 안내를 확인한다. Claude는 2026-10-07 도움말 센터 기준으로 Agent SDK를 플랜 사용 한도 안에서 쓸 수 있다.
- 이 예제는 macOS에서 실행해 확인했다. Windows에서는 실행해 보지 않았다.
- 답을 기다리는 시간 제한과 중간에 멈추기(`session/cancel`)는 다루지 않는다. `run_once.py`만 300초가 지나면 연결을 끊는다.

## 참고

- Agent Client Protocol: https://agentclientprotocol.com/
- Kiro ACP 문서: https://kiro.dev/docs/cli/acp/
- Claude 어댑터: https://github.com/agentclientprotocol/claude-agent-acp
- Codex 어댑터: https://github.com/agentclientprotocol/codex-acp
