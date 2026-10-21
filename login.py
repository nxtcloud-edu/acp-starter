"""샌드박스 홈에 로그인하거나 로그인 상태를 본다.

실행: python login.py claude           (claude 샌드박스에 로그인)
      python login.py codex --status   (codex 샌드박스의 로그인 상태)

샌드박스 홈(.homes/<이름>/)은 내 컴퓨터의 평소 설정과 따로 있다.
그래서 Claude와 Codex는 여기에 한 번 따로 로그인한다. Kiro는 평소 로그인을 그대로 쓴다.
"""

import shutil
import subprocess
import sys

from acp_client import AcpError, load_engine, sandbox_env


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    name = sys.argv[1]
    try:
        engine = load_engine(name)
    except AcpError as error:
        print(error)
        return
    command = engine["status"] if "--status" in sys.argv else engine["login"]
    executable = shutil.which(command[0])
    if executable is None:
        print(f"{command[0]}를 찾지 못했습니다. README의 준비 절을 보세요.")
        return
    subprocess.run([executable, *command[1:]], env=sandbox_env(name, engine))


if __name__ == "__main__":
    main()
