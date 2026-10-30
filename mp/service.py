# 2026-10-30 21:58 KST
"""1단계 서비스: 관리자 계정, 로그인, 명단으로 처음 상태 만들기, 화면용 조회

모든 함수는 DB 연결 풀을 받음. 관리자 여부는 세션 값이 아니라 DB의 is_admin으로 확인함
"""
from dataclasses import dataclass

import bcrypt

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


def load_view(pool):
    """화면에 그릴 팀 목록과 팀이 없는 학생을 읽음. 질의 4회, 연결 1개"""
    with pool.connection() as conn:
        teams = conn.execute("select id, team_no, name from tf_mp_teams order by team_no").fetchall()
        members = conn.execute(
            "select m.team_id, s.id, s.name, s.main_role, " + _SUB_ROLES_SQL +
            " from tf_mp_members m join tf_mp_students s on s.id = m.student_id"
            " order by m.team_id, m.slot_no"
        ).fetchall()
        unassigned = conn.execute(
            "select s.id, s.name, s.main_role, " + _SUB_ROLES_SQL +
            " from tf_mp_students s where not s.is_admin"
            " and not exists (select 1 from tf_mp_members m where m.student_id = s.id)"
            " order by s.student_no"
        ).fetchall()
        phase = conn.execute("select value from tf_mp_settings where key = 'phase'").fetchone()

    by_team = {t[0]: [] for t in teams}
    for team_id, sid, name, main_role, subs in members:
        by_team[team_id].append(
            {"id": sid, "name": name, "main_role": main_role, "sub_roles": _split_roles(subs)}
        )
    return {
        "phase": phase[0] if phase else None,
        "teams": [
            {"team_no": team_no, "name": name, "members": by_team[team_id]}
            for team_id, team_no, name in teams
        ],
        "unassigned": [
            {"id": sid, "name": name, "main_role": main_role, "sub_roles": _split_roles(subs)}
            for sid, name, main_role, subs in unassigned
        ],
    }
