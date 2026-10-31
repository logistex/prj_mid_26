# 2026-10-30 21:58 KST
"""팀 편성 앱의 화면(로그인, 명단 올리기, 지원, 투표, 모집 마감, AI 배정과 확정, 팀 목록). 화면 요소의 key는 공고 2.7절의 표를 그대로 따름

로그인한 뒤의 본문은 3초마다 자동으로 다시 그려지는 fragment 1개에 담음(PRD_step2 8장).
단추와 result가 같은 fragment 안에 있어야 단추를 눌렀을 때 result가 함께 갱신됨
AI 배정 영역은 fragment 밖에 둠. 배정을 실행하는 동안에는 자동 갱신을 끄고 진행 안내를 1초마다 갱신함(PRD_step3 6장)
"""
import streamlit as st

from mp import ai, rules, service
from mp.config import ai_config, get_secret
from mp.db import make_pool
from mp.style import CSS

st.set_page_config(page_title="팀 편성", page_icon="👥", layout="centered")

REFRESH_INTERVAL = "3s"  # 공고 2.7절: 다른 사람의 변경을 5초 이하의 간격으로 다시 그림
PHASE_LABEL = {None: "명단이 올라오지 않음", "open": "모집 중", "closed": "모집 마감", "confirmed": "배정 확정"}
# result 안내의 첫 단어(공고 2.7절)별 글자색. 색은 첫 단어에만 입히고 글은 바꾸지 않음
RESULT_COLOR = {"승인": "green", "대기": "blue", "거절": "orange", "막힘": "red"}


def md(text):
    """학생 이름과 안내 글을 마크다운에 넣을 때 서식으로 읽히는 기호를 글자 그대로 보이게 함"""
    return "".join("\\" + c if c in "\\`*_[]<>~$:" else c for c in str(text))


@st.cache_resource
def get_pool():
    return make_pool(get_secret("DATABASE_URL"))


@st.cache_resource
def get_read_pool():
    """읽기 전용 풀(autocommit). 화면을 그릴 때 질의마다 BEGIN과 COMMIT을 따로 보내지 않아 DB 왕복이 줄어듦"""
    return make_pool(get_secret("DATABASE_URL"), max_size=3, autocommit=True)


@st.cache_resource
def init_app():
    pool = get_pool()
    service.ensure_admin(pool, get_secret("ADMIN_PASSWORD"))
    get_read_pool()
    return pool


def set_result(res):
    st.session_state["last_result"] = res.text


def guarded(fn):
    """DB 오류가 나도 접속 정보가 화면에 나오지 않게 오류 종류만 안내함"""

    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            set_result(service.Result("막힘", f"처리하지 못함({type(e).__name__})"))

    return wrapper


missing = [k for k in ("DATABASE_URL", "ADMIN_PASSWORD") if not get_secret(k)]
if missing:
    st.error("설정 값이 없음: " + ", ".join(missing))
    st.stop()
try:
    pool = init_app()
except Exception as e:
    st.error(f"DB를 준비하지 못함({type(e).__name__}). schema.sql을 적용했는지 확인해야 함")
    st.stop()


@guarded
def on_login():
    res, user_id = service.login(
        pool, st.session_state.get("login_student_no"), st.session_state.get("login_password")
    )
    if user_id is not None:
        st.session_state["user_id"] = user_id
        st.session_state["user"] = service.get_user(get_read_pool(), user_id)  # 화면을 그릴 때마다 읽지 않게 세션에 둠
    set_result(res)


def on_logout():
    st.session_state.pop("user_id", None)
    st.session_state.pop("user", None)
    set_result(service.Result("승인", "로그아웃함"))


@guarded
def on_start():
    uploaded = st.session_state.get("admin_roster_file")
    data = uploaded.getvalue() if uploaded is not None else None
    set_result(service.start_roster(
        pool, st.session_state.get("user_id"), data, st.session_state.get("admin_team_count")
    ))


@guarded
def on_close():
    set_result(service.close_recruitment(pool, st.session_state.get("user_id")))


@guarded
def on_apply(team_no):
    set_result(service.apply_to_team(pool, st.session_state.get("user_id"), team_no))


@guarded
def on_vote(applicant_no, choice):
    set_result(service.vote(pool, st.session_state.get("user_id"), applicant_no, choice))


@guarded
def on_assign():
    # 이 실행에서만 배정을 진행함. 이전 결과 안내는 지워 두어, 배정이 끝난 뒤의 result가 이번 결과를 뜻하게 함
    st.session_state["assigning"] = True
    st.session_state["last_result"] = ""


@guarded
def on_confirm():
    set_result(service.confirm_assignment(pool, st.session_state.get("user_id")))


def role_line(person):
    line = f"{person['name']} · {person['main_role']}"
    if person["sub_roles"]:
        line += f" (보조: {', '.join(person['sub_roles'])})"
    return line


