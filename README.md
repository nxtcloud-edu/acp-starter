# acp-starter

내 일을 위한 AI 에이전트 플랫폼의 출발점이다. 내가 만든 에이전트를 ACP(Agent Client Protocol)로 Kiro, Claude, Codex 가운데 하나에 실어 돌리고, 각자 가진 계정이나 구독으로 쓴다. 브라우저로 여는 작은 대시보드와 터미널 예제가 함께 들어 있다.

처음 열면 기본 기능만 있는 빈 플랫폼이다. 에이전트를 만들고, 엔진에 로그인하고, 대화하고, 스킬을 쓰고, 허락하고, 일을 정해진 시각에 돌리고, 결과를 모아 본다. 그다음에 이 레포를 포크해서 내 업무 전용 플랫폼으로 키운다. 어디를 바꿀 수 있는지는 [만들_곳.md](만들_곳.md)에 있다. 최종 과제 안내는 [안내/](안내/)에 있다.

## 에이전트와 엔진

이 플랫폼은 두 가지를 나눈다.

| 이름 | 뜻 | 어디에 있나 |
|---|---|---|
| 에이전트 | 내가 만드는 것. 이름, 역할, 쓸 스킬, 기본 엔진 | `custom/agents/<이름>.md` |
| 엔진 | 에이전트를 실제로 돌리는 ACP 프로그램. 생각하고 도구를 쓰는 쪽 | `engines.json`(`kiro`, `claude`, `codex`) |

에이전트의 역할, 업무(`custom/업무.md`), 스킬 목록, 앞의 대화는 플랫폼이 엔진에게 보낸다. 허락 규칙, 일 실행, 결과함도 플랫폼이 맡는다. 그래서 **엔진을 바꿔도 플랫폼 기능은 그대로 돈다.** 에이전트의 `engine:` 한 줄을 바꾸거나, 대시보드에서 다른 엔진을 골라 연결하면 된다. 엔진마다 다른 것은 답의 말투와 실력, 쓴 양을 세는 방법, 엔진이 스스로 묻지 않고 하는 일뿐이다.

코드도 이 구분대로 나뉜다.

| 층 | 파일 | 하는 일 |
|---|---|---|
| 엔진 층 | `acp_client.py`, `engines.json`, `workspace/.kiro/agents/engine.json`, `login.py` | 엔진마다 다른 실행 명령, 안전 모드, 로그인, 도구 요청의 모양을 여기서 하나로 맞춘다 |
| 플랫폼 층 | `custom_loader.py`, `dashboard.py`, `runner.py`, `app/static/` | 에이전트, 플랫폼 안내, 허락, 일, 결과, 대화 기록. 엔진 이름을 쓰지 않는다(`tests/test_engine_agnostic.py`가 확인한다) |
| 내 것 | `custom/`, `workspace/skills/`, `workspace/자료/`, `tasks/` | 내 업무에 맞게 바꾸는 곳 |

엔진만이 가진 기능(Kiro의 에이전트 파일, Claude의 `CLAUDE.md`와 스킬, Codex의 `AGENTS.md`)에는 기대지 않는다. 그런 곳에 넣은 지시는 엔진을 바꾸면 사라지기 때문이다.

## 샌드박스: 깨끗한 상태로 시작한다

엔진마다 이 레포 안의 `.homes/<이름>/`을 설정 폴더로 쓴다. 그래서 내 컴퓨터에 원래 있던 전역 설정, 스킬, 플러그인, 기억, MCP 서버를 가져오지 않는다. `.homes/`는 `.gitignore`에 들어 있다.

| 엔진 | 샌드박스 홈을 가리키는 환경변수 | 로그인 | 지침 파일을 막는 방법 |
|---|---|---|---|
| Kiro | `KIRO_HOME` | 평소 Kiro CLI 로그인을 그대로 쓴다 | Kiro 엔진 설정(`engine.json`)의 `resources`와 `prompt`가 비어 있다 |
| Claude | `CLAUDE_CONFIG_DIR` | 샌드박스에 한 번 따로 로그인한다 | `settingSources: []`(설정 파일과 `CLAUDE.md`를 읽지 않는다) |
| Codex | `CODEX_HOME` | 샌드박스에 한 번 따로 로그인한다 | 샌드박스의 `config.toml`에 `project_doc_max_bytes = 0` |

