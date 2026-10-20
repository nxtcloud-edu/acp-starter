"""테스트용 가짜 에이전트. kiro-cli acp처럼 표준 입출력으로 ACP 메시지를 주고받는다."""

import json
import sys

AGENT = sys.argv[sys.argv.index("--agent") + 1]


def send(message):
    message["jsonrpc"] = "2.0"
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def read():
    return json.loads(sys.stdin.readline())


def update(sid, body):
    send({"method": "session/update", "params": {"sessionId": sid, "update": body}})


for line in sys.stdin:
    message = json.loads(line)
    method, rid = message.get("method"), message.get("id")
    if method == "initialize":
        send({"id": rid, "result": {"protocolVersion": 1}})
    elif method == "session/new":
        send({"method": "_kiro.dev/commands/available", "params": {"commands": []}})
        mode = "other" if AGENT == "missing" else AGENT
        send({"id": rid, "result": {"sessionId": "s1", "modes": {"currentModeId": mode}}})
    elif method == "session/prompt":
        sid = message["params"]["sessionId"]
        text = message["params"]["prompt"][0]["text"]
        update("s1", {"sessionUpdate": "agent_message_chunk",
                      "content": {"type": "text", "text": "받음: "}})
        update("s1", {"sessionUpdate": "agent_message_chunk",
                      "content": {"type": "text", "text": text}})
        if "도구" in text:
            update(sid, {"sessionUpdate": "tool_call", "toolCallId": "t1", "title": "Running: date"})
            send({"id": "p1", "method": "session/request_permission", "params": {
                "sessionId": sid,
                "toolCall": {"toolCallId": "t1", "title": "Running: date"},
                "options": [{"optionId": "allow_once", "kind": "allow_once"},
                            {"optionId": "reject_once", "kind": "reject_once"}]}})
            answer = read()
            chosen = answer["result"]["outcome"].get("optionId", "cancelled")
            update(sid, {"sessionUpdate": "agent_message_chunk",
                         "content": {"type": "text", "text": f" / {chosen}"}})
        send({"id": 99, "method": "fs/read_text_file", "params": {}})
        unknown = read()
        assert unknown["error"]["code"] == -32601
        send({"method": "_kiro.dev/metadata", "params": {
            "meteringUsage": [{"unit": "credit", "value": 0.25}, {"unit": "credit", "value": 0.5}]}})
        send({"id": rid, "result": {"stopReason": "end_turn"}})
