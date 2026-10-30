# 2026-10-30 21:58 KST
"""커밋 전에 .env의 값이 git이 추적하는 파일에 들어 있는지 검사함. 값은 출력하지 않고 파일 이름과 있음, 없음만 출력함"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_LENGTH = 6  # 이보다 짧은 값은 부분 일치 검사가 의미 없어 건너뜀


def read_env(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main():
    env_path = ROOT / ".env"
    if not env_path.exists():
        print(".env 없음")
        return 1
    tracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"]).decode().split("\0")
    tracked = [f for f in tracked if f]
    found = False
    if ".env" in tracked:
        print(".env가 git에 추적됨: 있음")
        found = True
    for key, value in read_env(env_path).items():
        if len(value) < MIN_LENGTH:
            print(f"{key}: 값이 짧아 검사를 건너뜀")
            continue
        hits = [f for f in tracked if (ROOT / f).is_file() and value.encode() in (ROOT / f).read_bytes()]
        if hits:
            found = True
        print(f"{key}: {'있음 -> ' + ', '.join(hits) if hits else '없음'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
