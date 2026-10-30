# 2026-10-30 21:58 KST
"""서비스: 관리자 계정, 로그인, 명단으로 처음 상태 만들기(1단계), 지원, 투표, 모집 마감(2단계), AI 배정과 확정(3단계), 화면용 조회

모든 함수는 DB 연결 풀을 받음. 관리자 여부는 세션 값이 아니라 DB의 is_admin으로 확인함
"""
from dataclasses import dataclass

import bcrypt
from psycopg import errors

import json

from . import ai, rules
from .config import ADMIN_STUDENT_NO, DEFAULT_STUDENT_PASSWORD
from .roster import RosterError, parse_roster


@dataclass(frozen=True)
class Result:
    status: str  # 승인, 대기, 거절, 막힘 가운데 하나
    message: str

    @property
    def text(self):
        return f"{self.status}: {self.message}"

    @property
    def ok(self):
        return self.status == "승인"


LOGIN_FAILED = Result("막힘", "학번 또는 비밀번호가 맞지 않음")

# 명단을 새로 올릴 때 지우는 테이블(자식 테이블 먼저). 아직 없는 테이블은 건너뜀
_RESET_TABLES = ("tf_mp_votes", "tf_mp_applications", "tf_mp_members", "tf_mp_teams")
_RESET_SETTINGS = ("phase", "proposal", "assign_status")


def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()


def check_password(password, hashed):
    raw = password.encode()
    if len(raw) > 72:  # bcrypt가 처리하지 못하는 길이
        return False
    try:
        return bcrypt.checkpw(raw, hashed.encode())
    except ValueError:
        return False


def ensure_admin(pool, admin_password):
    """관리자 계정을 만들거나, 비밀번호가 ADMIN_PASSWORD와 다르면 해시만 갱신함"""
    with pool.connection() as conn:
        row = conn.execute(
            "select password_hash from tf_mp_students where student_no = %s",
            (ADMIN_STUDENT_NO,),
        ).fetchone()
        if row is None:
            conn.execute(
                "insert into tf_mp_students (student_no, name, main_role, password_hash, is_admin)"
                " values (%s, '관리자', null, %s, true) on conflict (student_no) do nothing",
                (ADMIN_STUDENT_NO, hash_password(admin_password)),
            )
        elif not check_password(admin_password, row[0]):
            conn.execute(
                "update tf_mp_students set password_hash = %s where student_no = %s",
                (hash_password(admin_password), ADMIN_STUDENT_NO),
            )


def login(pool, student_no, password):
    """(Result, 계정 id)를 돌려줌. 학번과 비밀번호 중 무엇이 틀렸는지는 알리지 않음"""
    student_no = (student_no or "").strip()
    if not student_no or not password:
        return LOGIN_FAILED, None
    with pool.connection() as conn:
        row = conn.execute(
            "select id, password_hash from tf_mp_students where student_no = %s", (student_no,)
        ).fetchone()
    if row is None or not check_password(password, row[1]):
        return LOGIN_FAILED, None
    return Result("승인", "로그인함"), row[0]


def get_user(pool, user_id):
    with pool.connection() as conn:
        row = conn.execute(
            "select id, student_no, name, is_admin from tf_mp_students where id = %s", (user_id,)
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "student_no": row[1], "name": row[2], "is_admin": row[3]}


