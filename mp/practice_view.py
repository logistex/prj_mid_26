# 2026-10-31 13:07 KST
"""연습 시나리오 실행 화면(PRD_step4). 기본 화면의 "시나리오 실행" 탭에 그려짐(관리자만). 관리자가 명단 CSV와 단계표 CSV를 올리면
단계표의 동작을 지금 있는 서비스 함수로 1개씩 실행하고, 그 단계에서 지원, 투표, 배정이 어떻게 바뀌었는지 보여 줌.
좌측은 단계를 시간 순서로 늘어놓은 줄(번호, 한 줄 요약, 결과 배지), 우측은 고른 단계의 상황: 일어난 일 한 문장, 기대와 실제 결과,
이전과 이후를 한 판에 겹쳐 바뀐 것만 표시한 팀 카드(mp/practice_board.py)

공고 2.7절의 key를 쓰는 "팀 편성" 탭과 섞이지 않게, 이 화면의 key는 모두 practice_로 시작함.
저장한 기록은 세션 상태에만 둠(PRD_step4 3.7절). 이 화면에는 어떤 시나리오의 학번, 이름, 단계 번호도 쓰지 않음
"""
from html import escape

import streamlit as st

from mp import ai, practice, practice_board, practice_run, rules, service
from mp.config import ai_config, get_secret
from mp.practice import md_escape as md
from mp.style import PRACTICE_CSS

S = st.session_state
VERDICT_COLOR = {"일치": "green", "불일치": "red", "비교 없음": "gray", "건너뜀": "gray"}
VERDICT_MARK = {"일치": "○", "불일치": "✕", "비교 없음": "–", "건너뜀": "–"}
# 결과는 눌러 보이는 것이 아니라 상황을 알리는 글이므로 테두리, 바탕, 그림자 없이 기호와 색 글자만 씀
STATUS_MARK = {"승인": ("○", "pv-yes"), "거절": ("✕", "pv-no"), "대기": ("…", "pv-wait"), "막힘": ("–", "pv-none"),
               "건너뜀": ("–", "pv-none"), "오류": ("!", "pv-no")}
WARNING = ("채점하는 동안에는 이 탭을 쓰지 마십시오(채점 프로그램을 돌릴 때와 손으로 조작할 때 모두). "
           "\"시나리오 시작\"은 기존 팀, 지원, 투표를 모두 지웁니다.")
STATE_KEYS = ("practice_units", "practice_records", "practice_selected", "practice_pending", "practice_running",
              "practice_errors", "practice_names", "practice_title", "practice_confirm", "practice_finish_modal",
              "practice_ai_effective")
_pool = None  # render가 받은 연결 풀. 기본 화면이 만든 풀을 함께 씀(프로세스 안에서 하나뿐이므로 세션이 달라도 같음)


def clear():
    """로그아웃할 때 이 화면의 저장한 기록을 지움"""
    for key in STATE_KEYS:
        S.pop(key, None)


# ---- 단추를 눌렀을 때 ----

def uploaded(key):
    f = S.get(key)
    return None if f is None else f.getvalue()


def on_start():
    S.pop("practice_errors", None)
    check = practice.prep_check(uploaded("practice_roster_file"), uploaded("practice_steps_file"), S.get("practice_team_count"))
    if not check.ready:
        S["practice_errors"] = list(check.errors) or ["명단 CSV와 단계표 CSV를 모두 올려야 함"]
        return
    team_count = int(S.get("practice_team_count") or 1)
    roster_file, steps_file = S["practice_roster_file"], S["practice_steps_file"]
    try:
        res = service.start_roster(_pool, S["user_id"], roster_file.getvalue(), team_count)
    except Exception as e:
        S["practice_errors"] = [f"처리하지 못함({type(e).__name__})"]
        return
    if not res.ok:
        S["practice_errors"] = [res.text]
        return
    for key in ("practice_pending", "practice_running", "practice_selected", "practice_confirm", "practice_finish_modal"):
        S.pop(key, None)
    S["practice_units"] = practice.split_units(list(check.rows))
    S["practice_records"] = {}
    S["practice_names"] = {s["student_no"]: practice.short_name(s["name"]) for s in check.students}
    S["practice_title"] = practice.scenario_title(getattr(steps_file, "name", ""))


