# 개발 안내 (코딩 에이전트용)

이 파일은 이 레포를 고치는 코딩 에이전트(Kiro CLI, Claude Code, Codex)가 읽는다. 사람이 읽어도 된다.
플랫폼 안에서 일하는 에이전트(작업 폴더 `workspace/`)는 이 파일을 읽지 않게 막아 두었다.

## 이 레포는 무엇인가

ACP(Agent Client Protocol)로 Kiro, Claude, Codex 가운데 하나를 부르는 "내 업무 전용 에이전트 플랫폼"의 출발점이다. 사용자는 이 레포를 포크해서 자기 업무에 맞는 플랫폼으로 바꾼다. 사용자가 무엇을 바꾸고 싶은지는 `custom/업무.md`, `계획/`, 그리고 사용자의 말에서 알아낸다.

## 구조

| 파일 | 맡는 일 |
|---|---|
| `acp_client.py` | ACP 클라이언트. 에이전트를 샌드박스 홈(`.homes/<이름>/`)으로 실행하고, 안전 모드로 바꾸고, 메시지를 주고받는다 |
| `agents.json` | 에이전트마다 실행 명령, 샌드박스 홈, 안전 모드, 로그인 방식 |
| `custom_loader.py` | `custom/`와 `workspace/skills/`를 읽어 플랫폼에 잇는다. 플랫폼 안내(첫 질문 앞에 붙는 글)를 만든다 |
| `custom/` | 사용자가 먼저 바꾸는 곳: `brand.json`(이름과 색), `업무.md`(업무와 역할), `rules.py`(허락 규칙), `deliver.py`(결과 보내기) |
| `dashboard.py` | 대시보드 서버. JSON API만 낸다. 대화, 허락 카드, 일 실행과 스케줄, 결과함, 로그인 |
| `app/static/` | 대시보드 화면. `dashboard.py`의 API를 부르는 클라이언트다 |
| `runner.py` | 사람 없이 일을 한 번 돌린다. 대시보드와 `run_once.py`가 함께 쓴다 |
| `tasks/` | 일 파일(머리말 `agent`, `time`) |
| `workspace/` | 플랫폼 안 에이전트의 작업 폴더. `skills/`, `자료/`, `outbox/`(결과함) |
| `tests/` | 가짜 에이전트(`fake_agent.py`)와 가짜 로그인(`fake_login.py`)으로 도는 테스트 |
| `만들_곳.md` | 바꿀 수 있는 곳의 지도. Kiro Crew의 비슷한 위치도 적혀 있다 |

## 고칠 때 지킬 것

- 새 기능은 API부터 정한다. `dashboard.py`에 JSON API를 더하고, README의 "대시보드 API" 표에 적고, 그다음에 `app/static/app.js`에서 부른다.
- 기능을 더하면 `tests/`에 테스트를 더한다. 테스트는 실제 에이전트를 부르지 않는다. `python -m unittest discover tests`가 모두 통과해야 한다.
- 표준 라이브러리만 쓰는 것이 처음 상태다. 패키지를 더하면 `requirements.txt`를 만들고 README의 준비 절에 적는다.
- 사용자가 고칠 수 있는 동작은 `custom/`에 두는 쪽을 먼저 고려한다.
- 한국어 문장, 짧은 함수, 이름은 지금 코드와 같은 꼴로 쓴다.

## 하지 않을 것

- `agents.json`의 `safe_mode`를 Claude `bypassPermissions`·`acceptEdits`·`auto`, Codex `agent`·`agent-full-access`로 바꾸지 않는다. 모든 도구를 묻지 않고 실행하게 된다. `tests/test_safety.py`가 이를 막는다.
- Kiro `workspace/.kiro/agents/starter.json`의 `allowedTools`에 `read` 밖의 도구를 넣지 않는다. 허락은 `custom/rules.py`로 정한다.
- Claude의 `settingSources: []`와 Codex의 `project_doc_max_bytes = 0`을 지우지 않는다. 지우면 플랫폼 안의 에이전트가 사용자의 전역 설정이나 이 파일을 읽는다.
- `.homes/`(로그인 정보), `.env`(시크릿)를 커밋하지 않는다. 시크릿은 코드와 문서에 적지 않고 `.env`에 둔다.
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
