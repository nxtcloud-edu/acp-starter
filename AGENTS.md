# 개발 안내 (코딩 에이전트용)

이 파일은 이 레포를 고치는 코딩 에이전트(Kiro CLI, Claude Code, Codex)가 읽는다. 사람이 읽어도 된다.
앱 안에서 일하는 엔진(작업 폴더 `workspace/`)은 이 파일을 읽지 않게 막아 두었다.

## 이 레포는 무엇인가

"내 에이전트 플랫폼 앱"의 출발점이다. 브라우저로 여는 작은 앱에서 엔진(Kiro, Claude, Codex)을 ACP(Agent Client Protocol)로 연결해 대화하고, 엔진이 도구를 쓸 때 허락을 묻는다. 처음에는 이 기본 템플릿만 있다. 사용자는 여기에 이름과 색감을 입히고, 필요한 기능을 하나씩 붙여 자기 앱으로 키운다. 사용자가 무엇을 만들고 싶은지는 `custom/brand.json`, `custom/업무.md`, `계획/`, 그리고 사용자의 말에서 알아낸다.

용어: "엔진"은 앱 안에서 대화하고 일하는 ACP 프로그램이다. 이 파일을 읽는 코딩 에이전트(너)와 헷갈리지 않는다.

## 사용자와 일하는 방식

- 사용자는 이 앱을 처음 고치는 학생일 수 있다. 처음이면 눈에 보이는 변화부터 함께 한다: 앱 이름과 한 줄 소개(`custom/brand.json`), 색감(`app/static/style.css`의 `:root` 토큰), 화면의 말.
- 기능을 정해 주지 않는다. 사용자가 하고 싶은 일을 묻고, 선택지를 두세 개 제안하고, 사용자가 고른 것을 하나씩 만든다.
- 더할 수 있는 기능의 목록은 `만들_곳.md`에 있다. acp-starter 레포의 브랜치 `전체기능-예시`에 한 번 만들어 둔 기능(에이전트 여럿, 스킬, 일 스케줄, 결과함, 결과 보내기, 파일 올리기, 대화 목록)이 있다. 참고해서 사용자의 앱에 맞게 작게 다시 만든다.
- 하나를 만들면 사용자가 앱을 새로 고쳐 직접 보게 한다. 그다음 것으로 넘어간다.
- 그날 작업을 마칠 때 일지(`기록/일지/<날짜>.md`, `_틀.md`를 복사)와 변경 기록(`기록/변경.md`)을 남기자고 권한다. 사용자가 맡기면 정리해 준다. 그다음에 커밋과 푸시를 권한다. 사용자의 확인 없이 커밋하거나 푸시하지 않는다.

## 가장 중요한 규칙: 엔진이 바뀌어도 앱의 기능은 그대로 돈다

흐름은 하나다. 사용자의 입력 → 플랫폼(엔진 이름을 모름) → 엔진 어댑터가 그 엔진에 맞는 형식으로 바꿔 보냄 → 엔진 → 엔진 어댑터가 하나의 형식(`ToolRequest`, `TurnResult`)으로 포장 → 플랫폼이 화면 표시와 기능 수행.

- 엔진마다 다른 것은 엔진 층(`engines/`, `login.py`)에만 둔다. 엔진 하나는 `engines/<이름>.py` 하나다. 공통 통역은 `engines/base.py`다.
- 플랫폼 층(`custom_loader.py`, `conversations.py`, `dashboard.py`, `app/static/`)과 `custom/`의 코드는 엔진 이름을 문자열로 쓰지 않는다. `tests/test_engine_agnostic.py`가 확인한다.
- 플랫폼은 `engines.make(이름, 작업 폴더)`로 엔진을 만들고, `send(글)`이 돌려주는 `TurnResult`만 쓴다. 엔진이 보낸 원래 모양(`raw`)에 기대는 코드는 쓰지 않는다.
- 새 기능은 플랫폼이 직접 한다. 엔진만이 가진 기능(Kiro 에이전트 설정의 prompt, Claude의 `CLAUDE.md`·스킬·훅·메모리, Codex의 `AGENTS.md`·스킬·플러그인·기억)에 기대지 않는다. 그런 곳에 넣은 동작은 엔진을 바꾸면 사라진다.
- 엔진에게 무언가를 알려야 하면 플랫폼 안내(`custom_loader.preamble`)나 `custom/업무.md`에 넣는다. 작업 폴더(`workspace/`)에는 엔진만의 파일(`.kiro/`, `.claude/`, `.codex/`, `AGENTS.md`, `CLAUDE.md`)을 두지 않는다.
- 엔진의 모양이 다르면 그 엔진의 파일에서 훅을 덮어써 맞추고, 실제로 받은 모양을 `tests/test_tool_request.py`에 더한다. 방법은 README의 "새 엔진 더하기"에 있다.

## 구조

