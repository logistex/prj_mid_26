# 2026-10-31 11:13 KST
"""연습 시나리오 실행기의 DB 시험(PRD_step4 8장 S-2~S-4, S-6, S-8, S-9, E-1, E-2, P-1, A-1). 실제 Supabase DB의 tf_mp_ 테이블을 씀

실제 OpenRouter 호출은 하지 않음. 모델을 부르는 경로는 가짜 호출 함수로 대신하고, 모델 호출 없는 경로(앱이 직접 배정)를 씀
"""
import pytest

from conftest import DATA
from mp import ai, practice, practice_run, rules, service
from mp.config import get_secret
from mp.db import make_pool

pytestmark = pytest.mark.skipif(
    not (get_secret("DATABASE_URL") and get_secret("ADMIN_PASSWORD")), reason="DATABASE_URL 또는 ADMIN_PASSWORD 없음"
)

NO_MODEL = practice_run.AiPlan()  # 모델을 부르지 않고 앱이 직접 배정함(진행 안내는 실행마다 새로 만듦)
_cache = {}


@pytest.fixture(scope="module")
def pool():
    p = make_pool(get_secret("DATABASE_URL"), max_size=3)
    service.ensure_admin(p, get_secret("ADMIN_PASSWORD"))
    yield p
    p.close()


def admin_id(pool):
    return service.find_user_id(pool, "admin")


def start(pool, roster_bytes, teams):
    assert service.start_roster(pool, admin_id(pool), roster_bytes, teams).ok


def run_file(pool, name, step_bytes=None, ai_plan=NO_MODEL, only=None):
    """명단과 단계표 파일로 시나리오를 처음부터 끝까지 실행함. [(하위 단계, 기록, 행별 판정)]를 돌려줌"""
    start(pool, (DATA / f"{name}.csv").read_bytes(), {"쉬움": 3, "중간": 4, "어려움": 4}[name])
    rows = practice.parse_steps(step_bytes or (DATA / f"{name}_단계.csv").read_bytes())
    out = []
    for unit in practice.split_units(rows):
        record = practice_run.run_unit(pool, admin_id(pool), [r.to_action() for r in unit.rows], ai_plan)
        verdicts = practice.verdicts(unit.rows, record)
        out.append((unit, record, verdicts))
        if only and unit.label == only:
            break
    return out


def cached_run(pool, name):
    if name not in _cache:
        _cache[name] = run_file(pool, name)
    return _cache[name]


@pytest.fixture(scope="module")
def easy(pool):
    return cached_run(pool, "쉬움")


# ---- E-1: 부록 3개 끝까지 ----

def test_easy_scenario_runs_to_the_end_and_every_compared_row_matches(easy):
    assert [u.label for u, _, _ in easy] == ["1", "2", "3", "4", "5", "6-1", "6-2", "6-3"]
    for unit, record, verdicts in easy:
        assert "denied" not in record and "error" not in record, unit.label
        assert set(verdicts) <= {"일치", "비교 없음", "건너뜀"}, (unit.label, verdicts)


@pytest.mark.parametrize("name", ["중간", "어려움"])
def test_middle_and_hard_scenarios_run_to_the_end_and_every_compared_row_matches(pool, name):
    results = cached_run(pool, name)
    for unit, record, verdicts in results:
        assert "denied" not in record and "error" not in record, (name, unit.label, record)
        assert "불일치" not in verdicts, (name, unit.label, [(r["action"], r["status"], r["message"]) for r in record["rows"]], verdicts)
    # 막힌 지원 뒤의 투표는 건너뜀으로 표시됨(공고 부록: 중간 3단계, 어려움 11단계)
    skipped = {u.label: [r["skipped"] for r in rec["rows"]] for u, rec, _ in results}
    assert skipped["3" if name == "중간" else "11"] == [False, True, True]
    last = results[-1][1]
    assert last["final_checks"] and all(c["ok"] for c in last["final_checks"])
    assert last["after"]["unassigned"] == []