def on_step(label):
    S["practice_selected"] = label


def on_run(label):
    """실행 단추. 모델을 부르지 않고 배정하려는 경우에는 바로 실행하지 않고 확인 창을 먼저 띄움"""
    unit = next((u for u in S.get("practice_units", ()) if u.label == label), None)
    if unit is not None and unit.kind == "배정" and not S.get("practice_ai_effective"):
        S["practice_confirm"] = label
    else:
        S["practice_pending"] = label


# ---- 화면 조각 ----

def role_line(person):
    line = f"**{md(person['name'])}** · {md(person['main_role'])}"
    if person["sub_roles"]:
        line += f" :gray[(보조: {md(', '.join(person['sub_roles']))})]"
    return line


def render_view(view, changes, side):
    """팀 카드와 팀이 없는 학생 목록. 바뀐 곳은 기호(+, −)와 색으로 구별함"""
    new = {(c.team_no, c.student_no) for c in changes if c.kind == "새 팀원"}
    gone = {(c.team_no, c.student_no) for c in changes if c.kind == "빠진 팀원"}
    pend_new = {(c.team_no, c.student_no) for c in changes if c.kind == "대기 지원 생김"}
    pend_gone = {(c.team_no, c.student_no) for c in changes if c.kind == "대기 지원 없어짐"}
    un_new = {c.student_no for c in changes if c.kind == "팀이 없는 학생 생김"}
    un_gone = {c.student_no for c in changes if c.kind == "팀이 없는 학생 없어짐"}
    plus, minus = ":green[**+**] ", ":red[**−**] "
    for team in view["teams"]:
        no, n = team["team_no"], len(team["members"])
        with st.container(border=True):
            st.markdown(f"**{md(team['name'])}** :gray[· {n}/4]")
            for m in team["members"]:
                mark = plus if side == "after" and (no, m["student_no"]) in new else \
                    minus if side == "before" and (no, m["student_no"]) in gone else ""
                st.markdown(mark + role_line(m))
            if not team["members"]:
                st.caption("팀원 없음")
            for p in team["pending"]:
                mark = plus if side == "after" and (no, p["student_no"]) in pend_new else \
                    minus if side == "before" and (no, p["student_no"]) in pend_gone else ""
                yes = sum(1 for v in p.get("votes", {}).values() if v == "찬성")
                st.markdown(f"{mark}:orange[**대기 지원**] {role_line(p)} :gray[(찬성 {yes}/{n})]")
    with st.container(border=True):
        st.markdown(f"**팀이 없는 학생** :gray[· {len(view['unassigned'])}명]")
        for u in view["unassigned"]:
            mark = plus if side == "after" and u["student_no"] in un_new else \
                minus if side == "before" and u["student_no"] in un_gone else ""
            st.markdown(mark + role_line(u))
        if not view["unassigned"]:
            st.caption("없음")


def cell(text):
    return md(text).replace("|", "\\|")


def checks_table(first_column, checks):
    """규칙 확인과 배정안 검사의 표. 결과는 기호와 글자(○ 통과, ✕ 위반)를 함께 씀(팀 카드의 투표 표시와 같은 기호)"""
    lines = [f"| {first_column} | 결과 | 위반 내용 |", "|---|---|---|"]
    for c in checks:
        result = ":green[**○ 통과**]" if c["ok"] else ":red[**✕ 위반**]"
        lines.append(f"| {cell(c['title'])} | {result} | {'' if c['ok'] else cell(c['detail'])} |")
    return "\n".join(lines)


def verdict_text(verdict):
    return f":{VERDICT_COLOR[verdict]}[**{VERDICT_MARK[verdict]} {verdict}**]"


