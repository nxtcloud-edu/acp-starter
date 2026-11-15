# acp-starter

내 에이전트 플랫폼 앱의 출발점입니다. 브라우저로 여는 작은 앱에서 엔진(Claude, Codex, Kiro)과 대화합니다. 엔진은 ACP(Agent Client Protocol)로 연결하고, 각자 가진 계정이나 구독으로 씁니다.

처음 받은 앱은 아주 기본만 있습니다. 엔진에 로그인하고, 연결하고, 대화하고, 엔진이 도구(파일 쓰기, 명령, 인터넷)를 쓰려 할 때 허락을 묻습니다. 여기에 이름을 붙이고, 내 색감으로 꾸미고, 필요한 기능을 하나씩 붙여서 내 앱으로 키웁니다.

## 처음 30분

1. **코딩 에이전트로 열기.** 이 폴더(`AGENTS.md`가 있는 폴더)를 내 코딩 에이전트(Kiro CLI, Claude Code, Codex)로 엽니다. 다른 폴더에서 열면 에이전트가 `AGENTS.md`를 읽지 못합니다. 먼저 "이 앱이 무엇이고 어떤 파일로 이루어져 있는지 알려 줘. 고치지는 마."라고 물어봅니다.
2. **켜 보기.** 다른 터미널을 열고 이 폴더에서 `python dashboard.py`를 실행하면 브라우저에서 `http://127.0.0.1:8765`가 열립니다. macOS에서 `python`이 없으면 `python3`을 씁니다. 끝낼 때는 터미널에서 Ctrl+C를 누릅니다.
3. **엔진 연결.** 왼쪽 엔진 카드에서 로그인하고 "연결"을 누릅니다. 아무 일이나 맡겨 보고, "작업 폴더에 메모 파일을 만들어 줘"처럼 파일을 쓰게 해서 허락 카드도 봅니다.
4. **이름 짓기.** 코딩 에이전트에게 "앱 이름을 ○○로 바꾸고 한 줄 소개를 써 줘"라고 맡깁니다. 바뀌는 곳은 `custom/brand.json`입니다. 브라우저를 새로 고치면 바뀝니다.
5. **내 색감으로.** "내가 좋아하는 색감으로 꾸며 줘"라고 맡겨 봅니다. 색은 `app/static/style.css` 맨 위의 `:root`에 모여 있습니다.
6. **기능 하나.** 써 보면서 "이게 있으면 좋겠다" 싶은 것을 하나 더합니다. 고를 거리는 [만들_곳.md](만들_곳.md)에, 코딩 에이전트에게 맡기는 말의 예는 [안내/코딩_에이전트와_일하기.md](안내/코딩_에이전트와_일하기.md)에 있습니다.
7. **남기기.** 작업한 날에는 `기록/일지/`에 그날 일지를 쓰고, 커밋하고 푸시합니다.

## 준비

- Python 3.10 이상. 설치할 Python 패키지는 없습니다.
- 쓸 엔진 하나 이상:

| 엔진 | 필요한 것 | 계정 |
|---|---|---|
| Kiro | [Kiro CLI](https://kiro.dev/docs/getting-started/installation/) | Kiro 계정 |
| Claude | Node.js(`npx` 포함), [Claude Code](https://code.claude.com/docs) (`claude` 명령) | Claude Pro·Max 구독 |
| Codex | Node.js(`npx` 포함), [Codex CLI](https://developers.openai.com/codex/cli) (`codex` 명령) | ChatGPT 구독 |

Claude와 Codex의 ACP 어댑터는 처음 연결할 때 `npx`가 내려받습니다. 버전은 `engines/claude.py`와 `engines/codex.py`에 고정했습니다.

## 로그인

엔진 카드의 "로그인"을 누르면 그 자리에 로그인 상자가 뜹니다.

| 엔진 | 로그인 상자 |
|---|---|
| Codex | 주소와 기기 코드가 나옵니다. 주소를 열고 ChatGPT 계정으로 로그인한 뒤 코드를 넣습니다 |
| Claude | 주소가 나옵니다(브라우저가 저절로 열리기도 합니다). Claude 계정으로 로그인한 뒤 화면에 나온 코드를 상자에 붙여 넣습니다 |
| Kiro | 앱에서 로그인하지 않습니다. Kiro 로그인은 컴퓨터 전체에 걸리므로 터미널에서 `kiro-cli login`을 실행합니다 |

이미 로그인된 엔진은 로그인을 다시 시작할 수 없습니다. Codex는 로그인을 시작하자마자 있던 로그인을 지우기 때문입니다. 다른 계정으로 바꾸려면 "로그아웃"을 먼저 누릅니다. 터미널로도 할 수 있습니다: `python login.py claude`(로그인), `python login.py codex --status`(상태).

## 앱의 모습

| 자리 | 하는 일 |
|---|---|
| 위 | 이름과 한 줄 소개(`custom/brand.json`), 지금 연결 상태 |
| 왼쪽 엔진 카드 | 로그인 상태, 로그인, 연결, 로그아웃. 지금 대화의 엔진이 강조됩니다 |
| 오른쪽 대화 | 질문과 답, 엔진이 쓴 도구, 허락 카드, "플랫폼이 보낸 안내". "새 대화"로 비웁니다 |

- 대화는 하나입니다. 기록은 `conversations/`에 남고 커밋되지 않습니다. 앱을 다시 켜도 이어집니다.
- 엔진을 바꿔 연결해도 대화가 이어집니다. 앱이 앞의 대화(최근 12개, 8000자 안)를 새 엔진에게 넘기기 때문입니다.
- 허락 카드는 5분 안에 누르지 않으면 거절합니다. 무엇을 묻고 무엇을 바로 허락할지는 `custom/rules.py`에서 정합니다.
- 엔진이 일하는 폴더는 `workspace/`입니다. 엔진이 만든 파일은 커밋되지 않습니다(`.gitignore`).

## 구조

```
사용자의 입력 (화면, 터미널)
   │   플랫폼 안내(업무, 도구 규칙, 앞의 대화)와 질문
   ▼
플랫폼                     custom_loader.py, conversations.py, dashboard.py, app/static/   ← 엔진 이름을 모른다
   │   engines.make(엔진 이름)
   ▼
엔진 어댑터                engines/kiro.py, claude.py, codex.py (공통은 engines/base.py)
   │   그 엔진에 맞는 형식으로 바꾼다(샌드박스, 세션 설정, 안전 모드, 허락 답)
   ▼
엔진                       kiro-cli, claude-agent-acp, codex-acp
   ▼
엔진 어댑터                하나의 형식으로 포장한다(ToolRequest, TurnResult)
   ▼
플랫폼                     화면 표시, 허락 규칙(custom/rules.py), 대화 기록
```

엔진이 무엇이든 플랫폼이 받는 것은 같은 꼴입니다. 그래서 **엔진을 바꿔도 앱의 기능은 그대로 돕니다.** 내가 더하는 기능도 플랫폼 쪽에 만들면 어느 엔진으로든 돕니다.

| 형식 | 뜻 | 칸 |
|---|---|---|
| `ToolRequest` | 엔진이 쓰려는 도구 하나 | `kind`(종류), `command`(명령), `path`(작업 폴더 기준 파일), `url`(인터넷 주소), `label`(화면 이름), `detail`(세부) |
| `TurnResult` | 한 차례의 결과 | `stop`(끝난 까닭: `done`, `limit`, `refusal`, `cancelled`), `text`(답), `segments`(도구 사이사이의 말), `tools`(쓴 도구), `refused`(거절한 도구), `notices`(플랫폼 알림), `usage`(쓴 양) |

| 파일 | 하는 일 |
|---|---|
| `custom/brand.json` | 앱 이름, 한 줄 소개, 강조색 |
| `custom/업무.md` | 엔진에게 먼저 알리는 내 업무와 규칙. 어느 엔진으로 연결해도 같은 글이 갑니다 |
| `custom/rules.py` | 허락 규칙. `decide(request)`가 `"allow"`, `"deny"`, `"ask"`를 돌려줍니다 |
| `app/static/` | 앱 화면(`index.html`, `style.css`, `app.js`). `dashboard.py`의 API를 부르는 클라이언트입니다 |
| `dashboard.py` | 앱 서버. JSON API만 냅니다. 엔진 목록과 로그인, 연결, 대화, 허락 카드 |
| `custom_loader.py` | `custom/`를 읽고 플랫폼 안내를 만듭니다 |
| `conversations.py` | 대화 기록을 `conversations/<번호>.json`으로 읽고 씁니다 |
| `engines/` | 엔진 층. `base.py`가 공통 통역이고, 엔진 하나에 파일 하나입니다 |
| `login.py`, `chat.py` | 터미널 예제: 로그인, 대화(`python chat.py claude`) |
| `tests/` | 가짜 엔진으로 도는 테스트. `python -m unittest discover tests`. 사용량이 들지 않습니다 |
| `만들_곳.md` | 바꾸거나 더할 수 있는 곳 |
| `AGENTS.md`, `CLAUDE.md` | 이 폴더를 고치는 코딩 에이전트용 개발 안내 |
| `안내/`, `계획/`, `기록/`, `발표/` | 최종 과제 안내, 계획, 기록, 발표 자리 |

## 엔진마다 다른 점

2026-10-21에 세 엔진(Kiro CLI 2.29.1, claude-agent-acp 0.94.0, codex-acp 2.2.2)을 실제로 돌려 확인했습니다. 맞추는 코드는 `engines/`에 있습니다.

| 다른 점 | Kiro | Claude | Codex | 플랫폼이 받는 꼴 |
|---|---|---|---|---|
| 역할과 지침 | 엔진 설정의 역할 문장(`prompt`)을 비웁니다 | `CLAUDE.md`를 읽지 않게 합니다(`settingSources: []`) | `AGENTS.md`를 읽지 않게 합니다(`project_doc_max_bytes = 0`) | 플랫폼 안내 |
| 엔진이 따로 읽는 것 | 기본 자원을 물려받지 않게 합니다 | 기본 스킬, 내장 플러그인의 스킬, 자동 메모리, claude.ai 계정의 스킬과 플러그인 동기를 끕니다 | 홈 폴더의 개인 스킬(`~/.agents/skills`), 계정 플러그인, Apps, 기억을 끕니다. 홈 폴더도 샌드박스로 돌립니다 | 엔진에게 가는 것은 플랫폼 안내뿐 |
| 허락 요청의 종류 | `kind`가 비어 옵니다 | 있습니다 | 있습니다 | `kind`. 비면 시작 알림의 값으로 채웁니다 |
| 명령 | 그대로 | 그대로 | 따옴표로 감싸 옵니다 | `command` |
| 파일 경로 | `rawInput.path` | 세부가 뒤의 갱신 알림에 옵니다 | `content`의 diff에 옵니다 | `path`(작업 폴더 기준) |
| 인터넷 | `web_fetch`가 `kind: read`로 옵니다 | `Fetch` | 자체 웹 검색과 Apps 도구는 끄고, `curl`은 허락을 묻습니다 | `url` |
| 거절하면 | 그 단계만 건너뛰고 계속합니다 | 그 단계만 건너뛰고 계속합니다 | 차례 전체가 멈춥니다(`cancel`) | 플랫폼이 거절을 알리고 이어서 하게 합니다(`notices`). 최대 3번 |
| 쓴 양 | 크레딧 | 컨텍스트 토큰 | 컨텍스트 토큰 | `usage` |
| 로그인 | 컴퓨터 전체에 걸립니다. 터미널에서 | 샌드박스에. 코드를 붙여 넣습니다 | 샌드박스에. 기기 코드 | 엔진 카드의 로그인 상자 |

## 샌드박스: 깨끗한 상태로 시작합니다

엔진마다 이 폴더 안의 `.homes/<이름>/`을 설정 폴더로 씁니다. 그래서 내 컴퓨터에 원래 있던 전역 설정, 스킬, 플러그인, 기억, MCP 서버를 가져오지 않습니다. `.homes/`에는 로그인 정보가 들어 있고 `.gitignore`에 들어 있습니다.

| 엔진 | 샌드박스 홈을 가리키는 환경변수 | 엔진 어댑터가 쓰는 설정 |
|---|---|---|
| Kiro | `KIRO_HOME` | `agents/engine.json`(쓸 도구와 묻지 않을 도구), `settings/cli.json`(기본 자원을 물려받지 않음) |
| Claude | `CLAUDE_CONFIG_DIR` | 설정 파일 없음. 세션을 열 때 `settingSources: []`와 끄는 설정(`engines/claude.py`의 `SETTINGS`)을 보냅니다 |
| Codex | `CODEX_HOME`, 그리고 `HOME` | `config.toml` 맨 위의 관리 블록. 실행할 때마다 다시 쓰고, 사용자가 쓴 다른 줄은 그대로 둡니다 |

막혔는지는 세션 기록으로 확인했습니다. 이 폴더의 개발 안내(`AGENTS.md`)와 컴퓨터의 개인 스킬은 세 엔진 어디에도 실리지 않았습니다. Codex 자체의 기본 스킬(예: `skill-creator`)은 남습니다. Claude의 기본 스킬은 끄고 스킬 목록이 비어 있는 것을 확인했습니다(2026-11-04). 까닭과 경위는 [GOTCHAS.md](GOTCHAS.md)에 있습니다.

## 안전 모드와 허락

연결하면 바로 안전 모드로 바꿉니다. 세 엔진이 같은 종류의 일을 묻도록 맞춰 두었습니다.

| 일 | Kiro | Claude | Codex |
|---|---|---|---|
| 파일 읽기 | 묻지 않습니다 | 묻지 않습니다 | 묻지 않습니다 |
| 파일 쓰기 | 묻습니다 | 묻습니다 | 묻습니다 |
| 명령 실행 | 묻습니다 | 묻습니다. 단 `ls`, `date` 같은 읽기 전용 명령은 묻지 않습니다 | 묻습니다. 단 읽기 명령은 읽기만 되는 샌드박스 안에서 묻지 않고 실행합니다 |
| 인터넷 | 묻습니다 | 묻습니다 | 묻습니다(`curl`) |
| 설정 | 묻지 않는 도구는 `read`뿐 | 안전 모드 `default` | 안전 모드 `read-only` |

엔진이 허락을 물으면 플랫폼은 그 요청을 `ToolRequest`로 바꾼 뒤 `custom/rules.py`에 묻습니다. 규칙이 `"ask"`를 돌려주면 허락 카드가 뜹니다. 같은 규칙은 어느 엔진에도 똑같이 걸립니다. 예를 들어 `if request.url: return "deny"` 한 줄은 세 엔진의 인터넷을 모두 막습니다.

## 앱 API

서버(`dashboard.py`)는 JSON만 냅니다. 화면(`app/static/`)은 이 API를 부르는 클라이언트입니다. 새 기능은 먼저 API를 더하고, 그다음에 화면에서 그 API를 부릅니다. 오류는 `{"error"}`로 옵니다.

| 요청 | 하는 일 | 응답 |
|---|---|---|
| `GET /api/brand` | 이름, 한 줄 소개, 색 | `{"name", "tagline", "accent"}` |
| `GET /api/engines` | 엔진 목록, 설치·로그인 상태, 로그인 방식 | `{"engines": [{"name", "installed", "loggedIn", "loginMode", "loginCommand", "canLogout"}]}` |
| `GET /api/state` | 지금 연결 상태와 답을 쓰는 중인 차례의 사건. 화면을 처음 열 때 부릅니다 | `{"state", "engine", "conversation", "live", "last", "epoch"}` |
| `GET /api/conversation` | 지금 대화. 메시지의 꼴은 `conversations.py` 머리에 있습니다 | `{"id", "engine", "created", "updated", "messages"}` |
| `POST /api/conversation/new` | 새 대화. 엔진 세션을 닫습니다 | `201`. 답을 쓰는 중이면 `409` |
| `POST /api/connect` `{"engine"}` | 엔진 연결. 엔진을 바꾸면 앞의 대화를 새 엔진에 넘깁니다 | `202`. 없는 엔진은 `400`, 답을 쓰는 중이면 `409` |
| `POST /api/prompt` `{"text"}` | 질문 보내기. 연결하지 않았으면 대화의 엔진으로 연결합니다. 답은 사건으로 옵니다 | `202`. 빈 글은 `400`, 답을 쓰거나 연결하는 중이면 `409` |
| `POST /api/permissions/{번호}` `{"allow": true}` | 허락 카드에 답하기 | `200`. 기다리는 요청이 없으면 `404` |
| `GET /api/events?after={번호}` | 그 번호 뒤의 사건. 새 사건이 없으면 15초까지 기다립니다 | `{"events", "last", "epoch", "state", "engine"}`. `epoch`가 바뀌면 서버를 다시 켠 것이므로 `/api/state`부터 다시 읽습니다 |
| `POST /api/login/{엔진}` | 로그인 시작. 진행은 사건 `login`으로 옵니다 | `202`. 이미 로그인했으면 `409`, 터미널로 하는 엔진은 `400` |
| `POST /api/login/{엔진}/code` `{"code"}` | 코드 방식 로그인의 코드 넘기기 | `202` |
| `DELETE /api/login/{엔진}` | 진행 중인 로그인 멈추기 | `200` |
| `POST /api/logout/{엔진}` | 로그아웃 | `200` |

사건의 종류(`type`):

| 사건 | 뜻 |
|---|---|
| `status` | 연결 상태. `state`(`starting`, `ready`, `busy`, `error`), `engine`, 오류이면 `message` |
| `preamble` | 새 세션의 첫 질문 앞에 붙인 플랫폼 안내. `engine`, `text`, `history`(넣은 앞의 대화 수) |
| `user`, `text` | 보낸 질문, 답의 조각 |
| `tool`, `permission`, `rule` | 쓴 도구, 허락 요청, 규칙이 정한 허락·거절. `kind`, `label`, `detail` |
| `permission_result`, `rule_error` | 허락 결과, 규칙 오류 |
| `note`, `notice` | 플랫폼이 대화에 남긴 알림(예: 엔진을 바꿨다), 거절 뒤 이어서 하게 한 알림 |
| `conversation` | 새 대화를 열었다 |
| `record_error` | 대화 기록을 저장하지 못했다. 답은 계속 받습니다 |
| `done` | 차례 끝. `stop`, `stopLabel`, `usage`, `refused` |
| `login` | 로그인 진행. `engine`, `state`(`started`, `waiting`, `checking`, `done`, `failed`, `cancelled`, `logged_out`) |

## ACP 흐름

메시지는 JSON 한 줄씩 표준 입출력으로 주고받습니다(JSON-RPC 2.0). 세 엔진이 같은 흐름을 씁니다.

| 순서 | 메시지 | 보내는 쪽 | 뜻 |
|---|---|---|---|
| 1 | `initialize` | 플랫폼 | 플랫폼이 해 줄 수 있는 일을 알립니다 |
| 2 | `session/new` | 플랫폼 | 작업 폴더를 정하고 대화 하나를 엽니다. 엔진에 따라 `_meta`를 붙입니다(Claude) |
| 3 | `session/set_mode` | 플랫폼 | 안전 모드로 바꿉니다(Claude, Codex) |
| 4 | `session/prompt` | 플랫폼 | 질문을 보냅니다. 첫 질문에는 플랫폼 안내가 앞에 붙습니다 |
| 5 | `session/update` | 엔진 | 답의 조각, 도구 사용과 그 갱신, 사용량을 알립니다 |
| 6 | `session/request_permission` | 엔진 | 도구를 써도 되는지 묻습니다. 플랫폼은 `ToolRequest`로 바꿔 `custom/rules.py`와 사람에게 묻고, 그 엔진의 선택지로 답합니다 |
| 7 | `session/prompt`의 응답 | 엔진 | 이번 차례가 끝났습니다(`stopReason`). 플랫폼은 `TurnResult`로 포장합니다 |

## 새 엔진 더하기

1. `engines/<이름>.py`를 만들고 `AcpEngine`을 이어받습니다. 실행 명령, 샌드박스 홈 환경변수, 안전 모드, 로그인 명령을 적습니다.
2. 그 엔진만의 모양이 있으면 훅을 덮어씁니다: `prepare_home`(설정 파일), `session_meta`, `file_block`(올린 파일), `choose_option`(허락 선택지), `command_text`, `tool_request`, `on_extension`(확장 알림), `logged_in`.
3. `engines/__init__.py`의 `ENGINES`에 더합니다.
4. 실제로 받은 도구 요청의 모양을 `tests/test_tool_request.py`에 더하고, 테스트를 모두 돌립니다.
5. 세션 기록으로 개발 안내와 개인 설정이 실리지 않는지 확인합니다.

## 주의

- 토큰, 비밀번호, 개인 정보, 회사 자료를 커밋하지 않습니다. 시크릿은 `.env`에 둡니다. `.homes/`와 `.env`는 `.gitignore`에 들어 있습니다.
- `.homes/`에는 로그인 정보가 들어 있습니다. 다른 사람에게 이 폴더를 주지 않습니다.
- 안전 모드를 Claude의 `bypassPermissions`나 Codex의 `agent-full-access`로 바꾸지 않습니다. 모든 도구를 묻지 않고 허락하게 됩니다. 허락을 넓히려면 `custom/rules.py`로 합니다.
- 구독 계정의 사용 규칙은 바뀔 수 있습니다. 쓰기 전에 각 서비스의 안내를 확인합니다.
- 앱은 내 컴퓨터(`127.0.0.1`)에서만 열립니다. 인증이 없으므로 밖으로 열지 않습니다.
- 답을 기다리는 시간 제한과 중간에 멈추기(`session/cancel`)는 아직 없습니다.

## 참고

- Agent Client Protocol: https://agentclientprotocol.com/
- Kiro ACP 문서: https://kiro.dev/docs/cli/acp/
- Claude 어댑터: https://github.com/agentclientprotocol/claude-agent-acp
- Codex 어댑터: https://github.com/agentclientprotocol/codex-acp
- Kiro Crew: https://github.com/kirodotdev/KiroCrew