# ---- E-2: 기존 시험과 같음 ----

@pytest.mark.parametrize("name", ["쉬움", "중간", "어려움"])
def test_actual_results_equal_the_existing_scenario_test_expectations(pool, name):
    from test_scenarios import SCENARIOS
    results = cached_run(pool, name)
    actual = [r["status"] for unit, rec, _ in results for r in rec["rows"] if not r["skipped"]
              and r["action"] in ("지원", "투표", "마감")]
    want = []
    for _, actions in SCENARIOS[name]["steps"]:
        for a in actions:
            want.append(a[-1])
    if name == "쉬움":
        want.append("승인")  # 쉬움의 마감은 기존 시험이 마지막 단계 함수에서 따로 함
    assert actual == want


# ---- S-2: 기대 결과는 실행에 쓰이지 않음 ----

def test_corrupting_the_expected_column_changes_verdicts_but_not_actual_results(pool, easy):
    text = (DATA / "쉬움_단계.csv").read_text(encoding="utf-8-sig").splitlines()
    wrong = {"승인": "거절", "대기": "승인", "거절": "막힘", "막힘": "대기", "": ""}
    out = [text[0]]
    for line in text[1:]:
        cells = line.split(",")
        cells[6] = wrong[cells[6]]
        out.append(",".join(cells))
    corrupted = run_file(pool, "쉬움", "\n".join(out).encode("utf-8"))
    statuses = lambda res: [[(r["status"], r["message"], r["skipped"]) for r in rec["rows"]] for _, rec, _ in res]
    assert statuses(corrupted) == statuses(easy)
    assert any("불일치" in v for _, _, v in corrupted)  # 판정만 달라짐


# ---- S-3: 실제 결과가 DB 상태와 맞음 ----

def test_results_match_the_state_changes(easy):
    by = {u.label: rec for u, rec, _ in easy}
    one = by["1"]
    assert [len(t["members"]) for t in one["before"]["teams"]] == [0, 0, 0]
    assert [len(t["members"]) for t in one["after"]["teams"]] == [1, 1, 1]
    assert {c.kind for c in practice.diff_views(one["before"], one["after"])} == {"새 팀원", "팀이 없는 학생 없어짐"}
    four = by["4"]  # 학생7의 지원은 거절됨: 대기 지원이 생겼다가 같은 단계 안에서 없어지므로 전후에 차이가 없음
    assert [r["status"] for r in four["rows"]] == ["대기", "대기", "거절"]
    assert practice.diff_views(four["before"], four["after"]) == []


# ---- S-4: 연습 시나리오가 아닌 경우 ----

ROSTER = (
    "student_no,name,main_role,sub_roles\n"
    "7001,갑(PL),기획자,\n7002,을(PL),기획자,\n7003,병(WP),웹 프로그래머,\n"
    "7004,정(WP),웹 프로그래머,\n7005,무(TT),테스터,\n7006,기(PT),발표자,\n"
)
STEPS = (
    "step,action,actor,team_no,target,choice,expected,note\n"
    "1,지원,7001,2,,,승인,팀이 비어 있으면 바로 승인\n"
    "2,지원,7002,2,,,막힘,같은 주 역할\n"
    "3,지원,7003,2,,,대기,\n"
    "3,투표,7001,,7003,찬성,승인,\n"
    "4,마감,,,,,승인,\n"
    "5,배정,,,,,승인,\n"
    "5,확정,,,,,승인,\n"
)