def collect_names(records):
    """이름 목록. 올린 명단의 이름을 먼저 쓰고, 없으면 기록 속 상태에서 읽음"""
    names = {}
    for rec in records.values():
        for view in (rec.get("before"), rec.get("after")):
            if not view:
                continue
            for team in view["teams"]:
                for person in [*team["members"], *team["pending"]]:
                    names[person["student_no"]] = practice.short_name(person["name"])
            for person in view["unassigned"]:
                names[person["student_no"]] = practice.short_name(person["name"])
    names.update(S.get("practice_names", {}))
    return names


def result_html(text):
    mark, cls = STATUS_MARK.get(text, ("–", "pv-none"))
    return f'<span class="pv-result {cls}">{mark} {escape(text)}</span>'


def step_summary(unit, name_of):
    """시간 줄 한 칸의 글: 단계표의 "하는 일" 문장을 그대로 씀. 열이 없는 단계표는 행으로 만든 한 줄 요약을 씀.
    한 단계가 여러 하위 단계로 나뉘어 같은 문장이 되풀이되면 이 칸이 어느 일인지 덧붙임"""
    own = practice.summarize_unit(unit, name_of)
    if not unit.plan:
        return own
    return f"{unit.plan} · {own}" if unit.step_units > 1 else unit.plan


def render_step_row(unit, state, record, selected, busy, name_of):
    """시간 줄의 한 칸. 실행했고 지금 오른쪽에 보이지 않는 단계는 칸 전체가 단추이고(눌러서 보기),
    지금 보이는 단계, 아직 실행하지 않은 단계는 눌러지지 않는 글임"""
    summary = step_summary(unit, name_of)
    if state == "실행함" and not selected:
        with st.container(key=f"practice_row_go_{unit.key}"):
            st.button(f"**{unit.label}** {md(summary)}", key=f"practice_step_{unit.key}", on_click=on_step,
                      args=(unit.label,), disabled=busy, width="stretch", wrap=True, help="이 단계 보기")
            st.html(result_html(practice.unit_result(unit, record)))
        return
    if state == "실행함":
        mode, mark, result = "sel", "▶", result_html(practice.unit_result(unit, record))
    elif state == "다음 차례":
        mode, mark, result = "next", "", '<span class="pv-result pv-next">다음 차례</span>'
    elif state == "중단됨":
        mode, mark, result = "stop", "", '<span class="pv-result pv-no">✕ 중단됨</span>'
    else:
        mode, mark, result = "wait", "", '<span class="pv-result pv-none">실행 전</span>'
    with st.container(key=f"practice_row_{mode}_{unit.key}"):
        st.html(f'<div class="pv-card"><span class="pv-mark">{mark}</span><span class="pv-text"><b>{escape(unit.label)}</b> '
                f'{escape(summary)}</span>{result}</div>')


def render_story(unit, record, previous, name_of):
    """"▶ N단계의 상황" 바로 아래 세 줄: 시나리오(하는 일), 기대(기대 결과), 실제(일치 여부와 앱이 한 일)"""
    verdict = practice.judge_unit(practice.verdicts(unit.rows, record))
    plan = unit.plan or practice.summarize_unit(unit, name_of)
    expect = unit.expect_text or ", ".join(r.expected for r in unit.rows if r.expected) or "없음"
    with st.container(key="practice_verdict"):
        st.markdown(f"**시나리오:** {md(plan)}")
        st.markdown(f"**기대:** {md(expect)}")
        st.markdown(f"**실제:** {verdict_text(verdict)} · {md(practice.narrate(unit, record, name_of))}")
    if record.get("error"):
        st.error(f"실행 중 오류({record['error']}). 이 하위 단계부터 다시 시작해야 함")
    if previous is not None and practice.is_discontinuous(previous, record):
        st.warning("이전 상태가 앞 단계의 이후 상태와 다름: 다른 곳에서 DB가 바뀌었을 수 있음")


