# 2026-10-30 22:55 KST
"""연습용 시나리오 재현 시험(PRD_step2 10.2절). 학생마다 별도의 앱 세션(AppTest)을 만들어 key로 단추를 누르고,
단계마다 result의 첫 낱말이 공고 부록의 기대 결과와 같은지 비교함. 실제 Supabase DB의 tf_mp_ 테이블을 씀

공고 부록의 단계 표를 그대로 옮김. 한 단계 안에 동작이 여럿이면 적힌 순서대로 하고, 막힌 지원 뒤의 투표는 건너뜀
`pytest -s tests/test_scenarios.py`로 실행하면 단계별 표가 출력됨
"""
import pytest
from streamlit.testing.v1 import AppTest

from conftest import DATA, ROOT
from mp import service
from mp.config import get_secret
from mp.db import make_pool

pytestmark = pytest.mark.skipif(
    not (get_secret("DATABASE_URL") and get_secret("ADMIN_PASSWORD")), reason="DATABASE_URL 또는 ADMIN_PASSWORD 없음"
)

APP = str(ROOT / "streamlit_app.py")
YES, NO = "찬성", "거부"


class Session:
    """한 학생의 브라우저 1개. 단추를 누르기 전에 화면을 다시 그려 다른 사람의 변경을 반영함"""

    def __init__(self, student_no, password="1234"):
        self.student_no = student_no
        self.at = AppTest.from_file(APP, default_timeout=60)
        self.at.run()
        self.at.text_input(key="login_student_no").set_value(student_no)
        self.at.text_input(key="login_password").set_value(password)
        self.at.button(key="login_submit").click().run()
        assert not self.at.exception
        assert self.result().startswith("승인"), f"{student_no} 로그인 실패: {self.result()}"

    def result(self):
        return " ".join(e.value for e in self.at.get_by_key("result").text)

    def press(self, key):
        """(결과 안내, 단추가 없었는지). 단추가 없으면 공고 2.7절에 따라 막힘으로 봄"""
        self.at.run()
        try:
            button = self.at.button(key=key)
        except Exception:
            return "막힘: (단추가 없음)", True
        button.click().run()
        assert not self.at.exception
        return self.result(), False


# (단계 번호, [동작...]). 동작: ("지원", 학생 번호, 팀 번호, 기대), ("투표", 투표자, 지원자, 찬성 또는 거부, 기대), ("마감", 기대)
SCENARIOS = {
    "쉬움": {
        "csv": "쉬움.csv", "base": 2026100, "teams": 3,
        "steps": [
            (1, [("지원", 1, 1, "승인"), ("지원", 2, 2, "승인"), ("지원", 3, 3, "승인")]),
            (2, [("지원", 4, 1, "대기"), ("투표", 1, 4, YES, "승인")]),
            (3, [("지원", 5, 2, "대기"), ("투표", 2, 5, YES, "승인")]),
            (4, [("지원", 7, 1, "대기"), ("투표", 1, 7, YES, "대기"), ("투표", 4, 7, NO, "거절")]),
            (5, [("지원", 6, 3, "대기"), ("투표", 3, 6, YES, "승인")]),
        ],
    },
    "중간": {
        "csv": "중간.csv", "base": 2026200, "teams": 4,
        "steps": [
            (1, [("지원", 1, 1, "승인")]),
            (2, [("지원", 5, 1, "대기"), ("투표", 1, 5, YES, "승인")]),
            (3, [("지원", 2, 1, "막힘")]),  # 주 역할 중복. 뒤의 투표(학생1, 학생5)는 건너뜀
            (4, [("지원", 6, 2, "승인")]),
            (5, [("지원", 9, 2, "대기"), ("투표", 6, 9, YES, "승인")]),
            (6, [("지원", 10, 2, "대기"), ("투표", 6, 10, YES, "대기"), ("투표", 9, 10, NO, "거절")]),
            (7, [("지원", 3, 3, "승인"), ("지원", 11, 4, "승인")]),
            (8, [("지원", 12, 4, "대기"), ("지원", 12, 3, "막힘")]),
            (9, [("마감", "승인")]),
            (10, [("지원", 2, 3, "막힘")]),
        ],
    },
    "어려움": {
        "csv": "어려움.csv", "base": 2026300, "teams": 4,
        "steps": [
            (1, [("지원", 1, 1, "승인")]),
            (2, [("지원", 4, 1, "대기"), ("투표", 1, 4, YES, "승인")]),
            (3, [("지원", 7, 1, "대기"), ("투표", 1, 7, YES, "대기"), ("투표", 4, 7, YES, "승인")]),
            (4, [("지원", 2, 2, "승인")]),
            (5, [("지원", 8, 2, "대기"), ("투표", 2, 8, YES, "승인")]),
            (6, [("지원", 5, 2, "대기"), ("지원", 6, 2, "대기")]),
            (7, [("투표", 2, 5, YES, "대기"), ("투표", 8, 5, YES, "승인")]),
            (8, [("투표", 2, 6, YES, "대기"), ("투표", 8, 6, YES, "대기"), ("투표", 5, 6, YES, "거절")]),
            (9, [("지원", 11, 3, "승인")]),
            (10, [("지원", 15, 3, "대기"), ("투표", 11, 15, YES, "승인")]),
            (11, [("지원", 14, 3, "막힘")]),  # 필수 포함 역할 자리 부족. 뒤의 투표(학생11, 학생15)는 건너뜀
            (12, [("지원", 10, 4, "승인")]),
            (13, [("지원", 13, 1, "대기"), ("투표", 1, 13, YES, "대기")]),
            (14, [("마감", "승인")]),
        ],
    },
}


