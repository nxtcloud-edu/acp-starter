# 개발 안내 (코딩 에이전트용)

이 파일은 이 레포를 고치는 코딩 에이전트(Kiro CLI, Claude Code, Codex)가 읽는다. 사람이 읽어도 된다.
플랫폼 안에서 일하는 엔진(작업 폴더 `workspace/`)은 이 파일을 읽지 않게 막아 두었다.

## 이 레포는 무엇인가

"내 업무 전용 에이전트 플랫폼"의 출발점이다. 사용자가 만든 에이전트(`custom/agents/`)를 ACP(Agent Client Protocol)로 엔진(Kiro, Claude, Codex) 가운데 하나에 실어 돌린다. 사용자는 이 레포를 포크해서 자기 업무에 맞는 플랫폼으로 바꾼다. 사용자가 무엇을 바꾸고 싶은지는 `custom/업무.md`, `custom/agents/`, `계획/`, 그리고 사용자의 말에서 알아낸다.

용어: "에이전트"는 이 플랫폼에서 사용자가 만드는 것(역할, 스킬, 기본 엔진)이다. "엔진"은 그 에이전트를 돌리는 ACP 프로그램이다. 이 파일을 읽는 코딩 에이전트(너)와 헷갈리지 않는다.

## 가장 중요한 규칙: 엔진이 바뀌어도 플랫폼 기능은 그대로 돈다

흐름은 하나다. 사용자의 입력 → 플랫폼(엔진 이름을 모름) → 엔진 어댑터가 그 엔진에 맞는 형식으로 바꿔 보냄 → 엔진 → 엔진 어댑터가 하나의 형식(`ToolRequest`, `TurnResult`)으로 포장 → 플랫폼이 화면 표시와 기능 수행.

- 엔진마다 다른 것은 엔진 층(`engines/`, `login.py`)에만 둔다. 엔진 하나는 `engines/<이름>.py` 하나다. 공통 통역은 `engines/base.py`다.
- 플랫폼 층(`custom_loader.py`, `conversations.py`, `dashboard.py`, `runner.py`, `app/static/`)과 `custom/`의 코드는 엔진 이름을 문자열로 쓰지 않는다. `tests/test_engine_agnostic.py`가 확인한다.
- 플랫폼은 `engines.make(이름, 작업 폴더)`로 엔진을 만들고, `send(글)`이 돌려주는 `TurnResult`만 쓴다. 엔진이 보낸 원래 모양(`raw`)에 기대는 코드는 쓰지 않는다.
- 새 기능은 플랫폼이 직접 한다. 엔진만이 가진 기능(Kiro 에이전트 설정의 prompt, Claude의 `CLAUDE.md`·스킬·훅, Codex의 `AGENTS.md`·스킬·플러그인·기억)에 기대지 않는다. 그런 곳에 넣은 동작은 엔진을 바꾸면 사라진다.
- 에이전트에게 무언가를 알려야 하면 플랫폼 안내(`custom_loader.preamble`)에 넣는다. 작업 폴더(`workspace/`)에는 엔진만의 파일(`.kiro/`, `.claude/`, `.codex/`, `AGENTS.md`, `CLAUDE.md`)을 두지 않는다.
- 엔진의 모양이 다르면 그 엔진의 파일에서 훅을 덮어써 맞추고, 실제로 받은 모양을 `tests/test_tool_request.py`에 더한다. 방법은 README의 "새 엔진 더하기"에 있다.

## 구조

| 층 | 파일 | 맡는 일 |
|---|---|---|
| 엔진 | `engines/base.py` | 공통 통역. 엔진을 샌드박스 홈(`.homes/<이름>/`)으로 실행하고, 안전 모드로 바꾸고, 메시지를 주고받고, `ToolRequest`와 `TurnResult`로 포장한다. 거절 뒤 멈춘 엔진을 이어 가게 한다 |
| 엔진 | `engines/kiro.py`, `claude.py`, `codex.py` | 엔진 하나씩. 실행 명령, 샌드박스 설정 파일, 안전 모드, 로그인, 그 엔진만의 모양 |
| 엔진 | `engines/__init__.py` | 엔진 목록(`ENGINES`)과 `make`, `get`, `names` |
| 플랫폼 | `custom_loader.py` | `custom/`와 `workspace/skills/`를 읽어 잇는다. 에이전트를 읽고 저장한다. 플랫폼 안내(첫 질문 앞에 붙는 글)를 만든다 |
| 플랫폼 | `conversations.py` | 대화 기록. 대화 하나가 `conversations/<번호>.json` 하나다. 대화 기록은 엔진이 아니라 플랫폼이 갖는다 |
| 플랫폼 | `dashboard.py` | 대시보드 서버. JSON API만 낸다. 에이전트, 대화, 엔진 세션(한 번에 하나), 허락 카드, 일 실행과 스케줄, 결과함, 로그인 |
| 플랫폼 | `app/static/` | 대시보드 화면. `dashboard.py`의 API를 부르는 클라이언트다 |
| 플랫폼 | `runner.py` | 사람 없이 일을 한 번 돌린다. 대시보드와 `run_once.py`가 함께 쓴다 |
| 사용자 | `custom/` | `brand.json`(이름과 색), `업무.md`(모든 에이전트 공통 업무), `agents/`(에이전트), `rules.py`(허락 규칙), `deliver.py`(결과 보내기) |
| 사용자 | `tasks/` | 일 파일(머리말 `agent`, `engine`, `time`) |
| 사용자 | `workspace/` | 엔진의 작업 폴더. `skills/`, `자료/`, `outbox/`(결과함) |
| 시험 | `tests/` | 가짜 엔진(`fake_agent.py`)과 가짜 로그인(`fake_login.py`)으로 도는 테스트 |
| 문서 | `만들_곳.md` | 바꿀 수 있는 곳의 지도. Kiro Crew의 비슷한 위치도 적혀 있다 |