def render_record(unit, record):
    part = record.get("ai")
    if part is not None:
        with st.container(key="practice_checks"):
            text = md(practice.ai_source_text(part))
            st.markdown("**배정안의 출처** " + (f":red[{text}]" if part.get("called") else f":gray[{text}]"))
            if part["checks"]:
                st.markdown("**배정안 검사 5가지**")
                st.markdown(checks_table("검사", part["checks"]))
            if part["lines"]:
                st.markdown("**진행 안내(실패한 모델의 기록)**")
                for line in part["lines"]:
                    st.text(line)
    if record.get("final_checks"):
        with st.container(key="practice_checks"):
            st.markdown("**규칙 확인**")
            st.markdown(checks_table("규칙", record["final_checks"]))
    changes = practice.diff_views(record["before"], record["after"])
    st.toggle("이전 상태도 나란히 보기", key="practice_show_before")
    with st.container(key="practice_board"):
        st.html(practice_board.board_html(practice_board.build_board(record["before"], record["after"], unit.rows, record["rows"])))
    if S.get("practice_show_before"):
        c_before, c_after = st.columns(2)
        with c_before:
            st.markdown("**이전**" + (" (마감 뒤)" if unit.kind == "배정" else ""))
            with st.container(key="practice_before"):
                render_view(record["before"], changes, "before")
        with c_after:
            st.markdown("**이후**" + (" (배정안)" if unit.kind == "배정" else " (확정한 최종 팀)" if unit.kind == "확정" else ""))
            with st.container(key="practice_after"):
                render_view(record["after"], changes, "after")
    with st.expander("바뀐 것 목록"):
        with st.container(key="practice_summary"):
            if not changes:
                st.caption("바뀐 것 없음")
            for c in changes:
                where = f"팀{c.team_no}" if c.team_no else "-"
                detail = f" · {md(c.detail)}" if c.detail else ""
                who = f" · {md(c.name)}" if c.name else ""
                st.markdown(f"- {c.kind} · {where}{who}{detail}")
    verdicts = practice.verdicts(unit.rows, record)
    with st.expander("행별 결과"):
        for row, rr, v in zip(unit.rows, record["rows"], verdicts):
            who = f" {md(row.actor)}" if row.actor else ""
            st.markdown(f"{row.action}{who}: **{md(rr['status'])}** {md(rr['message'])} · 기대 {row.expected or '없음'} · "
                        f"{verdict_text(v)}")


def ask_factory(api_key, limit, base_url):
    """기본 화면의 AI 배정과 같은 방식으로 모델을 부르는 함수를 만듦"""
    def factory(prep):
        messages = ai.build_messages(prep.teams, prep.unassigned)

        def check(pairs):
            return rules.check_assignment(prep.teams, prep.unassigned, pairs)

        def ask(n, model, tick):
            return ai.ask_model(api_key, model, messages, limit, base_url, check, tick)

        return ask

    return factory


def ai_box():
    """배정 하위 단계의 행 안: 실제 모델을 부르는지 켜고 끄는 토글과 오늘 호출 횟수"""
    try:
        used = service.count_ai_calls_today(_pool)
    except Exception:
        used = None
    q = practice.quota(used) if used is not None else None
    blocked = q is None or q.blocked
    with st.container(border=True):
        st.toggle("실제 AI 모델 호출", key="practice_ai_on", value=True, disabled=blocked)
        on = bool(S.get("practice_ai_on")) and not blocked
        S["practice_ai_effective"] = on  # 실행 단추와 build_plan이 읽음(토글이 그려지지 않는 실행에서도 남음)
        if on:
            st.markdown(f":red[**실제 모델을 부름.**] 무료 모델을 1차부터 최대 {practice.CALLS_PER_RUN}회 부름(실패해도 횟수에 들어감)")
        else:
            st.markdown(":gray[모델을 부르지 않음. 앱이 직접 배정함(호출 0회)]")
        if used is None:
            st.caption("오늘 호출 횟수를 읽지 못해 모델 호출을 켤 수 없음")
        else:
            st.caption(f"오늘 이 앱이 기록한 호출 {used}회 / 하루 {practice.DAILY_LIMIT}회(이 앱 밖의 호출은 모름)")
            if q.blocked:
                st.markdown(f":red[오늘 한도({practice.DAILY_LIMIT}회)를 넘기므로 켤 수 없음]")
            elif q.warn:
                st.markdown(f":orange[이 실행 뒤 남는 횟수가 {q.remaining_after}회임. 채점 기간(11/3~11/4)에는 "
                            f"하루 {practice.RESERVE}회 이상을 남겨야 하므로 오늘이 채점 기간이면 켜지 마십시오]")
    return on