| 층 | 파일 | 맡는 일 |
|---|---|---|
| 엔진 | `engines/base.py` | 공통 통역. 엔진을 샌드박스 홈(`.homes/<이름>/`)으로 실행하고, 안전 모드로 바꾸고, 메시지를 주고받고, `ToolRequest`와 `TurnResult`로 포장한다. 거절 뒤 멈춘 엔진을 이어 가게 한다. 올린 파일을 그 엔진이 받는 블록으로 바꾸는 `file_block`도 있다(지금 플랫폼은 쓰지 않는다) |
| 엔진 | `engines/kiro.py`, `claude.py`, `codex.py` | 엔진 하나씩. 실행 명령, 샌드박스 설정, 안전 모드, 로그인, 그 엔진만의 모양 |
| 엔진 | `engines/__init__.py`, `login.py` | 엔진 목록(`ENGINES`)과 `make`, `get`, `names`. 터미널 로그인 |
| 플랫폼 | `custom_loader.py` | `custom/`를 읽는다. 플랫폼 안내(업무, 도구 규칙, 앞의 대화)를 만든다 |
| 플랫폼 | `conversations.py` | 대화 기록. 대화 하나가 `conversations/<번호>.json` 하나다. 화면은 가장 새 대화 하나를 보인다 |
| 플랫폼 | `dashboard.py` | 앱 서버. JSON API만 낸다. 엔진 목록과 로그인, 연결(한 번에 하나), 대화, 허락 카드 |
| 플랫폼 | `app/static/` | 앱 화면. `dashboard.py`의 API를 부르는 클라이언트다. 색은 `style.css`의 `:root` 토큰에만 둔다 |
| 플랫폼 | `chat.py` | 터미널 대화 예제 |
| 사용자 | `custom/` | `brand.json`(이름, 한 줄 소개, 강조색), `업무.md`(엔진에게 먼저 알리는 업무), `rules.py`(허락 규칙 `decide(request)`) |
| 사용자 | `workspace/` | 엔진의 작업 폴더. 안의 파일은 커밋하지 않는다(`.gitignore`) |
| 시험 | `tests/` | 가짜 엔진(`fake_agent.py`)과 가짜 로그인(`fake_login.py`)으로 도는 테스트 |
| 문서 | `만들_곳.md` | 바꾸거나 더할 수 있는 곳과 예시 코드의 위치 |

## 고칠 때 지킬 것

- 새 기능은 API부터 정한다. `dashboard.py`에 JSON API를 더하고, README의 "앱 API" 표에 적고, 그다음에 `app/static/app.js`에서 부른다.
- 기능을 더하면 `tests/`에 테스트를 더한다. 테스트는 실제 엔진을 부르지 않는다. `python -m unittest discover tests`가 모두 통과해야 한다.
- 실제 엔진으로 확인할 때는 사용자에게 어느 엔진으로 볼지 묻는다. 사용량이 든다.
- 표준 라이브러리만 쓰는 것이 처음 상태다. 패키지를 더하면 `requirements.txt`를 만들고 README의 준비 절에 적는다.
- 사용자가 고칠 수 있는 동작은 `custom/`에 두는 쪽을 먼저 고려한다.
- 화면의 색은 `style.css`의 `:root` 토큰으로만 쓴다. 다크 화면 토큰도 함께 맞춘다.
- 한국어 문장, 짧은 함수, 이름은 지금 코드와 같은 꼴로 쓴다. 화면 글은 '-습니다'체로 쓴다.

## 하지 않을 것

- 엔진 파일의 `safe_mode`를 Claude `bypassPermissions`·`acceptEdits`·`auto`, Codex `agent`·`agent-full-access`로 바꾸지 않는다. 모든 도구를 묻지 않고 실행하게 된다. `tests/test_safety.py`가 이를 막는다.
- Kiro 엔진 설정(`engines/kiro.py`의 `SPEC`)의 `allowedTools`에 `read` 밖의 도구를 넣지 않는다. 허락은 `custom/rules.py`로 정한다.
- Codex 관리 블록(`engines/codex.py`의 `MANAGED`)에서 웹 검색, Apps, 플러그인, 기억을 다시 켜지 않는다. 허락을 거치지 않는 도구와 엔진만의 기억이 생긴다.
- Claude의 `SETTINGS`(`engines/claude.py`)와 실행 환경변수에서 기본 스킬, 자동 메모리, 계정 스킬·플러그인 동기를 다시 켜지 않는다. 같은 까닭이다.
- Claude의 `settingSources: []`와 Codex의 `project_doc_max_bytes = 0`을 지우지 않는다. 지우면 앱 안의 엔진이 사용자의 전역 설정이나 이 파일을 읽는다.
- 로그인된 엔진의 로그인을 다시 시작하지 않는다. Codex는 시작하자마자 있던 로그인을 지운다(`GOTCHAS.md`).
- `.homes/`(로그인 정보), `.env`(시크릿), `conversations/`(대화 기록), `workspace/`의 파일을 커밋하지 않는다. 시크릿은 코드와 문서에 적지 않고 `.env`에 둔다.
- 앱 서버를 `127.0.0.1` 밖으로 열지 않는다. 인증이 없다.

## 참고 코드

- acp-starter 레포의 브랜치 `전체기능-예시`: 이 앱에 기능을 많이 붙여 둔 모습이다. GitHub의 `https://github.com/nxtcloud-edu/acp-starter/tree/전체기능-예시`에서 읽거나, 이 레포 밖의 폴더에 클론해서 읽는다(`git clone --depth 1 --branch 전체기능-예시 https://github.com/nxtcloud-edu/acp-starter.git <레포 밖의 폴더>/acp-starter-예시`). 그대로 되돌리지 말고 사용자가 고른 기능만 작게 다시 만든다.
- Kiro Crew(https://github.com/kirodotdev/KiroCrew, Apache-2.0): 같은 층의 완성된 범용 플랫폼이다. 이 레포 밖의 폴더에 클론해서 필요한 부분만 찾아 읽는다(`git clone --depth 1 https://github.com/kirodotdev/KiroCrew.git <레포 밖의 폴더>/KiroCrew`). 이 레포 안에는 클론하지 않는다. 소스는 `src/kiro_crew/`에 있고, 위치는 `만들_곳.md`에 있다. 코드를 그대로 가져오면 그 파일에 출처와 Apache-2.0 고지를 남긴다.

## 실행

```sh
python dashboard.py                 # http://127.0.0.1:8765
python -m unittest discover tests   # 테스트
python login.py claude --status     # 샌드박스 로그인 상태
```
