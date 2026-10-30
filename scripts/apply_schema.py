# 2026-10-30 21:58 KST
"""schema.sql을 DB에 적용함. 비밀 값은 출력하지 않음"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mp.config import get_secret  # noqa: E402
from mp.db import make_pool  # noqa: E402


def main():
    url = get_secret("DATABASE_URL")
    if not url:
        print("DATABASE_URL 없음")
        return 1
    sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
    try:
        pool = make_pool(url, max_size=1)
        with pool.connection() as conn:
            conn.execute(sql)
        pool.close()
    except Exception as e:
        print("스키마 적용 실패:", type(e).__name__)
        return 1
    print("스키마 적용됨")
    return 0


if __name__ == "__main__":
    sys.exit(main())
