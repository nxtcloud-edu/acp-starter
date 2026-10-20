# kiro-acp-starter

내 프로그램에서 Kiro 에이전트를 부르는 가장 작은 Python 예제다. Kiro CLI와 ACP(Agent Client Protocol)로 대화한다.

Kiro CLI 안의 에이전트가 생각하고, 도구를 고르고, 자료를 읽는다. 이 레포의 코드는 질문을 보내고, 답을 받고, 도구를 써도 되는지 정한다. 화면, 실행 시각, 결과를 보낼 곳은 내가 만든다.

## 준비

- Python 3.10 이상. 설치할 패키지는 없다.
- Kiro CLI. 설치: https://kiro.dev/docs/getting-started/installation/
- Kiro CLI 로그인. 터미널에서 `kiro-cli whoami`를 실행해 로그인한 계정이 나오는지 본다. 나오지 않으면 `kiro-cli login`을 실행한다.

## 실행

```sh
git clone https://github.com/nxtcloud-edu/kiro-acp-starter.git
cd kiro-acp-starter

python chat.py                 # 터미널에서 대화한다. 도구 허락을 y/n으로 정한다
python run_once.py             # workspace/task.md를 한 번 맡기고 결과를 workspace/outbox/에 남긴다
python run_once.py "질문"      # 질문을 바로 맡긴다
python -m unittest discover tests   # 가짜 에이전트로 확인한다. 크레딧을 쓰지 않는다
```

macOS에서 `python`이 없으면 `python3`을 쓴다.

질문 하나에 쓰는 크레딧은 이 예제로 확인했을 때 0.04~0.1이었다. 실행이 끝날 때마다 화면이나 결과 파일에 나온다.

## 파일

| 파일 | 하는 일 |
|---|---|
| `acp_client.py` | ACP 클라이언트. Kiro CLI를 실행하고 메시지를 주고받는다 |
| `chat.py` | 예제 1. 사람이 있는 대화. 허락이 필요한 도구는 사람에게 묻는다 |
| `run_once.py` | 예제 2. 사람이 없는 한 번 실행. 허락이 필요한 도구는 모두 거절하고 결과를 파일로 남긴다 |
| `workspace/` | 에이전트가 일하는 폴더 |
| `workspace/.kiro/agents/starter.json` | 에이전트 설정. 지시문, 쓸 수 있는 도구, 묻지 않고 쓰는 도구 |
| `workspace/.kiro/settings/cli.json` | 이 폴더 밖의 기본 자료를 에이전트에게 넘기지 않는 설정 |
| `workspace/notes.md`, `workspace/task.md` | 예제 자료와 예제 일 |
| `tests/` | 가짜 에이전트(`fake_agent.py`)와 테스트 |

## ACP 흐름

메시지는 JSON 한 줄씩 표준 입출력으로 주고받는다(JSON-RPC 2.0).

| 순서 | 메시지 | 보내는 쪽 | 뜻 |
|---|---|---|---|
| 1 | `initialize` | 내 코드 | 내 코드가 해 줄 수 있는 일을 알린다 |
| 2 | `session/new` | 내 코드 | 작업 폴더를 정하고 대화 하나를 연다 |
| 3 | `session/prompt` | 내 코드 | 질문을 보낸다 |
| 4 | `session/update` | 에이전트 | 답의 조각(`agent_message_chunk`), 도구 사용(`tool_call`, `tool_call_update`)을 알린다 |
| 5 | `session/request_permission` | 에이전트 | 도구를 써도 되는지 묻는다. 내 코드가 허락하거나 거절한다 |
| 6 | `session/prompt`의 응답 | 에이전트 | 이번 차례가 끝났다(`stopReason`) |

`_kiro.dev/`로 시작하는 메시지는 Kiro가 더한 것이다. 이 예제는 그 가운데 크레딧(`_kiro.dev/metadata`)만 읽는다.

## 바꿔 볼 곳

| 바꿀 것 | 고칠 곳 |
|---|---|
| 에이전트의 역할 | `starter.json`의 `prompt` |
| 쓸 수 있는 도구 | `starter.json`의 `tools`. 예: `read`, `write`, `shell`, `grep`, `glob`, `web_fetch` |
| 묻지 않고 쓰는 도구 | `starter.json`의 `allowedTools` |
| 허락하는 기준 | `on_permission` 함수. 예: 특정 명령만 허락한다 |
| 결과를 받는 곳 | `run_once.py`의 끝. 파일 대신 메일이나 메신저로 보낼 수 있다 |
| 정해진 때의 실행 | OS 스케줄러에 `run_once.py`를 등록한다. macOS·Linux는 `cron`, Windows는 작업 스케줄러 |
| 근거 자료 | `workspace/`에 자료를 넣고 지시문에서 그 자료를 쓰게 한다 |

## 주의

- 이 레포는 공개다. 토큰, 비밀번호, 개인 정보를 커밋하지 않는다. 시크릿은 환경변수나 `.env` 파일에 두고, `.env`는 `.gitignore`에 들어 있다.
- `allowedTools`에 `shell`이나 `write`를 넣으면 에이전트가 묻지 않고 명령을 실행하거나 파일을 고친다. 넣기 전에 무엇을 막을지 `on_permission`에 먼저 정한다.
- `kiro-cli acp --trust-all-tools`를 쓰지 않는다. 모든 도구를 묻지 않고 허락한다.
- 이 예제는 macOS에서 실행해 확인했다. Windows에서는 실행해 보지 않았다.
- 이 예제는 답을 기다리는 시간 제한과 중간에 멈추기(`session/cancel`)를 다루지 않는다. `run_once.py`만 300초가 지나면 연결을 끊는다.

## 참고

- Kiro ACP 문서: https://kiro.dev/docs/cli/acp/
- Agent Client Protocol: https://agentclientprotocol.com/
