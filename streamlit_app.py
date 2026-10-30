# 2026-10-30 21:58 KST
"""팀 편성 앱의 화면(로그인, 명단 올리기, 지원, 투표, 모집 마감, 팀 목록). 화면 요소의 key는 공고 2.7절의 표를 그대로 따름

로그인한 뒤의 본문 전체는 3초마다 자동으로 다시 그려지는 fragment 1개에 담음(PRD_step2 8장).
단추와 result가 같은 fragment 안에 있어야 단추를 눌렀을 때 result가 함께 갱신됨
"""
import streamlit as st

from mp import service
from mp.config import get_secret
from mp.db import make_pool

st.set_page_config(page_title="팀 편성", layout="centered")

REFRESH_INTERVAL = "3s"  # 공고 2.7절: 다른 사람의 변경을 5초 이하의 간격으로 다시 그림
PHASE_LABEL = {None: "명단이 올라오지 않음", "open": "모집 중", "closed": "모집 마감", "confirmed": "배정 확정"}


@st.cache_resource
def get_pool():
    return make_pool(get_secret("DATABASE_URL"))


@st.cache_resource
def init_app():
    pool = get_pool()
    service.ensure_admin(pool, get_secret("ADMIN_PASSWORD"))
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
    set_result(res)


def on_logout():
    st.session_state.pop("user_id", None)
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


def role_line(person):
    line = f"{person['name']} · {person['main_role']}"
    if person["sub_roles"]:
        line += f" (보조: {', '.join(person['sub_roles'])})"
    return line


def render_result():
    with st.container(key="result"):
        if st.session_state.get("last_result"):
            st.text(st.session_state["last_result"])


def render_team(team, user, my_team_id, my_pending, phase):
    """팀 하나: 팀 이름, 인원, 팀원, 대기 지원. 지원 단추와 (팀원에게만) 투표 단추를 함께 그림"""
    is_member = team["id"] == my_team_id
    with st.container(key=f"team_{team['team_no']}", border=True):
        st.text(f"{team['name']}{' (내 팀)' if is_member else ''} · {len(team['members'])}/4")
        if team["members"]:
            for m in team["members"]:
                st.text(role_line(m))
        else:
            st.text("팀원 없음")

        for p in team["pending"]:
            yes = sum(1 for v in p["votes"].values() if v == "찬성")
            st.text(f"대기 지원: {role_line(p)} (찬성 {yes}/{len(team['members'])})")
            if is_member:
                if user["id"] in p["votes"]:
                    st.text(f"내 투표: {p['votes'][user['id']]}")
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


@st.fragment(run_every=REFRESH_INTERVAL)
def main_view(user_id):
    render_result()
    try:
        user, view = service.load_page(pool, user_id)
    except Exception as e:
        st.error(f"DB 오류({type(e).__name__})")
        return
    if user is None:
        st.session_state.pop("user_id", None)
        set_result(service.Result("막힘", "명단이 새로 올라와 계정이 사라짐. 다시 로그인해야 함"))
        st.rerun()

    phase = view["phase"]
    st.text(f"상태: {PHASE_LABEL.get(phase, phase)}")

    my_team_id = next(
        (t["id"] for t in view["teams"] if any(m["id"] == user["id"] for m in t["members"])), None
    )
    my_pending = next(
        ((t, p) for t in view["teams"] for p in t["pending"] if p["id"] == user["id"]), None
    )

    if user["is_admin"]:
        st.subheader("명단 올리기")
        st.file_uploader("명단 CSV", type="csv", key="admin_roster_file")
        st.number_input("팀 수", min_value=1, value=3, step=1, key="admin_team_count")
        st.button("명단으로 처음 상태 만들기", key="admin_start", on_click=on_start)
        st.button("모집 마감", key="admin_close", on_click=on_close)
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
            st.text(f"내 지원: {my_pending[0]['name']}에서 대기 중")

    st.subheader("팀 목록")
    if not view["teams"]:
        st.text("아직 명단이 올라오지 않음")
    for team in view["teams"]:
        render_team(team, user, my_team_id, my_pending, phase)


st.title("팀 편성")

user = None
user_id = st.session_state.get("user_id")
if user_id is not None:
    try:
        user = service.get_user(pool, user_id)
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

st.button("로그아웃", key="logout", on_click=on_logout)
main_view(user["id"])
