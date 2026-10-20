"""테스트용 가짜 로그인 명령. 실제 로그인 명령처럼 주소(와 기기 코드)를 출력하고 기다린다.

실행 인자: fake_login.py code     (주소를 보이고, 표준 입력으로 받은 코드가 good이면 성공)
          fake_login.py device   (주소와 기기 코드를 보이고 곧 성공)
"""

import sys
import time

mode = sys.argv[1] if len(sys.argv) > 1 else "code"
url = "https://example.com/oauth/authorize?code=true&state=AbCd-EfGhI"
# Claude처럼 링크 표시(OSC 8)와 색(ANSI)을 섞어 출력한다.
print(f"Opening browser to sign in…\nIf the browser didn't open, visit: \x1b]8;;{url}\x07\x1b[94m{url}\x1b[39m\x1b]8;;\x07", flush=True)
if mode == "device":
    print("Enter this one-time code \x1b[90m(expires in 15 minutes)\x1b[0m\n   \x1b[94mABCD-EFGHI\x1b[0m", flush=True)
    time.sleep(0.5)
    print("Successfully logged in", flush=True)
    sys.exit(0)
sys.stdout.write("Paste code here if prompted > ")
sys.stdout.flush()
code = sys.stdin.readline().strip()
if code == "good":
    print("Login successful.", flush=True)
    sys.exit(0)
print("Login failed: Request failed with status code 400", flush=True)
sys.exit(1)