def start_roster(pool, user_id, csv_bytes, team_count):
    """명단 CSV와 팀 수로 처음 상태를 만듦. 중간에 실패하면 이전 상태를 유지함(관리자만)"""
    with pool.connection() as conn:
        row = conn.execute(
            "select is_admin from tf_mp_students where id = %s", (user_id,)
        ).fetchone()
    if row is None or not row[0]:
        return Result("막힘", "관리자만 할 수 있음")
    if csv_bytes is None:
        return Result("막힘", "명단 CSV 파일을 올리지 않음")
    try:
        team_count = int(team_count)
    except (TypeError, ValueError):
        return Result("막힘", "팀 수가 올바르지 않음")
    if team_count < 1:
        return Result("막힘", "팀 수는 1 이상이어야 함")
    try:
        students = parse_roster(csv_bytes)
    except RosterError as e:
        return Result("막힘", str(e))

    # 해시는 느리므로 트랜잭션을 열기 전에 계산함
    hashes = [hash_password(DEFAULT_STUDENT_PASSWORD) for _ in students]

    with pool.connection() as conn:
        for table in _RESET_TABLES:
            if conn.execute("select to_regclass(%s)", (table,)).fetchone()[0] is not None:
                conn.execute(f"delete from {table}")
        conn.execute("delete from tf_mp_students where not is_admin")
        conn.execute("delete from tf_mp_settings where key = any(%s)", (list(_RESET_SETTINGS),))
        conn.execute("insert into tf_mp_settings (key, value) values ('phase', 'open')")
        for n in range(1, team_count + 1):
            conn.execute("insert into tf_mp_teams (team_no, name) values (%s, %s)", (n, f"팀{n}"))
        for s, password_hash in zip(students, hashes):
            student_id = conn.execute(
                "insert into tf_mp_students (student_no, name, main_role, password_hash, is_admin)"
                " values (%s, %s, %s, %s, false) returning id",
                (s["student_no"], s["name"], s["main_role"], password_hash),
            ).fetchone()[0]
            for role in s["sub_roles"]:
                conn.execute(
                    "insert into tf_mp_student_sub_roles (student_id, role) values (%s, %s)",
                    (student_id, role),
                )
    return Result("승인", f"학생 {len(students)}명과 빈 팀 {team_count}개로 처음 상태를 만듦")


_SUB_ROLES_SQL = (
    "coalesce((select string_agg(r.role, ';' order by r.role)"
    " from tf_mp_student_sub_roles r where r.student_id = s.id), '')"
)


def _split_roles(text):
    return [r for r in text.split(";") if r]


def _load(conn):
    """화면에 그릴 팀 목록, 대기 지원, 팀이 없는 학생을 읽음. 질의 4회(사용자 조회까지 하면 6회)"""
    teams = conn.execute("select id, team_no, name from tf_mp_teams order by team_no").fetchall()
    members = conn.execute(
        "select m.team_id, s.id, s.student_no, s.name, s.main_role, " + _SUB_ROLES_SQL +
        " from tf_mp_members m join tf_mp_students s on s.id = m.student_id"
        " order by m.team_id, m.slot_no"
    ).fetchall()
    unassigned = conn.execute(
        "select s.id, s.student_no, s.name, s.main_role, " + _SUB_ROLES_SQL +
        " from tf_mp_students s where not s.is_admin"
        " and not exists (select 1 from tf_mp_members m where m.student_id = s.id)"
        " order by s.student_no"
    ).fetchall()
    phase = conn.execute("select value from tf_mp_settings where key = 'phase'").fetchone()
    pending = conn.execute(
        "select a.id, a.team_id, s.id, s.student_no, s.name, s.main_role, " + _SUB_ROLES_SQL + ","
        " coalesce((select json_agg(json_build_object('voter_id', v.voter_id, 'vote', v.vote))"
        "  from tf_mp_votes v where v.application_id = a.id), '[]'::json)"
        " from tf_mp_applications a join tf_mp_students s on s.id = a.student_id"
        " where a.status = '대기' order by a.id"
    ).fetchall()

    def person(sid, student_no, name, main_role, subs):
        return {
            "id": sid, "student_no": student_no, "name": name,
            "main_role": main_role, "sub_roles": _split_roles(subs),
        }

    by_team = {t[0]: {"members": [], "pending": []} for t in teams}
    for team_id, sid, student_no, name, main_role, subs in members:
        by_team[team_id]["members"].append(person(sid, student_no, name, main_role, subs))
    for app_id, team_id, sid, student_no, name, main_role, subs, votes in pending:
        entry = person(sid, student_no, name, main_role, subs)
        entry["application_id"] = app_id
        entry["votes"] = {v["voter_id"]: v["vote"] for v in votes}
        by_team[team_id]["pending"].append(entry)
    return {
        "phase": phase[0] if phase else None,
        "teams": [
            {"id": team_id, "team_no": team_no, "name": name, **by_team[team_id]}
            for team_id, team_no, name in teams
        ],
        "unassigned": [person(*row) for row in unassigned],
    }


def load_view(pool):
    with pool.connection() as conn:
        return _load(conn)