def role_line_md(person):
    """role_line과 같은 내용을 위계를 두어 보여 줌: 이름과 주 역할은 굵게, 보조 역할은 보조 글씨"""
    line = f"**{md(person['name'])}** · {md(person['main_role'])}"
    if person["sub_roles"]:
        line += f" :gray[(보조: {md(', '.join(person['sub_roles']))})]"
    return line


def render_result():
    with st.container(key="result"):
        text = st.session_state.get("last_result")
        if not text:
            return
        head = text.split(":", 1)[0].strip()
        if head in RESULT_COLOR:
            # 렌더링된 글은 "승인: …"처럼 첫 단어가 그대로임. 색과 굵기만 입힘
            st.markdown(f":{RESULT_COLOR[head]}[**{head}**]{md(text[len(head):])}")
        else:
            st.markdown(md(text))


def render_team(team, user, my_team_id, my_pending, phase):
    """팀 하나: 팀 이름, 인원, 팀원, 대기 지원. 지원 단추와 (팀원에게만) 투표 단추를 함께 그림"""
    is_member = team["id"] == my_team_id
    with st.container(key=f"team_{team['team_no']}", border=True):
        st.markdown(f"**{md(team['name'])}**{' :blue-badge[내 팀]' if is_member else ''}"
                    f" :gray[· {len(team['members'])}/4]")
        if team["members"]:
            for m in team["members"]:
                st.markdown(role_line_md(m))
        else:
            st.caption("팀원 없음")

        for p in team["pending"]:
            yes = sum(1 for v in p["votes"].values() if v == "찬성")
            st.markdown(f":orange[**대기 지원**] {role_line_md(p)} :gray[(찬성 {yes}/{len(team['members'])})]")
            if is_member:
                if user["id"] in p["votes"]:
                    st.markdown(f"내 투표: **{md(p['votes'][user['id']])}**")
                else:
                    c1, c2 = st.columns(2)
                    c1.button("찬성", key=f"vote_yes_{p['student_no']}", on_click=on_vote,
                              args=(p["student_no"], "찬성"))
                    c2.button("거부", key=f"vote_no_{p['student_no']}", on_click=on_vote,
                              args=(p["student_no"], "거부"))

        # 공고 2.8절: 이미 팀에 속했거나 결과를 기다리는 지원이 있거나 모집이 마감되었으면 지원 단추를 숨김
        if not user["is_admin"] and my_team_id is None and not my_pending and phase == "open":
            st.button(f"{team['name']}에 지원", key=f"apply_{team['team_no']}", on_click=on_apply,
                      args=(team["team_no"],))


def main_view(user_id):
    render_result()
    try:
        user, view = service.load_page(get_read_pool(), user_id)
    except Exception as e:
        st.error(f"DB 오류({type(e).__name__})")
        return
    if user is None:
        st.session_state.pop("user_id", None)
        st.session_state.pop("user", None)
        set_result(service.Result("막힘", "명단이 새로 올라와 계정이 사라짐. 다시 로그인해야 함"))
        st.rerun()

    phase = view["phase"]
    st.markdown(f"상태: **{md(PHASE_LABEL.get(phase, phase))}**")

    my_team_id = next(
        (t["id"] for t in view["teams"] if any(m["id"] == user["id"] for m in t["members"])), None
    )
    my_pending = next(
        ((t, p) for t in view["teams"] for p in t["pending"] if p["id"] == user["id"]), None
    )

    if user["is_admin"]:
        with st.container(border=True):
            st.subheader("명단과 마감")
            st.file_uploader("명단 CSV", type="csv", key="admin_roster_file")
            st.number_input("팀 수", min_value=1, value=3, step=1, key="admin_team_count")
            st.button("명단으로 처음 상태 만들기", key="admin_start", on_click=on_start)
            st.caption("이 단추를 누르면 기존 팀, 지원, 투표, 학생 계정이 모두 지워지고 올린 명단으로 새로 만듦")
            st.divider()
            st.button("모집 마감", key="admin_close", on_click=on_close, type="primary")
        with st.container(border=True):
            st.subheader("팀이 없는 학생")
            with st.container(key="unassigned"):
                if view["unassigned"]:
                    for m in view["unassigned"]:
                        st.text(role_line(m))
                else:
                    st.text("없음")
    else:
        if my_team_id is None:
            st.info("아직 팀이 없음")
        if my_pending:
            st.markdown(f"내 지원: **{md(my_pending[0]['name'])}**에서 대기 중")

    st.subheader("팀 목록")
    if not view["teams"]:
        st.text("아직 명단이 올라오지 않음")
    for team in view["teams"]:
        render_team(team, user, my_team_id, my_pending, phase)


st.title("팀 편성")
st.html(CSS)  # 높이를 차지하지 않는 스타일 요소. fragment 밖에 있어 3초마다 다시 그려지지 않음

