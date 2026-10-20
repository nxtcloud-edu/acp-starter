# GOTCHAS

## Claude 샌드박스에 상위 폴더의 CLAUDE.md가 실림 (2026-10-20)

- 증상: `CLAUDE_CONFIG_DIR`을 레포 안의 `.homes/claude/`로 바꿨는데도, Claude의 답에 사용자 전역 지침(`~/.claude/CLAUDE.md`)의 말투와 문구가 나왔다. "지시문에 '작업 규격'이 있나"라고 물으면 "있음"이라고 답했다.
- 근본 원인: Claude Code는 작업 폴더에서 상위 폴더로 올라가며 각 폴더의 `CLAUDE.md`와 `.claude/CLAUDE.md`를 프로젝트 지침으로 읽는다. 작업 폴더가 홈 폴더 아래에 있으면 홈 폴더의 `.claude/CLAUDE.md`, 곧 전역 지침 파일이 그 경로에 걸린다. 설정 폴더를 바꾸는 것으로는 이 경로를 막지 못한다.
- 해결: `session/new`의 `_meta.claudeCode.options`로 `settingSources: []`를 넘긴다(`agents.json`의 `session_meta`). 같은 질문에 "없음"으로 답했다. 대신 작업 폴더의 `CLAUDE.md`도 읽지 않는다.
- 교훈: 샌드박스가 깨끗한지는 설정 폴더만 보고 판단하지 않는다. 지시문에만 있는 낱말을 물어서 실제로 실린 것을 확인한다. Kiro와 Codex는 같은 방법으로 확인했을 때 실리지 않았다(Codex는 세션 기록 파일로 확인).