def load_page(pool, user_id):
    """(사용자, 화면 내용)을 연결 1개로 읽음. 계정이 없으면 (None, None)"""
    with pool.connection() as conn:
        row = conn.execute(
            "select id, student_no, name, is_admin from tf_mp_students where id = %s", (user_id,)
        ).fetchone()
        if row is None:
            return None, None
        user = {"id": row[0], "student_no": row[1], "name": row[2], "is_admin": row[3]}
        return user, _load(conn)


# ---- 2단계: 지원, 투표, 모집 마감 ----
# 상태를 바꾸는 함수는 phase 행을 공유 잠금(마감은 배타 잠금)으로 읽은 뒤 팀 행을 for update로 잠금.
# 잠금은 규칙 검사의 일관성을 지키고, DB 제약은 마지막 방어선임(PRD_step2 7장)


def _lock_phase(conn, exclusive=False):
    lock = "update" if exclusive else "share"
    row = conn.execute(f"select value from tf_mp_settings where key = 'phase' for {lock}").fetchone()
    return row[0] if row else None


def _student(conn, student_id):
    row = conn.execute(
        "select s.id, s.student_no, s.name, s.main_role, s.is_admin, " + _SUB_ROLES_SQL +
        " from tf_mp_students s where s.id = %s", (student_id,)
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "student_no": row[1], "name": row[2], "main_role": row[3],
        "is_admin": row[4], "sub_roles": _split_roles(row[5]),
    }


def _team_members(conn, team_id):
    rows = conn.execute(
        "select s.id, s.student_no, s.name, s.main_role, " + _SUB_ROLES_SQL +
        " from tf_mp_members m join tf_mp_students s on s.id = m.student_id"
        " where m.team_id = %s order by m.slot_no", (team_id,)
    ).fetchall()
    return [
        {"id": r[0], "student_no": r[1], "name": r[2], "main_role": r[3], "sub_roles": _split_roles(r[4])}
        for r in rows
    ]


def _join(conn, team_id, student_id):
    """비어 있는 가장 작은 정원 번호에 넣음. 유일성 제약에 걸리면 UniqueViolation이 남"""
    used = {r[0] for r in conn.execute("select slot_no from tf_mp_members where team_id = %s", (team_id,))}
    slot = next(n for n in range(1, rules.MAX_TEAM_SIZE + 1) if n not in used)
    conn.execute(
        "insert into tf_mp_members (team_id, slot_no, student_id) values (%s, %s, %s)",
        (team_id, slot, student_id),
    )


def _decide_application(conn, application_id, status, reason):
    conn.execute(
        "update tf_mp_applications set status = %s, reason = %s, decided_at = now() where id = %s",
        (status, reason, application_id),
    )
    return Result(status, reason)


def apply_to_team(pool, user_id, team_no):
    """지원 단추. 접수 검사(PRD_step2 4.1절)를 통과하지 못하면 DB에 기록하지 않고 막힘"""
    try:
        with pool.connection() as conn:
            return _apply(conn, user_id, team_no)
    except errors.UniqueViolation:
        return Result("막힘", "같은 시각에 다른 요청이 먼저 처리됨")


def _apply(conn, user_id, team_no):
    phase = _lock_phase(conn)
    user = _student(conn, user_id)
    if user is None:
        return Result("막힘", "계정이 없음")
    if phase != "open":
        return Result("막힘", "아직 명단이 올라오지 않음" if phase is None else "모집이 마감됨")
    if user["is_admin"]:
        return Result("막힘", "학생만 지원할 수 있음")
    team = conn.execute(
        "select id from tf_mp_teams where team_no = %s for update", (team_no,)
    ).fetchone()
    if team is None:
        return Result("막힘", "없는 팀임")
    team_id = team[0]
    if conn.execute("select 1 from tf_mp_members where student_id = %s", (user_id,)).fetchone():
        return Result("막힘", "이미 팀이 있음")
    if conn.execute(
        "select 1 from tf_mp_applications where student_id = %s and status = '대기'", (user_id,)
    ).fetchone():
        return Result("막힘", "결과를 기다리는 지원이 있음")
    members = _team_members(conn, team_id)
    reason = rules.join_violation(members, user)
    if reason:
        return Result("막힘", reason)
    if not members:
        _join(conn, team_id, user_id)
        conn.execute(
            "insert into tf_mp_applications (team_id, student_id, status, reason, decided_at)"
            " values (%s, %s, '승인', '빈 팀이라 바로 팀원이 됨', now())",
            (team_id, user_id),
        )
        return Result("승인", "빈 팀이라 바로 팀원이 됨")
    conn.execute(
        "insert into tf_mp_applications (team_id, student_id, status) values (%s, %s, '대기')",
        (team_id, user_id),
    )
    return Result("대기", f"팀원 {len(members)}명의 투표를 기다림")