Claude는 작업 폴더의 상위 폴더를 거슬러 올라가며 `CLAUDE.md`를 읽는다. 그래서 `settingSources: []`가 없으면 홈 폴더의 전역 지침까지 실린다([GOTCHAS.md](GOTCHAS.md)). 2026-10-21 확인에서 codex-acp 2.2.2는 `AGENTS.md`를 읽지 않았다. 어댑터가 바뀌어도 레포의 개발 안내(`AGENTS.md`)를 읽지 않게 `config.toml`로 한 번 더 막아 두었다. 세 엔진 모두 개발 안내에 넣은 표시 낱말을 보지 못했다.

ACP에는 시스템 프롬프트 칸이 없다. 그래서 플랫폼은 대화를 시작할 때 "플랫폼 안내"를 만들어 첫 질문 앞에 붙인다. 안내는 업무, 이 에이전트의 역할, 이 에이전트가 쓸 스킬, 결과를 둘 곳, 앞의 대화로 이루어진다. 대시보드에서 펼쳐 보면 실제로 간 글이 보인다.

## 안전 모드와 허락

연결하면 바로 안전 모드로 바꾼다. Claude와 Codex는 기본 모드에서 명령을 묻지 않고 실행하기 때문이다. 세 엔진이 같은 종류의 일을 묻도록 맞춰 두었다.

| 일 | Kiro | Claude | Codex |
|---|---|---|---|
| 파일 읽기 | 묻지 않는다 | 묻지 않는다 | 묻지 않는다 |
| 파일 쓰기 | 묻는다 | 묻는다 | 묻는다 |
| 명령 실행 | 묻는다 | 묻는다. 단 `ls`, `date` 같은 읽기 전용 명령은 묻지 않는다 | 묻는다. 단 읽기 명령은 읽기만 되는 샌드박스 안에서 묻지 않고 실행한다 |
| 인터넷 | 묻는다 | 묻는다 | 읽기만 되는 샌드박스가 막는다. 허락을 묻는지는 확인하지 않았다 |
| 설정 | `engine.json`의 `allowedTools`에 `read`만 | 안전 모드 `default` | 안전 모드 `read-only` |

2026-10-20~21 macOS에서 확인한 결과: 세 엔진 모두 안전 모드에서 파일 쓰기 전에 허락을 물었고, 거절하자 파일이 생기지 않았다. Kiro와 Claude는 인터넷 가져오기도 물었다.

엔진이 허락을 물으면 플랫폼은 그 요청을 엔진과 상관없는 꼴(`ToolRequest`: `kind`, `command`, `path`, `url`)로 바꾼 뒤 `custom/rules.py`에 묻는다. 규칙이 `"ask"`를 돌려주면 대시보드에 허락 카드가 뜬다. 같은 규칙은 어느 엔진에도 똑같이 걸린다.

## 준비

- Python 3.10 이상. 설치할 Python 패키지는 없다.
- 쓸 엔진 하나 이상:

| 엔진 | 필요한 것 | 계정 |
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

대시보드 왼쪽의 "엔진" 칸에 엔진마다 로그인 상태가 나온다. "로그인 필요"이면 "로그인"을 누른다. 대화 칸에 로그인 카드가 뜬다.

| 엔진 | 로그인 카드 |
|---|---|
| Codex | 주소와 기기 코드가 나온다. 주소를 열고 ChatGPT 계정으로 로그인한 뒤 코드를 넣는다 |
| Claude | 주소가 나온다(브라우저가 저절로 열리기도 한다). Claude 계정으로 로그인한 뒤 화면에 나온 코드를 복사해 카드의 칸에 붙여 넣는다 |
| Kiro | 화면에서 로그인하지 않는다. Kiro 로그인은 컴퓨터 전체에 걸리므로 터미널에서 `kiro-cli login`을 실행한다 |

이미 로그인된 엔진은 로그인을 다시 시작할 수 없다. Codex는 로그인을 시작하자마자 있던 로그인을 지우기 때문이다. 다른 계정으로 바꾸려면 "로그아웃"을 먼저 누른다.

터미널로도 할 수 있다: `python login.py claude`(로그인), `python login.py codex --status`(상태).

### 터미널 예제

```sh
python chat.py                                  # 기본_도우미와 대화
python chat.py 메모_정리 --engine claude          # 에이전트는 그대로, 엔진만 바꿔 대화
python run_once.py                              # 기본_도우미에게 workspace/task.md를 한 번 맡기고 결과를 outbox/에 남긴다
python run_once.py 메모_정리 "질문"               # 질문을 바로 맡긴다
python -m unittest discover tests               # 가짜 엔진으로 확인한다. 사용량이 없다
```

## 대시보드