def build_plan(unit, status_box):
    """배정 하위 단계의 AiPlan. 토글이 꺼져 있으면 모델 없이 앱이 직접 배정함. 모델을 부를 수 없으면 None"""
    if unit.kind != "배정":
        return practice_run.AiPlan()
    progress = ai.Progress(on_change=lambda p: status_box.text(p.text()))
    if not S.get("practice_ai_effective"):
        return practice_run.AiPlan(progress=progress)
    api_key = get_secret("OPENROUTER_API_KEY")
    if not api_key:
        return None
    used = service.count_ai_calls_today(_pool)
    if practice.quota(used).blocked:
        return None
    models, limit, base_url = ai_config()
    return practice_run.AiPlan(tuple(models), limit, ask_factory(api_key, limit, base_url), progress)


def run_pending(unit, records):
    S.pop("practice_pending", None)
    st.subheader(f"{unit.label}단계를 실행하는 중")
    status_box = st.empty()
    plan = build_plan(unit, status_box)
    if plan is None:
        st.error("실제 모델을 부를 수 없음(OPENROUTER_API_KEY 없음 또는 오늘 한도를 넘김). 토글을 끄고 다시 누르십시오")
        return
    S["practice_running"] = unit.label
    record = practice_run.run_unit(_pool, S["user_id"], [r.to_action() for r in unit.rows], plan)
    S.pop("practice_running", None)
    records[unit.label] = record
    S["practice_records"] = records
    S["practice_selected"] = unit.label
    states = practice.unit_states(S["practice_units"], records)
    if all(x == "실행함" for x in states):
        S["practice_finish_modal"] = True  # 마지막 단계를 실행한 직후에 한 번만 끝 안내 창을 띄움
    st.rerun()


def sync_team_count():
    """단계표를 새로 올리면 팀 수를 단계표가 쓰는 가장 큰 팀 번호로 맞춤. 이미 맞춘 파일이면 사람이 바꾼 값을 그대로 둠"""
    steps_file = S.get("practice_steps_file")
    if steps_file is None:
        S.pop("practice_auto_team", None)
        S.pop("practice_steps_seen", None)
        return
    sig = getattr(steps_file, "file_id", None) or (steps_file.name, steps_file.size)
    if S.get("practice_steps_seen") == sig:
        return
    S["practice_steps_seen"] = sig
    check = practice.prep_check(None, steps_file.getvalue(), 1)  # 팀 수는 쓰지 않고 단계표가 쓰는 팀 번호만 읽음
    if check.max_team is None:
        S.pop("practice_auto_team", None)
        return
    S["practice_team_count"] = check.max_team
    S["practice_auto_team"] = (check.max_team, f"단계표가 {practice.team_range_text(check.min_team, check.max_team)}를 쓰므로 "
                               f"팀 수를 {check.max_team}로 맞춤")