def test_a_scenario_other_than_the_practice_ones_runs_with_rule_based_results(pool):
    start(pool, ROSTER.encode("utf-8"), 2)
    rows = practice.parse_steps(STEPS.encode("utf-8"))
    assert practice.check_against_roster(rows, {"7001", "7002", "7003", "7004", "7005", "7006"}, 2) == []
    got = []
    for unit in practice.split_units(rows):
        record = practice_run.run_unit(pool, admin_id(pool), [r.to_action() for r in unit.rows], NO_MODEL)
        got.append((unit.label, [(r["action"], r["status"]) for r in record["rows"]]))
    assert got == [
        ("1", [("지원", "승인")]),
        ("2", [("지원", "막힘")]),
        ("3", [("지원", "대기"), ("투표", "승인")]),
        ("4", [("마감", "승인")]),
        ("5-1", [("배정", "승인")]),
        ("5-2", [("확정", "승인")]),
    ]
    view = service.load_view(pool)
    assert view["phase"] == "confirmed" and view["unassigned"] == []
    assert sum(len(t["members"]) for t in view["teams"]) == 6


# ---- S-6: 앞 하위 단계의 이후 상태와 이전 상태가 이어지는지 ----

def test_discontinuity_is_flagged_only_when_the_db_changed_between_units(pool):
    start(pool, (DATA / "쉬움.csv").read_bytes(), 3)
    units = practice.split_units(practice.parse_steps((DATA / "쉬움_단계.csv").read_bytes()))
    run = lambda unit: practice_run.run_unit(pool, admin_id(pool), [r.to_action() for r in unit.rows], NO_MODEL)
    first = run(units[0])
    second = run(units[1])
    assert practice.is_discontinuous(first, second) is False
    third = run(units[2])
    assert practice.is_discontinuous(second, third) is False
    # 다른 곳에서 DB가 바뀜: 학생4가 직접 팀1에 지원
    service.apply_to_team(pool, service.find_user_id(pool, "2026107"), 1)
    fourth = run(units[3])
    assert practice.is_discontinuous(third, fourth) is True


# ---- S-8: 배정 하위 단계 ----

def closed_easy(pool):
    results = run_file(pool, "쉬움", only="6-1")
    assert results[-1][0].label == "6-1" and results[-1][1]["rows"][0]["status"] == "승인"
    return results


def test_assign_unit_without_models_records_before_after_checks_and_source(pool):
    closed_easy(pool)
    record = practice_run.run_unit(pool, admin_id(pool), [practice.Action("배정")], NO_MODEL)
    assert record["rows"][0]["status"] == "승인"
    ai_part = record["ai"]
    assert ai_part["calls_models"] is False and ai_part["source"] == "앱이 직접 배정"
    assert [c["no"] for c in ai_part["checks"]] == [1, 2, 3, 4, 5] and all(c["ok"] for c in ai_part["checks"])
    assert len(record["before"]["unassigned"]) == 2 and record["before"]["phase"] == "closed"
    assert record["after"]["unassigned"] == []
    added = [m for t in record["after"]["teams"] for m in t["members"] if m.get("proposed")]
    assert len(added) == 2
    assert service.load_view(pool)["unassigned"] and len(service.load_view(pool)["unassigned"]) == 2  # DB의 팀은 그대로


def scripted(*outcomes):
    def factory(prep):
        def ask(n, model, tick):
            outcome = outcomes[n - 1]
            pairs = prep.fallback if outcome == ai.SUCCESS else []
            if outcome == ai.CHECK_FAILED:
                pairs = [(prep.unassigned[0]["student_no"], 1)]
            return ai.Attempt(model, outcome, 0.5 * n, "" if outcome == ai.SUCCESS else "가짜 실패", pairs)
        return ask
    return factory


def test_assign_unit_with_a_failing_first_model_records_the_progress_lines(pool):
    closed_easy(pool)
    plan = practice_run.AiPlan(models=("m1:free", "m2:free", "m3:free"), limit=120,
                               ask_factory=scripted(ai.TIMEOUT, ai.SUCCESS, ai.SUCCESS), progress=ai.Progress())
    record = practice_run.run_unit(pool, admin_id(pool), [practice.Action("배정")], plan)
    part = record["ai"]
    assert part["calls_models"] is True
    assert part["source"] == "2차 모델(m2:free)"
    assert part["lines"][0].startswith("1차 모델: 시간 초과")
    assert "2차 모델로 넘어감" in part["lines"][0]
    assert all(c["ok"] for c in part["checks"])