| 자리 | 하는 일 |
|---|---|
| 맨 위 | 이름과 한 줄 소개. `custom/brand.json`에서 바꾼다 |
| 에이전트 | `custom/agents/`의 에이전트. 엔진을 골라 "연결"한다. "고치기"와 "+ 새 에이전트"는 에이전트 파일을 고치거나 만든다 |
| 엔진 | 엔진의 설치·로그인 상태와 로그인·로그아웃 |
| 스킬 | `workspace/skills/`의 스킬. "해 보기"를 누르면 예시 요청이 입력칸에 들어간다 |
| 일 | `tasks/`의 일. "실행"을 누르면 바로 돌고, `time`이 있으면 대시보드가 켜져 있는 동안 매일 그 시각에 돈다 |
| 결과함 | `workspace/outbox/`의 md, json, html. 누르면 가운데에 내용이 나오고, html은 새 탭에서 열린다 |
| 가운데 대화 | 질문과 답, 쓴 도구, "플랫폼이 보낸 안내", 허락 카드, 로그인 카드, 에이전트 양식 |
| 새 대화 | 지금 에이전트의 앞의 대화를 지우고 같은 엔진으로 다시 연결한다 |

허락 카드는 5분 안에 누르지 않으면 거절한다. 일을 돌릴 때는 사람이 없는 것으로 본다. 그래서 `custom/rules.py`가 `"ask"`를 돌려주면 거절하고 결과 파일에 적는다. 대시보드를 켜기 전에 이미 지난 오늘의 시각은 건너뛴다. 꺼져 있던 동안 놓친 실행은 나중에 몰아서 하지 않는다.

대화는 한 번에 하나다. 플랫폼은 에이전트마다 앞의 대화(최근 12개, 8000자 안)를 기억한다. 같은 에이전트에 다시 연결하면, 엔진이 달라도 그 대화를 플랫폼 안내에 넣어 이어 간다. 이 기억은 대시보드를 끄면 사라진다.

### 처음 해 볼 것

1. "엔진" 칸에서 로그인한 엔진을 확인한다.
2. 에이전트 `메모_정리`에 그 엔진을 골라 연결한다.
3. 스킬 `memo-to-json`의 "해 보기"를 누르고 보낸다. 에이전트가 `SKILL.md`와 메모 사진(`workspace/자료/발표준비/내준비메모.jpg`)을 읽는다.
4. 에이전트가 검사 스크립트를 실행하려 하면 허락 카드가 뜬다. 명령을 읽고 "허락"을 누른다. 결과함에 `.json`이 생긴다.
5. 같은 에이전트를 다른 엔진으로 연결해 같은 요청을 보낸다. 같은 역할, 같은 스킬, 같은 허락 규칙으로 일하는지 본다.
6. "+ 새 에이전트"로 내 업무 에이전트를 하나 만든다.

AI가 읽고 정리하는 일과, 코드가 검사하고 저장하는 일이 나뉘어 있다. 에이전트는 도구를 고르고, 플랫폼은 허락을 묻고, 사람이 정한다.

### 일 파일

`tasks/` 아래에 `.md` 파일 하나가 일 하나다. 파일 이름이 일의 이름이다. 첫머리의 `---` 사이에 맡을 에이전트, 바꿔 쓸 엔진, 매일 실행할 시각을 적고, 그 아래에 맡길 내용을 적는다.

```
---
agent: 기본_도우미
engine: claude
time: 07:30
---
notes.md를 읽고, 마감이 있는 일만 날짜 순서로 표로 정리해 줘.
```

`agent`를 빼면 `기본_도우미`, `engine`을 빼면 에이전트의 기본 엔진, `time`을 빼면 직접 실행할 때만 돈다.

### 대시보드 API

서버(`dashboard.py`)는 JSON만 낸다. 화면(`app/static/`)은 이 API를 부르는 클라이언트다. 새 기능은 먼저 API를 더하고, 그다음에 화면에서 그 API를 부른다.

