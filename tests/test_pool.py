# 2026-10-31 00:30 KST
"""연결 풀이 죽은 연결을 알아채고 새로 만드는지 시험함(앱이 잠들었다 깨어났을 때를 재현). 실제 DB에 select 1만 보냄

죽은 연결은 풀에 돌아가 있는 연결의 소켓을 강제로 끊어 만듦(서버나 중간 장비가 끊은 것과 같은 상태)
"""
import os
import socket
import time

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from mp.config import get_secret
from mp.db import make_pool

pytestmark = pytest.mark.skipif(not get_secret("DATABASE_URL"), reason="DATABASE_URL 없음")


def kill_socket(conn):
    s = socket.socket(fileno=os.dup(conn.fileno()))
    s.shutdown(socket.SHUT_RDWR)
    s.detach()


def use(pool):
    with pool.connection() as c:
        return c.execute("select 1").fetchone()[0]


def attempts(pool, n=3):
    out = []
    for _ in range(n):
        try:
            out.append("성공" if use(pool) == 1 else "?")
        except psycopg.OperationalError:
            out.append("실패")
    return out


def idle_then_kill(pool):
    """연결을 1번 쓰고 풀에 돌려놓은 뒤 소켓을 끊음"""
    with pool.connection() as c:
        c.execute("select 1").fetchone()
        victim = c
    kill_socket(victim)


@pytest.fixture
def url():
    return get_secret("DATABASE_URL")


def test_premise_a_plain_pool_hands_out_the_dead_connection_once(url):
    # 점검이 없는 풀: 끊긴 뒤 첫 사용이 실패하고, 풀이 그 연결을 버린 뒤에야 성공함(이 문제를 고쳤다는 근거가 되는 재현)
    pool = ConnectionPool(url, min_size=1, max_size=1, kwargs={"prepare_threshold": None}, open=True)
    pool.wait(timeout=30)
    try:
        idle_then_kill(pool)
        assert attempts(pool) == ["실패", "성공", "성공"]
    finally:
        pool.close()


@pytest.mark.parametrize("autocommit", [False, True], ids=["write_pool", "read_pool"])
def test_make_pool_replaces_a_dead_idle_connection_without_error(url, autocommit):
    pool = make_pool(url, max_size=1, autocommit=autocommit, check_after=0.5)
    try:
        idle_then_kill(pool)
        time.sleep(0.7)  # 풀에서 점검 기준 시간보다 오래 놀게 함
        assert attempts(pool) == ["성공", "성공", "성공"]
    finally:
        pool.close()


def count_round_trips(fn):
    n = [0]
    original = psycopg.Connection.wait

    def counting(self, *a, **k):
        n[0] += 1
        return original(self, *a, **k)

    psycopg.Connection.wait = counting
    try:
        fn()
    finally:
        psycopg.Connection.wait = original
    return n[0]


def test_a_connection_used_just_now_is_not_checked_so_no_extra_round_trip(url):
    pool = make_pool(url, max_size=1, autocommit=True, check_after=30)
    try:
        use(pool)
        assert count_round_trips(lambda: use(pool)) == 2  # 질의 1개. 점검 왕복이 없음
    finally:
        pool.close()


def test_a_connection_idle_longer_than_the_limit_costs_one_check_round_trip(url):
    pool = make_pool(url, max_size=1, autocommit=True, check_after=0.5)
    try:
        use(pool)
        time.sleep(0.7)
        assert count_round_trips(lambda: use(pool)) == 3  # 점검 1회 + 질의 1개
        assert count_round_trips(lambda: use(pool)) == 2  # 방금 썼으므로 다시 점검하지 않음
    finally:
        pool.close()


def test_a_connection_killed_within_the_limit_fails_once_then_recovers(url):
    # 알려진 한계: 방금 쓴 연결은 점검하지 않으므로, 그 사이에 끊기면 첫 사용이 실패함(풀이 버린 뒤에는 성공)
    pool = make_pool(url, max_size=1, check_after=30)
    try:
        idle_then_kill(pool)
        assert attempts(pool) == ["실패", "성공", "성공"]
    finally:
        pool.close()


def test_a_connection_the_pool_made_in_advance_and_nobody_used_is_checked_too(url):
    # 풀을 열 때 미리 만든 연결도 아무도 안 쓰고 오래 놀다 끊길 수 있음: 만들어진 시각부터 센다(psycopg_pool의 내부 목록 _pool을 읽음)
    pool = make_pool(url, max_size=1, check_after=0.5)
    try:
        idle = list(pool._pool)
        assert len(idle) == 1, "풀이 미리 만든 연결을 찾지 못함"
        kill_socket(idle[0])
        time.sleep(0.7)
        assert attempts(pool) == ["성공", "성공", "성공"]
    finally:
        pool.close()