# 로그인한 사용자는 세션에 저장해 둔 것을 씀(DB 왕복 0회). 계정이 사라진 경우는 main_view가 3초 안에 알아채 로그아웃함.
# 관리자 기능은 이 값을 믿지 않고 서비스 함수가 DB의 is_admin으로 다시 확인함
user = st.session_state.get("user")
user_id = st.session_state.get("user_id")
if user_id is not None and user is None:
    try:
        user = st.session_state["user"] = service.get_user(get_read_pool(), user_id)
    except Exception as e:
        st.error(f"DB 오류({type(e).__name__})")
        st.stop()
    if user is None:
        st.session_state.pop("user_id", None)
        set_result(service.Result("막힘", "명단이 새로 올라와 계정이 사라짐. 다시 로그인해야 함"))

with st.container(key="whoami"):
    if user is None:
        st.text("로그인하지 않음")
    else:
        st.text(f"{user['name']} ({user['student_no']})" + (" · 관리자" if user["is_admin"] else ""))

if user is None:
    render_result()
    with st.form("login_form"):
        st.text_input("학번", key="login_student_no")
        st.text_input("비밀번호", type="password", key="login_password")
        st.form_submit_button("로그인", key="login_submit", on_click=on_login)
    st.stop()

def render_proposal(view, proposal):
    """검사를 통과한 배정안만 보여 줌: 팀마다 기존 팀원과 새로 배정된 학생(이름, 주 역할, 보조 역할)"""
    if not proposal:
        st.text("배정안 없음")
        return
    st.text(f"출처: {proposal['source']}")
    by_no = {m["student_no"]: m for m in view["unassigned"]}
    added = {}
    for student_no, team_no in proposal["pairs"]:
        added.setdefault(team_no, []).append(by_no[student_no] if student_no in by_no else None)
    for team in view["teams"]:
        st.text(f"{team['name']}")
        for m in team["members"]:
            st.text(f"  {role_line(m)}")
        for m in added.get(team["team_no"], []):
            st.text(f"  + {role_line(m)}" if m else "  + (알 수 없는 학생)")


def run_assignment(user, status_box):
    """AI 배정을 실행함. 끝나면 결과를 저장하고 전체를 다시 그림(자동 갱신을 되살림)"""
    try:
        models, limit, base_url = ai_config()
        prep = service.prepare_assignment(pool, user["id"])
        if prep.result is not None:
            set_result(prep.result)
        elif not get_secret("OPENROUTER_API_KEY"):
            set_result(service.Result("막힘", "OPENROUTER_API_KEY 없음"))
        else:
            api_key = get_secret("OPENROUTER_API_KEY")
            messages = ai.build_messages(prep.teams, prep.unassigned)

            def check(pairs):
                return rules.check_assignment(prep.teams, prep.unassigned, pairs)

            def ask(n, model, tick):
                return ai.ask_model(api_key, model, messages, limit, base_url, check, tick)

            progress = ai.Progress(on_change=lambda p: status_box.text(p.text()))
            set_result(service.generate_proposal(pool, prep, ask, models, limit, progress))
    except Exception as e:
        set_result(service.Result("막힘", f"처리하지 못함({type(e).__name__})"))
    st.rerun()


def admin_assign_area(user, assigning):
    data = service.load_admin_page(get_read_pool())  # 질의 1개로 읽음
    with st.container(border=True):
        st.subheader("AI 배정과 확정")
        st.button("AI 배정", key="admin_assign", on_click=on_assign, disabled=assigning, type="primary")
        with st.container(key="assign_status"):
            status_box = st.empty()
            status_box.text("배정을 시작함" if assigning else data["assign_status"])
        st.markdown("**배정안**")
        with st.container(key="proposal"):
            render_proposal(data["view"], data["proposal"])
        # 배정안이 없을 때와 AI 배정이 도는 동안에는 누르지 못하게 함: 채점 프로그램은 눌러지는 확정 단추를 배정안이 왔다는 신호로 씀
        st.button("배정안 확정", key="admin_confirm", on_click=on_confirm, type="primary",
                  disabled=assigning or not data["proposal"])
        with st.expander("최근 AI 호출 기록 10건"):
            if not data["logs"]:
                st.text("기록 없음")
            for row in data["logs"]:
                st.text(f"{row['at']} · {row['attempt_no']}차 · {row['model']} · {row['outcome']} · {row['seconds']}초"
                        + (f" · {row['detail']}" if row["detail"] else ""))
        if assigning:
            run_assignment(user, status_box)


assigning = bool(st.session_state.pop("assigning", False))  # 중간에 끊겨도 다음 실행에서 배정이 다시 시작되지 않게 바로 지움
st.button("로그아웃", key="logout", on_click=on_logout)
st.fragment(run_every=None if assigning else REFRESH_INTERVAL)(main_view)(user["id"])
if user["is_admin"]:
    admin_assign_area(user, assigning)