def reset(name):
    spec = SCENARIOS[name]
    pool = make_pool(get_secret("DATABASE_URL"), max_size=2)
    try:
        _, admin_id = service.login(pool, "admin", get_secret("ADMIN_PASSWORD"))
        res = service.start_roster(pool, admin_id, (DATA / spec["csv"]).read_bytes(), spec["teams"])
        assert res.ok, res.text
    finally:
        pool.close()


def query(sql, args=()):
    pool = make_pool(get_secret("DATABASE_URL"), max_size=1)
    try:
        with pool.connection() as conn:
            return conn.execute(sql, args).fetchall()
    finally:
        pool.close()


def application_status(student_no):
    rows = query(
        "select a.status, a.reason from tf_mp_applications a join tf_mp_students s on s.id = a.student_id"
        " where s.student_no = %s order by a.id desc limit 1", (student_no,)
    )
    return rows[0] if rows else None


def member_numbers():
    return {r[0] for r in query(
        "select s.student_no from tf_mp_members m join tf_mp_students s on s.id = m.student_id"
    )}


def run_scenario(name):
    spec = SCENARIOS[name]
    base = spec["base"]
    reset(name)
    sessions = {}

    def session(i):
        key = "admin" if i == "admin" else str(base + i)
        if key not in sessions:
            sessions[key] = Session(key, get_secret("ADMIN_PASSWORD") if key == "admin" else "1234")
        return sessions[key]

    rows = []
    for step_no, actions in spec["steps"]:
        for act in actions:
            if act[0] == "지원":
                _, who, team, expected = act
                text, hidden = session(who).press(f"apply_{team}")
                desc = f"학생{who}가 팀{team}에 지원"
            elif act[0] == "투표":
                _, voter, applicant, choice, expected = act
                key = ("vote_yes_" if choice == YES else "vote_no_") + str(base + applicant)
                text, hidden = session(voter).press(key)
                desc = f"학생{voter}가 학생{applicant}에 {choice}"
            else:
                _, expected = act
                text, hidden = session("admin").press("admin_close")
                desc = "관리자가 모집 마감"
            actual = text.split(":")[0]
            rows.append((name, step_no, desc, expected, actual, text + (" [단추 없음]" if hidden else "")))
    return rows, base


def print_table(rows):
    print()
    print("| 시나리오 | 단계 | 동작 | 기대 | 실제 | 일치 | result 전문 |")
    for name, step, desc, expected, actual, text in rows:
        print(f"| {name} | {step} | {desc} | {expected} | {actual} | {'O' if expected == actual else 'X'} | {text} |")


def assert_all_match(rows):
    print_table(rows)
    wrong = [r for r in rows if r[3] != r[4]]
    assert not wrong, f"기대와 다른 단계 {len(wrong)}개: {wrong[:3]}"


def test_easy_steps_1_to_5():
    rows, base = run_scenario("쉬움")
    assert_all_match(rows)
    # 단계 5까지 끝난 뒤의 팀 구성(부록 1 단계 6 직전)
    assert member_numbers() == {str(base + i) for i in (1, 2, 3, 4, 5, 6)}
    assert application_status(str(base + 7))[0] == "거절"


def test_middle_steps_1_to_10():
    rows, base = run_scenario("중간")
    assert_all_match(rows)
    # 단계 9: 학생12의 대기 지원은 거절되고, 학생3과 학생11은 1명뿐인 팀에서 빠짐
    assert application_status(str(base + 12)) == ("거절", "모집 마감")
    assert member_numbers() == {str(base + i) for i in (1, 5, 6, 9)}
    assert application_status(str(base + 10))[0] == "거절"
    unassigned = {r[0] for r in query(
        "select student_no from tf_mp_students s where not is_admin"
        " and not exists (select 1 from tf_mp_members m where m.student_id = s.id)"
    )}
    assert {str(base + i) for i in (2, 3, 4, 7, 8, 10, 11, 12)} <= unassigned


def test_hard_steps_1_to_14():
    rows, base = run_scenario("어려움")
    assert_all_match(rows)
    # 단계 8: 승인 직전 검사에서 거절(같은 주 역할). 단계 14: 대기 지원 거절, 1명 팀(팀4)에서 학생10이 빠짐
    assert application_status(str(base + 6))[0] == "거절"
    assert "승인 직전 검사" in application_status(str(base + 6))[1]
    assert application_status(str(base + 13)) == ("거절", "모집 마감")
    members = member_numbers()
    assert members == {str(base + i) for i in (1, 4, 7, 2, 8, 5, 11, 15)}