def test_assign_unit_blocked_when_no_assignment_keeps_rules(pool):
    start(pool, ("student_no,name,main_role,sub_roles\n" + "".join(f"8{i}00,기{i},기획자,\n" for i in range(1, 5))).encode(), 2)
    assert practice_run.run_unit(pool, admin_id(pool), [practice.Action("마감")], NO_MODEL)["rows"][0]["status"] == "승인"
    record = practice_run.run_unit(pool, admin_id(pool), [practice.Action("배정")], NO_MODEL)
    assert record["rows"][0]["status"] == "막힘" and "규칙을 지키는 배정이 없음" in record["rows"][0]["message"]
    assert record["ai"]["checks"] == [] and record["ai"]["source"] is None
    assert record["after"] == record["before"]


# ---- S-9: 확정 하위 단계 ----

def test_confirm_unit_shows_before_the_proposal_and_the_final_teams_with_rule_checks(pool):
    closed_easy(pool)
    assign = practice_run.run_unit(pool, admin_id(pool), [practice.Action("배정")], NO_MODEL)
    record = practice_run.run_unit(pool, admin_id(pool), [practice.Action("확정")], NO_MODEL)
    assert record["rows"][0]["status"] == "승인"
    assert len(record["before"]["unassigned"]) == 2 and record["before"]["unassigned"] == assign["before"]["unassigned"]
    assert record["after"]["unassigned"] == [] and record["after"]["phase"] == "confirmed"
    assert [c["no"] for c in record["final_checks"]] == [1, 2, 3, 4] and all(c["ok"] for c in record["final_checks"])


def test_confirm_without_a_proposal_is_blocked(pool):
    closed_easy(pool)
    record = practice_run.run_unit(pool, admin_id(pool), [practice.Action("확정")], NO_MODEL)
    assert record["rows"][0]["status"] == "막힘"
    assert record["after"] == record["before"]


# ---- P-1: 권한 ----

def test_a_student_account_cannot_run_a_unit_and_nothing_changes(pool):
    start(pool, (DATA / "쉬움.csv").read_bytes(), 3)
    student = service.find_user_id(pool, "2026101")
    before = service.load_view(pool)
    for action in (practice.Action("지원", actor="2026101", team_no=1), practice.Action("마감"), practice.Action("배정")):
        record = practice_run.run_unit(pool, student, [action], NO_MODEL)
        assert record.get("denied") == "막힘: 관리자만 할 수 있음" and record["rows"] == []
    assert service.load_view(pool) == before
    unknown = practice_run.run_unit(pool, 10**9, [practice.Action("마감")], NO_MODEL)
    assert unknown.get("denied") == "막힘: 관리자만 할 수 있음"


def test_an_actor_missing_from_the_roster_is_blocked_not_crashed(pool):
    start(pool, (DATA / "쉬움.csv").read_bytes(), 3)
    record = practice_run.run_unit(pool, admin_id(pool), [practice.Action("지원", actor="0000000", team_no=1)], NO_MODEL)
    assert record["rows"][0]["status"] == "막힘" and "명단에 없음" in record["rows"][0]["message"]


# ---- A-1: 오늘 AI 호출 기록 수 ----

def test_count_ai_calls_today_counts_new_log_rows(pool):
    before = service.count_ai_calls_today(pool)
    for n in (1, 2):
        service.log_attempt(pool, n, ai.Attempt("fake/practice-quota:free", ai.TIMEOUT, 1.0, "시험"))
    assert service.count_ai_calls_today(pool) == before + 2
    with pool.connection() as conn:
        conn.execute("delete from tf_mp_ai_logs where model = 'fake/practice-quota:free'")
    assert service.count_ai_calls_today(pool) == before