def vote(pool, user_id, applicant_no, choice):
    """찬성, 거부 단추. choice는 '찬성' 또는 '거부'. applicant_no는 지원자의 학번"""
    with pool.connection() as conn:
        return _vote(conn, user_id, applicant_no, choice)


def _vote(conn, user_id, applicant_no, choice):
    if choice not in ("찬성", "거부"):
        return Result("막힘", "투표 값이 올바르지 않음")
    if _student(conn, user_id) is None:
        return Result("막힘", "계정이 없음")
    found = conn.execute(
        "select a.id, a.team_id from tf_mp_applications a join tf_mp_students s on s.id = a.student_id"
        " where s.student_no = %s order by a.id desc limit 1", (applicant_no,)
    ).fetchone()
    if found is None:
        return Result("막힘", "지원이 없음")
    application_id, team_id = found
    _lock_phase(conn)
    conn.execute("select 1 from tf_mp_teams where id = %s for update", (team_id,))
    status, reason, applicant_id = conn.execute(
        "select status, reason, student_id from tf_mp_applications where id = %s for update",
        (application_id,),
    ).fetchone()
    if status != "대기":
        # 화면이 갱신되기 전에 누른 경우: 막힘이 아니라 그 지원의 지금 상태를 보여 줌(공고 2.7절)
        return Result(status, reason or "이미 결과가 나옴")
    if not conn.execute(
        "select 1 from tf_mp_members where team_id = %s and student_id = %s", (team_id, user_id)
    ).fetchone():
        return Result("막힘", "이 팀의 팀원만 투표할 수 있음")
    already = Result("막힘", "이미 투표함(바꿀 수 없음)")
    if conn.execute(
        "select 1 from tf_mp_votes where application_id = %s and voter_id = %s", (application_id, user_id)
    ).fetchone():
        return already
    try:
        with conn.transaction():
            conn.execute(
                "insert into tf_mp_votes (application_id, voter_id, vote) values (%s, %s, %s)",
                (application_id, user_id, choice),
            )
    except errors.UniqueViolation:
        return already
    return _judge(conn, application_id, team_id, applicant_id)


def _judge(conn, application_id, team_id, applicant_id):
    """투표를 기록한 직후의 판정(PRD_step2 5.2절). 같은 트랜잭션에서 함"""
    members = _team_members(conn, team_id)
    votes = dict(conn.execute(
        "select voter_id, vote from tf_mp_votes where application_id = %s", (application_id,)
    ).fetchall())
    if any(v == "거부" for v in votes.values()):
        return _decide_application(conn, application_id, "거절", "팀원이 거부함")
    if all(votes.get(m["id"]) == "찬성" for m in members):
        # 승인 직전 재검사: 팀 구성이 지원한 뒤에 바뀌었을 수 있음
        if conn.execute("select 1 from tf_mp_members where student_id = %s", (applicant_id,)).fetchone():
            return _decide_application(conn, application_id, "거절", "승인 직전 검사: 이미 다른 팀에 있음")
        reason = rules.join_violation(members, _student(conn, applicant_id))
        if reason:
            return _decide_application(conn, application_id, "거절", f"승인 직전 검사: {reason}")
        try:
            with conn.transaction():
                _join(conn, team_id, applicant_id)
        except errors.UniqueViolation:
            return _decide_application(conn, application_id, "거절", "먼저 도착한 지원이 정원을 차지함")
        return _decide_application(conn, application_id, "승인", "팀원이 되었음")
    yes = sum(1 for m in members if votes.get(m["id"]) == "찬성")
    waiting = sum(1 for m in members if m["id"] not in votes)
    return Result("대기", f"찬성 {yes}명, 투표하지 않은 팀원 {waiting}명")


