"""테스트용 가짜 엔진. ACP 엔진처럼 표준 입출력으로 메시지를 주고받는다.

실행 인자: fake_agent.py <현재 모드 이름>
환경변수 FAKE_STYLE: 비우면 거절해도 계속한다(Kiro, Claude처럼).
  codex          거절 선택지가 cancel뿐이고, 거절하면 차례를 멈춘다(Codex처럼).
  codex_decline  거절 선택지가 cancel과 decline 둘이다. decline이면 계속한다.
  codex_twice    codex와 같고, 첫 이어 묻기에서도 도구를 한 번 더 요청한다.
"""

import json
import os
import sys

MODE = sys.argv[1] if len(sys.argv) > 1 else "engine"
STYLE = os.environ.get("FAKE_STYLE", "")
OPTIONS = {
    "": [{"optionId": "allow-once", "kind": "allow_once"}, {"optionId": "reject", "kind": "reject_once"}],
    "codex": [{"optionId": "allow_once", "kind": "allow_once"}, {"optionId": "cancel", "kind": "reject_once"}],
    "codex_twice": [{"optionId": "allow_once", "kind": "allow_once"}, {"optionId": "cancel", "kind": "reject_once"}],
    "codex_decline": [{"optionId": "allow_once", "kind": "allow_once"}, {"optionId": "cancel", "kind": "reject_once"},
                      {"optionId": "decline", "kind": "reject_once"}],
}
PREAMBLE_END = "[여기까지 플랫폼 안내. 아래가 사용자의 요청이다]"   # custom_loader.PREAMBLE_END와 같다


def send(message):
    message["jsonrpc"] = "2.0"
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def read():
    return json.loads(sys.stdin.readline())


def update(body):
    send({"method": "session/update", "params": {"sessionId": "s1", "update": body}})


for line in sys.stdin:
    message = json.loads(line)
    method, rid = message.get("method"), message.get("id")
    if method == "initialize":
        send({"id": rid, "result": {"protocolVersion": 1}})
    elif method == "session/new":
        META = message["params"].get("_meta")
        send({"method": "_kiro.dev/commands/available", "params": {"commands": []}})
        send({"id": rid, "result": {"sessionId": "s1", "modes": {"currentModeId": MODE}}})
    elif method == "session/set_mode":
        MODE = message["params"]["modeId"]
        send({"id": rid, "result": {}})
    elif method == "session/prompt":
        text = message["params"]["prompt"][0]["text"]
        had_preamble = PREAMBLE_END in text
        text = text.split(PREAMBLE_END)[-1].strip()
        if text == "안내":
            text = "있음" if had_preamble else "없음"
        elif text == "모드":
            text = MODE
        elif text == "메타":
            text = json.dumps(globals().get("META"), ensure_ascii=False)
        elif text == "홈":
            text = os.environ.get("FAKE_HOME_CHECK", "")
        update({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "받음: "}})
        update({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}})
        followup = text.startswith("[플랫폼 알림]")
        if followup:
            FOLLOWUPS = globals().get("FOLLOWUPS", 0) + 1
        if ("도구" in text and not followup) or (STYLE == "codex_twice" and followup and FOLLOWUPS == 1):
            # 실제 엔진처럼 시작 알림에는 kind가 있고, 허락 요청에는 없다(Kiro와 같은 모양).
            update({"sessionUpdate": "tool_call", "toolCallId": "t1", "title": "Running: date", "kind": "execute"})
            send({"id": "p1", "method": "session/request_permission", "params": {
                "sessionId": "s1",
                "toolCall": {"toolCallId": "t1", "title": "Running: date", "rawInput": {"command": "date"}},
                "options": OPTIONS[STYLE]}})
            answer = read()
            chosen = answer["result"]["outcome"].get("optionId", "cancelled")
            if chosen == "cancel":
                # Codex처럼 차례 전체를 멈춘다. 거절에 대한 말은 하지 않는다.
                send({"id": rid, "result": {"stopReason": "cancelled"}})
                continue
            update({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": f" / {chosen}"}})
        send({"id": 99, "method": "fs/read_text_file", "params": {}})
        unknown = read()
        assert unknown["error"]["code"] == -32601
        send({"method": "_kiro.dev/metadata", "params": {
            "meteringUsage": [{"unit": "credit", "value": 0.25}, {"unit": "credit", "value": 0.5}]}})
        update({"sessionUpdate": "usage_update", "used": 1234, "size": 100000})
        send({"id": rid, "result": {"stopReason": "end_turn"}})