| 요청 | 하는 일 | 응답 |
|---|---|---|
| `GET /api/agents` | 에이전트 목록과 지금 연결 | `{"agents": [{"name", "engine", "description", "skills", "role", "history"}], "current", "engine", "state"}`. `skills`가 `null`이면 모든 스킬 |
| `POST /api/agents` `{"name", "engine", "description", "skills", "role"}` | 에이전트 만들기 | `201`. 이름이 이미 있으면 `409`, 틀린 값이면 `400` |
| `PUT /api/agents/{이름}` | 에이전트 고치기(이름은 그대로) | `200`. 없으면 `404` |
| `POST /api/session` `{"agent", "engine", "fresh"}` | 에이전트에 연결. `engine`을 주면 그 엔진으로, `fresh: true`이면 앞의 대화를 지운다 | `202`. 연결 결과는 사건으로 온다 |
| `POST /api/prompt` `{"text"}` | 질문 보내기 | `202`. 준비되지 않았으면 `409` |
| `POST /api/permissions/{번호}` `{"allow": true}` | 허락 카드에 답하기 | `200`. 기다리는 요청이 없으면 `404` |
| `GET /api/events?after={번호}` | 그 번호 뒤의 사건. 새 사건이 없으면 15초까지 기다린다 | `{"events", "last", "state", "agent", "engine"}` |
| `GET /api/engines` | 엔진 목록, 설치·로그인 상태, 로그인 방식 | `{"engines": [{"name", "installed", "loggedIn", "loginMode", "loginCommand", "canLogout"}]}` |
| `POST /api/login/{엔진}` | 로그인 시작. 진행은 사건 `login`으로 온다 | `202`. 이미 로그인되어 있으면 `409`, 터미널로 하는 엔진은 `400` |
| `POST /api/login/{엔진}/code` `{"code"}` | 코드 방식 로그인의 코드 넘기기 | `202`. 진행 중인 로그인이 없으면 `404` |
| `DELETE /api/login/{엔진}` | 진행 중인 로그인 멈추기 | `200` |
| `POST /api/logout/{엔진}` | 로그아웃 | `200`. 화면에서 로그아웃하지 않는 엔진은 `400` |
| `GET /api/brand` | 이름, 한 줄 소개, 색 | `{"name", "tagline", "accent"}` |
| `GET /api/skills` | 스킬 목록 | `{"skills": [{"name", "description", "example", "path"}]}` |
| `GET /api/tasks` | 일 목록 | `{"tasks": [{"name", "agent", "engine", "time", "prompt", "lastRun"}]}` |
| `POST /api/tasks/{이름}/run` | 일을 바로 실행 | `202` |
| `GET /api/outbox` | 결과 파일 목록(새것부터) | `{"files": [{"name", "type", "url"}]}` |
| `GET /api/outbox/{파일 이름}` | 결과 파일 내용 | `{"name", "type", "url", "text"}` |
| `GET /outbox/{파일 이름}` | 결과 파일 그대로. 대시보드 API를 부르지 못하게 따로 떼어 연다 | 파일 |

사건의 종류(`type`):

| 사건 | 뜻과 칸 |
|---|---|
| `status` | 연결 상태. `state`, `agent`, `engine` |
| `preamble` | 플랫폼 안내. `text`, `history`(이어 보낸 앞의 대화 수) |
| `user`, `text`, `done` | 보낸 질문, 답의 조각, 차례 끝과 쓴 양 |
| `tool`, `permission`, `rule` | 쓴 도구, 허락 요청, 규칙이 정한 허락·거절. `kind`, `label`, `detail` |
| `permission_result`, `rule_error` | 허락 결과, 규칙 오류 |
| `task` | 일의 시작과 끝. `agent`, `engine`, `file`, `deliveryError` |
| `login` | 로그인 진행. `engine`, `state`(`started`, `waiting`, `checking`, `done`, `failed`, `cancelled`, `logged_out`) |

## 파일

| 파일 | 하는 일 |
|---|---|
| `custom/` | 내가 먼저 바꾸는 곳. `brand.json`(이름과 색), `업무.md`(모든 에이전트에 공통인 업무), `agents/`(에이전트), `rules.py`(허락 규칙), `deliver.py`(결과 보내기) |
| `만들_곳.md` | 바꾸거나 더할 수 있는 곳의 지도와 Kiro Crew의 비슷한 위치 |
| `AGENTS.md`, `CLAUDE.md` | 이 레포를 고치는 코딩 에이전트용 개발 안내 |
| `안내/`, `계획/`, `기록/`, `발표/` | 최종 과제 안내와 계획서·기록·발표 자리 |
| `acp_client.py` | 엔진 층. 엔진을 샌드박스 홈으로 실행하고, 안전 모드로 바꾸고, 메시지를 주고받고, 도구 요청을 `ToolRequest`로 맞춘다 |
| `engines.json` | 엔진마다 실행 명령, 샌드박스 홈, 안전 모드, 로그인 방식 |
| `workspace/.kiro/agents/engine.json` | Kiro 엔진 설정. 쓸 도구와 묻지 않고 쓸 도구(`read`만) |
| `custom_loader.py` | 플랫폼 층. `custom/`와 스킬을 읽고, 에이전트를 읽고 저장하고, 플랫폼 안내를 만든다 |
| `dashboard.py` | 대시보드의 서버. JSON API, 에이전트, 대화와 대화 기록, 로그인, 일 실행, 스케줄, 결과함 |
| `app/static/` | 대시보드의 화면(`index.html`, `style.css`, `app.js`) |
| `runner.py` | 사람 없이 일을 한 번 돌리는 공용 코드. `run_once.py`와 대시보드가 함께 쓴다 |
| `tasks/` | 맡길 일 파일. 예: `마감_브리핑.md` |
| `login.py`, `chat.py`, `run_once.py` | 터미널 예제: 로그인, 대화, 한 번 실행 |
| `workspace/` | 엔진이 일하는 작업 폴더 |
| `workspace/skills/` | 스킬. 수업 스킬 `memo-to-json`, `data-to-html` |
| `workspace/자료/발표준비/` | 스킬을 해 볼 예시 자료(메모 사진, md, csv) |
| `tests/` | 가짜 엔진과 가짜 로그인으로 도는 테스트. `test_safety.py`는 안전 모드를, `test_engine_agnostic.py`는 플랫폼 층이 엔진에 기대지 않는지를, `test_tool_request.py`는 세 엔진의 도구 요청이 같은 꼴이 되는지를 본다 |