## 고칠 때 지킬 것

- 새 기능은 API부터 정한다. `dashboard.py`에 JSON API를 더하고, README의 "대시보드 API" 표에 적고, 그다음에 `app/static/app.js`에서 부른다.
- 기능을 더하면 `tests/`에 테스트를 더한다. 테스트는 실제 엔진을 부르지 않는다. `python -m unittest discover tests`가 모두 통과해야 한다.
- 실제 엔진으로 확인할 때는 사용자에게 어느 엔진으로 볼지 묻는다. 사용량이 든다.
- 표준 라이브러리만 쓰는 것이 처음 상태다. 패키지를 더하면 `requirements.txt`를 만들고 README의 준비 절에 적는다.
- 사용자가 고칠 수 있는 동작은 `custom/`에 두는 쪽을 먼저 고려한다.
- 한국어 문장, 짧은 함수, 이름은 지금 코드와 같은 꼴로 쓴다.

## 하지 않을 것

- 엔진 파일의 `safe_mode`를 Claude `bypassPermissions`·`acceptEdits`·`auto`, Codex `agent`·`agent-full-access`로 바꾸지 않는다. 모든 도구를 묻지 않고 실행하게 된다. `tests/test_safety.py`가 이를 막는다.
- Kiro 엔진 설정(`engines/kiro.py`의 `SPEC`)의 `allowedTools`에 `read` 밖의 도구를 넣지 않는다. 허락은 `custom/rules.py`로 정한다.
- Codex 관리 블록(`engines/codex.py`의 `MANAGED`)에서 웹 검색, Apps, 플러그인, 기억을 다시 켜지 않는다. 허락을 거치지 않는 도구와 엔진만의 기억이 생긴다.
- Claude의 `settingSources: []`와 Codex의 `project_doc_max_bytes = 0`을 지우지 않는다. 지우면 플랫폼 안의 엔진이 사용자의 전역 설정이나 이 파일을 읽는다.
- 로그인된 엔진의 로그인을 다시 시작하지 않는다. Codex는 시작하자마자 있던 로그인을 지운다(`GOTCHAS.md`).
- `.homes/`(로그인 정보), `.env`(시크릿), `conversations/`(대화 기록)를 커밋하지 않는다. 시크릿은 코드와 문서에 적지 않고 `.env`에 둔다. 레포가 공개이면 대화 기록이 모두에게 보인다.
- 대시보드를 `127.0.0.1` 밖으로 열지 않는다. 인증이 없다.

## 참고 레포: Kiro Crew

Kiro Crew(https://github.com/kirodotdev/KiroCrew, Apache-2.0)는 같은 층의 완성된 범용 플랫폼이다. 기능을 만들기 전에 Kiro Crew가 같은 문제를 어떻게 풀었는지 읽어 볼 수 있다.

- 이 레포 옆에 클론해서 읽는다: `git clone --depth 1 https://github.com/kirodotdev/KiroCrew.git ../KiroCrew`
- 소스는 `src/kiro_crew/`에 있다. 크고 복잡하므로 필요한 부분만 찾아 읽는다. 위치는 `만들_곳.md`에 있다.
- 코드를 그대로 가져오면 그 파일에 출처와 Apache-2.0 고지를 남긴다. 가능하면 구조만 참고해 작게 다시 쓴다.

## 실행

```sh
python dashboard.py                 # http://127.0.0.1:8765
python -m unittest discover tests   # 테스트
python login.py claude --status     # 샌드박스 로그인 상태
```