def close_recruitment(pool, user_id):
    """모집 마감 단추(관리자만). 대기 지원을 모두 거절하고, 팀원이 1명뿐인 팀에서 그 학생을 뺌"""
    with pool.connection() as conn:
        row = conn.execute("select is_admin from tf_mp_students where id = %s", (user_id,)).fetchone()
        if row is None or not row[0]:
            return Result("막힘", "관리자만 할 수 있음")
        if _lock_phase(conn, exclusive=True) != "open":
            return Result("막힘", "모집 중일 때만 마감할 수 있음")
        conn.execute("update tf_mp_settings set value = 'closed' where key = 'phase'")
        rejected = conn.execute(
            "update tf_mp_applications set status = '거절', reason = '모집 마감', decided_at = now()"
            " where status = '대기' returning id"
        ).fetchall()
        removed = conn.execute(
            "delete from tf_mp_members where team_id in"
            " (select team_id from tf_mp_members group by team_id having count(*) = 1)"
            " returning student_id"
        ).fetchall()
    return Result("승인", f"모집을 마감함. 대기 지원 {len(rejected)}건을 거절하고 {len(removed)}명이 팀에서 빠짐")


# ---- 3단계: AI 배정과 확정(PRD_step3) ----

def _set_setting(conn, key, value):
    conn.execute(
        "insert into tf_mp_settings (key, value) values (%s, %s)"
        " on conflict (key) do update set value = excluded.value",
        (key, value),
    )


def get_setting(pool, key):
    with pool.connection() as conn:
        row = conn.execute("select value from tf_mp_settings where key = %s", (key,)).fetchone()
    return row[0] if row else None


def set_assign_status(pool, text):
    with pool.connection() as conn:
        _set_setting(conn, "assign_status", text)


def _is_admin(conn, user_id):
    row = conn.execute("select is_admin from tf_mp_students where id = %s", (user_id,)).fetchone()
    return bool(row and row[0])


def _teams_and_unassigned(conn):
    """배정 입력: 지금의 팀 구성과 팀이 없는 학생. 학생은 id, student_no, name, main_role, sub_roles를 가짐"""
    view = _load(conn)
    teams = [
        {"id": t["id"], "team_no": t["team_no"], "name": t["name"], "members": t["members"]}
        for t in view["teams"]
    ]
    return view["phase"], teams, view["unassigned"]


@dataclass
class Prep:
    """배정을 시작하기 전의 준비 결과. result가 있으면 거기서 끝남(막힘). 없으면 AI를 부를 수 있음"""
    result: object = None
    teams: list = None
    unassigned: list = None
    fallback: list = None


def prepare_assignment(pool, user_id):
    """사전 검사와 규칙을 지키는 배정 찾기(PRD_step3 3장 1, 2번). 규칙을 지키는 배정이 없으면 AI를 부르지 않음"""
    with pool.connection() as conn:
        if not _is_admin(conn, user_id):
            return Prep(Result("막힘", "관리자만 할 수 있음"))
        phase, teams, unassigned = _teams_and_unassigned(conn)
    if phase is None:
        return Prep(Result("막힘", "아직 명단이 올라오지 않음"))
    if phase == "open":
        return Prep(Result("막힘", "모집을 마감한 뒤에 배정할 수 있음"))
    if phase == "confirmed":
        return Prep(Result("막힘", "이미 확정함"))
    if not unassigned:
        return Prep(Result("막힘", "팀이 없는 학생이 없음"))
    pairs, timed_out = rules.find_assignment(teams, unassigned)
    if pairs is None:
        if timed_out:
            reason = "규칙을 지키는 배정을 찾지 못함(탐색 시간 초과)"
        else:
            reason = rules.explain_no_assignment(teams, unassigned)
        set_assign_status(pool, f"규칙을 지키는 배정이 없음: {reason}" if not timed_out else reason)
        return Prep(Result("막힘", "규칙을 지키는 배정이 없음"), teams, unassigned)
    return Prep(None, teams, unassigned, pairs)


