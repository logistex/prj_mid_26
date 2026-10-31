# 2026-10-31 11:16 KST
"""연습 시나리오의 하위 단계 1개를 실제 서비스 함수로 실행함(PRD_step4 3장)

화면의 단추가 부르는 함수(service.apply_to_team 등)를 그대로 부르고, 서비스가 돌려준 결과를 가공하지 않고 기록함.
이 모듈은 기대 결과를 받지 않음: 실행 함수의 입력은 Action(동작, 학번, 팀 번호 등)뿐임(중간과제 공고 6.3절 감점 19번)
"""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from . import ai, practice, rules, service


@dataclass
class AiPlan:
    """배정 동작에서 모델을 부를지. models가 비어 있으면 모델을 부르지 않고 앱이 직접 배정함

    ask_factory(prep)는 ai.propose가 부르는 ask(번호, 모델, tick)를 돌려줌. progress는 진행 안내를 모으는 ai.Progress(없으면 새로 만듦)
    """
    models: tuple = ()
    limit: float = 0
    ask_factory: object = None
    progress: object = None


def _now():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")


def run_unit(pool, admin_id, actions, ai_plan=None):
    """하위 단계 1개의 동작들을 순서대로 실행하고 기록 1개를 돌려줌. 관리자가 아니면 아무것도 실행하지 않음

    기록: started_at, kind, rows(동작별 status, message, skipped), before(실행 직전 상태), after_db(실행 직후 DB 상태),
    after(보여 줄 이후 상태. 배정은 배정안을 얹은 상태), 배정이면 ai, 확정이면 final_checks, 오류가 나면 error
    """
    ai_plan = ai_plan or AiPlan()
    me = service.get_user(pool, admin_id)
    if me is None or not me["is_admin"]:
        return {"denied": "막힘: 관리자만 할 수 있음", "rows": [], "started_at": _now()}
    first = actions[0].action if actions else ""
    record = {"started_at": _now(), "kind": first if first in practice.ADMIN_ACTIONS else "지원과 투표", "rows": []}
    before = service.load_view(pool)
    tracker = practice.SkipTracker()
    for action in actions:
        row = {"action": action.action, "actor": action.actor, "status": "", "message": "", "skipped": False}
        record["rows"].append(row)
        if tracker.should_skip(action):
            row.update(skipped=True, status="건너뜀", message="앞의 지원이 막혀 건너뜀")
            continue
        try:
            result = _run_action(pool, admin_id, action, ai_plan, record)
        except Exception as e:  # 접속 정보가 섞일 수 있어 오류 종류만 남김
            row.update(status="오류", message=type(e).__name__)
            record["error"] = type(e).__name__
            break
        row.update(status=result.status, message=result.message)
        tracker.note_result(action, result.status)

    try:
        after_db = service.load_view(pool)
    except Exception as e:
        record.setdefault("error", type(e).__name__)
        after_db = before
    after = after_db
    part = record.get("ai")
    if part and part["pairs"]:
        after = practice.apply_proposal(after_db, [tuple(p) for p in part["pairs"]])
    if record["kind"] == "확정" and record["rows"] and record["rows"][0]["status"] == "승인":
        teams = [{"team_no": t["team_no"], "members": t["members"]} for t in after_db["teams"]]
        record["final_checks"] = rules.final_state_checks(teams, after_db["unassigned"])
    record.update(before=before, after_db=after_db, after=after)
    return record


def _run_action(pool, admin_id, action, plan, record):
    name = action.action
    if name == "지원":
        uid = service.find_user_id(pool, action.actor)
        if uid is None:
            return service.Result("막힘", "학번이 명단에 없음")
        return service.apply_to_team(pool, uid, action.team_no)
    if name == "투표":
        uid = service.find_user_id(pool, action.actor)
        if uid is None:
            return service.Result("막힘", "학번이 명단에 없음")
        return service.vote(pool, uid, action.target, action.choice)
    if name == "마감":
        return service.close_recruitment(pool, admin_id)
    if name == "확정":
        return service.confirm_assignment(pool, admin_id)
    if name == "배정":
        return _assign(pool, admin_id, plan, record)
    return service.Result("막힘", "알 수 없는 동작")


def _assign(pool, admin_id, plan, record):
    models = tuple(plan.models) if plan.ask_factory else ()
    part = {"calls_models": bool(models), "source": None, "pairs": [], "checks": [], "lines": []}
    record["ai"] = part
    prep = service.prepare_assignment(pool, admin_id)
    if prep.result is not None:  # 사전 검사에서 막힘: 규칙을 지키는 배정이 없음 등
        return prep.result
    progress = plan.progress or ai.Progress()
    ask = plan.ask_factory(prep) if models else None
    result = service.generate_proposal(pool, prep, ask, models, plan.limit, progress)
    part["lines"] = list(progress.lines)
    proposal = service.load_proposal(pool) if result.ok else None  # 실패한 실행이 앞의 배정안을 읽지 않게 함
    if proposal:
        part["source"] = proposal["source"]
        part["pairs"] = [list(p) for p in proposal["pairs"]]
        part["checks"] = rules.assignment_checks(prep.teams, prep.unassigned, [tuple(p) for p in proposal["pairs"]])
    return result