## ACP 흐름

메시지는 JSON 한 줄씩 표준 입출력으로 주고받는다(JSON-RPC 2.0). 세 엔진이 같은 흐름을 쓴다.

| 순서 | 메시지 | 보내는 쪽 | 뜻 |
|---|---|---|---|
| 1 | `initialize` | 플랫폼 | 플랫폼이 해 줄 수 있는 일을 알린다 |
| 2 | `session/new` | 플랫폼 | 작업 폴더를 정하고 대화 하나를 연다 |
| 3 | `session/set_mode` | 플랫폼 | 안전 모드로 바꾼다(Claude, Codex) |
| 4 | `session/prompt` | 플랫폼 | 질문을 보낸다. 첫 질문에는 플랫폼 안내가 앞에 붙는다 |
| 5 | `session/update` | 엔진 | 답의 조각(`agent_message_chunk`), 도구 사용(`tool_call`), 컨텍스트 사용량(`usage_update`)을 알린다 |
| 6 | `session/request_permission` | 엔진 | 도구를 써도 되는지 묻는다. 플랫폼은 `ToolRequest`로 바꿔 `custom/rules.py`와 사람에게 묻는다 |
| 7 | `session/prompt`의 응답 | 엔진 | 이번 차례가 끝났다(`stopReason`) |

허락 요청의 선택지 이름(`optionId`)은 엔진마다 다르다. 종류(`kind`)는 같다. 그래서 플랫폼은 `allow_once`와 `reject_once` 종류로 고른다. 도구 요청의 모양도 엔진마다 조금씩 다르다. `acp_client.tool_request`가 이를 맞추고, 그 차이는 함수 설명과 `tests/test_tool_request.py`에 적어 두었다.

## 주의

- 이 레포는 공개다. 토큰, 비밀번호, 개인 정보, 회사 자료를 커밋하지 않는다. `.homes/`와 `.env`는 `.gitignore`에 들어 있다.
- `.homes/`에는 로그인 정보가 들어 있다. 다른 사람에게 이 폴더를 주지 않는다.
- `safe_mode`를 Claude의 `bypassPermissions`나 Codex의 `agent-full-access`로 바꾸지 않는다. 모든 도구를 묻지 않고 허락한다. 허락을 넓히려면 `custom/rules.py`로 한다.
- 구독 계정의 사용 규칙은 바뀔 수 있다. 쓰기 전에 각 서비스의 안내를 확인한다. Claude는 2026-10-07 도움말 센터 기준으로 Agent SDK를 플랜 사용 한도 안에서 쓸 수 있다.
- 이 예제는 macOS에서 실행해 확인했다. Windows에서는 실행해 보지 않았다.
- 답을 기다리는 시간 제한과 중간에 멈추기(`session/cancel`)는 다루지 않는다. 일 실행만 300초가 지나면 연결을 끊는다.
- 대시보드는 내 컴퓨터(`127.0.0.1`)에서만 열린다. 인증이 없으므로 밖으로 열지 않는다.

## 참고

- Agent Client Protocol: https://agentclientprotocol.com/
- Kiro ACP 문서: https://kiro.dev/docs/cli/acp/
- Claude 어댑터: https://github.com/agentclientprotocol/claude-agent-acp
- Codex 어댑터: https://github.com/agentclientprotocol/codex-acp
- Kiro Crew: https://github.com/kirodotdev/KiroCrew