def prep_form():
    S.setdefault("practice_team_count", 3)
    st.file_uploader("명단 CSV", type="csv", key="practice_roster_file")
    st.file_uploader("단계표 CSV", type="csv", key="practice_steps_file")
    sync_team_count()
    st.number_input("팀 수", min_value=1, step=1, key="practice_team_count")
    check = practice.prep_check(uploaded("practice_roster_file"), uploaded("practice_steps_file"), S.get("practice_team_count"))
    auto = S.get("practice_auto_team")
    with st.container(key="practice_prep_notes"):
        if auto and auto[0] == int(S.get("practice_team_count") or 0):
            st.info(auto[1])
        if check.warning:
            st.warning(check.warning)
        for message in check.errors:
            st.markdown(f":red[**✕**] :red[{md(message)}]")
        if not check.errors and (uploaded("practice_roster_file") is None or uploaded("practice_steps_file") is None):
            st.caption("명단 CSV와 단계표 CSV를 모두 올려야 시작할 수 있음")
    st.checkbox("기존 팀, 지원, 투표가 모두 지워짐에 동의함", key="practice_agree")
    st.button("시나리오 시작", key="practice_start", on_click=on_start, disabled=not (S.get("practice_agree") and check.ready))
    for message in S.get("practice_errors", []):
        if message not in check.errors:
            st.markdown(f":red[{md(message)}]")


def render(pool, user):
    """"시나리오 실행" 탭의 내용. 관리자만 부름(이 탭이 열려 있을 때만 실행됨)"""
    global _pool
    _pool = pool
    if not user["is_admin"]:  # 기본 화면이 관리자에게만 이 탭을 그리지만, 여기서도 다시 막음
        st.error("관리자만 쓸 수 있음")
        return
    st.html(PRACTICE_CSS)
    st.warning(WARNING)
    units = S.get("practice_units")
    if not units:
        st.info("시작한 시나리오가 없음(저장한 기록이 없음). 아래에서 명단 CSV와 단계표 CSV를 올려 시작해야 함")
        prep_form()
        return

    with st.expander("준비(다시 시작)"):
        prep_form()

    records = S.get("practice_records", {})
    states = practice.unit_states(units, records, S.get("practice_running"))
    by_label = {u.label: (u, st_) for u, st_ in zip(units, states)}
    next_unit = next((u for u, st_ in zip(units, states) if st_ == "다음 차례"), None)
    pending = S.get("practice_pending")
    if pending is not None and not (next_unit is not None and pending == next_unit.label):
        S.pop("practice_pending", None)  # 이미 실행했거나 실행할 수 없는 요청은 버림
        pending = None
    busy = pending is not None
    done = [u for u, st_ in zip(units, states) if st_ == "실행함"]
    selected = S.get("practice_selected")
    if selected not in {u.label for u in done}:
        selected = done[-1].label if done else None
    names = collect_names(records)

    def name_of(no):
        return names.get(no, no)

    left, right = st.columns([3, 7])
    with left:
        st.subheader(S.get("practice_title") or "시나리오")
        st.caption(practice.progress_text(practice.progress(units, states)))
        for unit, state in zip(units, states):
            render_step_row(unit, state, records.get(unit.label), unit.label == selected, busy, name_of)

    with right:
        render_right(units, done, selected, next_unit, pending, busy, records, by_label, name_of)


def finish_line(fin):
    """완료 안내 한 줄. 기대와 다른 하위 단계, 규칙 위반이 있으면 그 수를 빨갛게 씀"""
    parts = [":green[**○ 시나리오 끝**]", f"{fin.steps}단계를 모두 실행함", f"기대와 일치 {fin.matched}/{fin.compared}"]
    if fin.mismatched:
        parts.append(f":red[**불일치 {len(fin.mismatched)}**]")
    if fin.has_confirm:
        bad = sum(1 for c in fin.checks if not c["ok"])
        if not fin.checks:
            parts.append(":red[**확정하지 못함**]")
        elif bad:
            parts.append(f"확정한 팀이 :red[**규칙 위반 {bad}**]")
        else:
            parts.append("확정한 팀이 규칙을 모두 지킴")
    return " · ".join(parts)


