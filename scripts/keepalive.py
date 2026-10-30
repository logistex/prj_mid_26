# 2026-10-30 21:58 KST
"""DB에 가벼운 질의를 보내 Supabase 프로젝트가 일시정지되지 않게 함. 비밀 값은 출력하지 않음"""
import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # GitHub Actions에서는 환경 변수만 씀
    pass

import psycopg


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL 없음")
        return 1
    try:
        with psycopg.connect(url, prepare_threshold=None, connect_timeout=30) as conn:
            count = conn.execute("select count(*) from tf_mp_settings").fetchone()[0]
    except Exception as e:
        print("keepalive 실패:", type(e).__name__)
        return 1
    print("keepalive 성공, tf_mp_settings 행 수:", count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