def log_attempt(pool, attempt_no, attempt):
    with pool.connection() as conn:
        conn.execute(
            "insert into tf_mp_ai_logs (model, attempt_no, outcome, seconds, detail,"
            " finish_reason, prompt_tokens, completion_tokens, reasoning_tokens, response_head)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (attempt.model, attempt_no, attempt.outcome, round(attempt.seconds, 1), attempt.detail or None,
             attempt.finish_reason or None, attempt.prompt_tokens, attempt.completion_tokens,
             attempt.reasoning_tokens, attempt.head or None),
        )


def recent_ai_logs(pool, limit=10):
    with pool.connection() as conn:
        return conn.execute(
            "select to_char(created_at at time zone 'Asia/Seoul', 'MM-DD HH24:MI:SS'),"
            " attempt_no, model, outcome, seconds, coalesce(detail, '')"
            " from tf_mp_ai_logs order by id desc limit %s", (limit,)
        ).fetchall()


def generate_proposal(pool, prep, ask, models, limit, progress):
    """AI에게 배정안을 받고, 3차까지 실패하면 앱이 찾은 배정을 씀. 검사를 통과한 배정안만 proposal로 저장함

    ask(번호, 모델, tick)는 ai.Attempt를 돌려주는 함수임. 모델을 부르는 동안 DB 연결을 잡고 있지 않음
    """
    by_no = {s["student_no"]: s for s in prep.unassigned}

    def check(pairs):
        return rules.check_assignment(prep.teams, prep.unassigned, pairs)

    pairs, source, _ = ai.propose(
        models, ask, prep.fallback, lambda n, a: log_attempt(pool, n, a), progress, limit
    )
    problem = check(pairs)
    if problem:  # 앱이 찾은 배정도 같은 검사를 통과해야 보여 줌
        progress.note(f"배정안이 검사를 통과하지 못함: {problem}")
        set_assign_status(pool, progress.text())
        return Result("막힘", "검사를 통과한 배정안이 없음")
    progress.note(f"검사를 통과한 배정안을 만듦(출처: {source})")
    proposal = {"source": source, "pairs": [[no, team_no] for no, team_no in pairs]}
    with pool.connection() as conn:
        _set_setting(conn, "proposal", json.dumps(proposal, ensure_ascii=False))
        _set_setting(conn, "assign_status", progress.text())
    return Result("승인", f"배정안을 만듦({source})")


def load_proposal(pool):
    raw = get_setting(pool, "proposal")
    return json.loads(raw) if raw else None


def confirm_assignment(pool, user_id):
    """배정안 확정(PRD_step3 7.2절). 한 트랜잭션에서 현재 구성으로 다시 검사한 뒤 팀원으로 저장함"""
    mismatch = Result("막힘", "배정안이 현재 팀 구성과 맞지 않음. 다시 배정해야 함")
    with pool.connection() as conn:
        if not _is_admin(conn, user_id):
            return Result("막힘", "관리자만 할 수 있음")
        phase = _lock_phase(conn, exclusive=True)
        if phase == "confirmed":
            return Result("막힘", "이미 확정함")
        if phase != "closed":
            return Result("막힘", "모집을 마감한 뒤에 확정할 수 있음")
        row = conn.execute("select value from tf_mp_settings where key = 'proposal'").fetchone()
        if row is None:
            return Result("막힘", "확정할 배정안이 없음")
        pairs = [(no, team_no) for no, team_no in json.loads(row[0])["pairs"]]
        conn.execute("select 1 from tf_mp_teams order by id for update").fetchall()  # 팀 행을 id 순서로 모두 잠금
        _, teams, unassigned = _teams_and_unassigned(conn)
        if rules.check_assignment(teams, unassigned, pairs):
            return mismatch
        team_id_of = {t["team_no"]: t["id"] for t in teams}
        student_id_of = {s["student_no"]: s["id"] for s in unassigned}
        try:
            with conn.transaction():
                for no, team_no in pairs:
                    _join(conn, team_id_of[team_no], student_id_of[no])
        except errors.UniqueViolation:
            return mismatch
        conn.execute("update tf_mp_settings set value = 'confirmed' where key = 'phase'")
        conn.execute("delete from tf_mp_settings where key = 'proposal'")
        _set_setting(conn, "assign_status", "배정안을 확정함")
    return Result("승인", "배정안을 확정함")
