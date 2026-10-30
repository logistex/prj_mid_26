# 2026-10-30 21:58 KST
"""DB 연결 풀. 연결은 풀에서 빌려 쓰고 화면을 그릴 때마다 새로 만들지 않음"""
from psycopg_pool import ConnectionPool


def make_pool(url, max_size=5, autocommit=False):
    """autocommit=True는 읽기 전용 풀용임. 질의마다 BEGIN과 COMMIT을 따로 보내지 않아 왕복이 줄어듦(쓰기 풀은 False)"""
    # Supabase 연결 풀러(포트 6543)는 트랜잭션 풀링이므로 준비된 문장을 쓰지 않음
    pool = ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        kwargs={"prepare_threshold": None, "autocommit": autocommit},
        open=False,
    )
    pool.open(wait=True, timeout=30)
    return pool
