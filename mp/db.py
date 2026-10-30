# 2026-10-30 21:58 KST
"""DB 연결 풀. 연결은 풀에서 빌려 쓰고 화면을 그릴 때마다 새로 만들지 않음

풀에 오래 놀던 연결은 서버나 중간 장비가 이미 끊었을 수 있으므로(앱이 잠들었다 깨어난 경우 등), 빌려 주기 전에 점검하고
죽었으면 버리고 새로 만듦. 방금 쓴 연결은 점검하지 않아 왕복이 늘지 않음
"""
import time
import weakref

from psycopg_pool import ConnectionPool

IDLE_CHECK_SECONDS = 30.0  # 풀에서 이만큼 놀던 연결만 빌려 주기 전에 점검함

_last_seen = weakref.WeakKeyDictionary()  # 연결 -> 만들어졌거나 풀에 마지막으로 돌아온 시각


def _remember(conn):
    _last_seen[conn] = time.monotonic()


def _checker(check_after):
    def check(conn):
        seen = _last_seen.get(conn)
        if seen is not None and time.monotonic() - seen < check_after:
            return
        ConnectionPool.check_connection(conn)  # 빈 질의 1개(왕복 1회). 죽었으면 예외를 일으켜 풀이 연결을 버림

    return check


def make_pool(url, max_size=5, autocommit=False, check_after=IDLE_CHECK_SECONDS):
    """autocommit=True는 읽기 전용 풀용임. 질의마다 BEGIN과 COMMIT을 따로 보내지 않아 왕복이 줄어듦(쓰기 풀은 False)"""
    # Supabase 연결 풀러(포트 6543)는 트랜잭션 풀링이므로 준비된 문장을 쓰지 않음
    pool = ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        kwargs={"prepare_threshold": None, "autocommit": autocommit},
        configure=_remember,  # 연결을 만들 때
        reset=_remember,  # 풀에 돌아올 때
        check=_checker(check_after),
        open=False,
    )
    pool.open(wait=True, timeout=30)
    return pool
