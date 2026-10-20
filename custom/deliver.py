"""결과를 받는 곳. 일(tasks/)을 한 번 돌려 결과 파일을 만든 뒤 플랫폼이 deliver()를 부른다.

- task: 일의 이름. run_once.py로 바로 맡긴 질문이면 None
- path: workspace/outbox/에 만든 결과 파일의 경로(pathlib.Path)
- text: 에이전트의 답

처음에는 아무것도 하지 않는다. 결과는 대시보드의 결과함에서 본다.
이 함수가 오류를 내면 플랫폼은 멈추지 않고 화면과 결과 파일에 오류를 적는다.

시크릿(웹훅 주소, 토큰)은 코드에 적지 않는다. 레포 맨 위의 .env 파일에 적는다.
.env는 .gitignore에 들어 있어서 커밋되지 않는다. 플랫폼이 켜질 때 .env를 환경변수로 읽는다.
    예) .env 파일 한 줄:  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

Kiro Crew에서 비슷한 곳: src/kiro_crew/cron.py(스케줄 결과를 대시보드와 Slack DM으로 보냄), src/kiro_crew/slack/
"""


def deliver(task, path, text):
    pass


# 예) Slack 채널로 보낸다. Slack 앱의 Incoming Webhook 주소가 필요하다.
#
# import json
# import os
# import urllib.request
#
# def deliver(task, path, text):
#     url = os.environ.get("SLACK_WEBHOOK_URL")
#     if not url:
#         return
#     body = json.dumps({"text": f"*{task or '바로 맡긴 질문'}*\n{text[:3000]}"}).encode("utf-8")
#     request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
#     urllib.request.urlopen(request, timeout=10)