@st.dialog("시나리오가 끝났습니다", width="large")
def finish_dialog(fin):
    st.markdown(f"실행한 단계: **{fin.steps}단계**(하위 단계 {fin.units}개)")
    if fin.mismatched:
        st.markdown(f"기대와 일치한 하위 단계: **{fin.matched}/{fin.compared}** · :red[**✕ 기대와 다른 번호: "
                    f"{md(', '.join(fin.mismatched))}**]")
    else:
        st.markdown(f"기대와 일치한 하위 단계: **{fin.matched}/{fin.compared}** · :green[**○ 모두 일치**]")
    if fin.checks:
        st.markdown("**규칙 확인**")
        st.markdown(checks_table("규칙", fin.checks))
        st.markdown("**확정한 팀**")
        for name, members in fin.teams:
            st.markdown(f"- {md(name)}: {md(', '.join(members)) if members else ':gray[팀원 없음]'}")
    elif fin.has_confirm:
        st.markdown(":red[**확정하지 못함**: 확정한 팀이 없음]")
    else:
        st.markdown(":gray[단계표에 확정 단계가 없음]")
    if st.button("닫기", key="practice_finish_close", type="primary"):
        st.rerun()


@st.dialog("실제 AI 모델 호출이 꺼져 있습니다")
def confirm_dialog(label):
    st.markdown("실제 AI 모델 호출이 꺼져 있습니다. 이대로 실행하면 AI를 부르지 않고 앱이 규칙에 맞는 배정을 직접 찾습니다.")
    go, cancel = st.columns(2)
    with go:
        if st.button("앱이 직접 배정으로 실행", key="practice_confirm_go", type="primary", width="stretch"):
            S["practice_pending"] = label
            st.rerun()
    with cancel:
        if st.button("취소", key="practice_confirm_cancel", width="stretch"):
            st.rerun()


def render_right(units, done, selected, next_unit, pending, busy, records, by_label, name_of):
    ai_on = False
    if next_unit is not None and next_unit.kind == "배정" and pending is None:
        ai_on = ai_box()
    finished = next_unit is None and bool(units) and len(done) == len(units)
    head, run = st.columns([2, 3] if finished else [3, 2])
    with head:
        st.subheader(f"▶ {selected}단계의 상황" if selected else "시작할 때의 상황")
    with run:
        if finished:
            with st.container(key="practice_finish"):
                st.markdown(finish_line(practice.finish_summary(units, records)))
        elif next_unit is not None:
            st.button(f"{next_unit.label}단계 실행", key="practice_run_next", on_click=on_run, args=(next_unit.label,),
                      disabled=busy, type="primary", width="stretch", wrap=True)
    if selected is not None and pending is None:
        unit = by_label[selected][0]
        position = units.index(unit)
        render_story(unit, records[selected], records.get(units[position - 1].label) if position > 0 else None, name_of)
    if done:
        index = [u.label for u in done].index(selected)
        prev_col, next_col, _ = st.columns([1, 1, 2])
        with prev_col:
            st.button("‹ 이전 단계 보기", key="practice_prev", on_click=on_step, args=(done[index - 1].label,) if index > 0 else (None,),
                      disabled=busy or index == 0, width="stretch")
        with next_col:
            last = index == len(done) - 1
            st.button("다음 단계 보기 ›", key="practice_next", on_click=on_step, args=(done[index + 1].label,) if not last else (None,),
                      disabled=busy or last, width="stretch")

    if pending is not None:
        run_pending(by_label[pending][0], records)
        return
    confirm = S.pop("practice_confirm", None)
    if confirm is not None and next_unit is not None and confirm == next_unit.label:
        confirm_dialog(confirm)
    if S.pop("practice_finish_modal", False) and finished:
        finish_dialog(practice.finish_summary(units, records))
    if selected is None:
        if next_unit is None:
            st.info("실행할 단계가 없음")
        else:
            st.info(f"아직 실행한 단계가 없음. 오른쪽 위의 {next_unit.label}단계 실행을 누르십시오")
        try:
            with st.container(key="practice_after"):
                st.html(practice_board.board_html(practice_board.state_board(service.load_view(_pool))))
        except Exception as e:
            st.caption(f"지금 상태를 읽지 못함({type(e).__name__})")
        return
    render_record(by_label[selected][0], records[selected])
