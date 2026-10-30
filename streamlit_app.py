# 2026-10-30 21:58 KST
"""팀 편성 앱의 화면(1단계: 로그인, 명단 올리기, 팀 목록). 화면 요소의 key는 공고 2.7절의 표를 그대로 따름"""
import streamlit as st

from mp import service
from mp.config import get_secret
from mp.db import make_pool

st.set_page_config(page_title="팀 편성", layout="centered")


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
    res = service.start_roster(
        pool, st.session_state.get("user_id"), data, st.session_state.get("admin_team_count")
    )
    set_result(res)


def role_line(member):
    line = f"{member['name']} · {member['main_role']}"
    if member["sub_roles"]:
        line += f" (보조: {', '.join(member['sub_roles'])})"
    return line


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

with st.container(key="result"):
    if st.session_state.get("last_result"):
        st.text(st.session_state["last_result"])

if user is None:
    with st.form("login_form"):
        st.text_input("학번", key="login_student_no")
        st.text_input("비밀번호", type="password", key="login_password")
        st.form_submit_button("로그인", key="login_submit", on_click=on_login)
    st.stop()

st.button("로그아웃", key="logout", on_click=on_logout)

if user["is_admin"]:
    st.subheader("명단 올리기")
    st.file_uploader("명단 CSV", type="csv", key="admin_roster_file")
    st.number_input("팀 수", min_value=1, value=3, step=1, key="admin_team_count")
    st.button("명단으로 처음 상태 만들기", key="admin_start", on_click=on_start)

try:
    view = service.load_view(pool)
except Exception as e:
    st.error(f"DB 오류({type(e).__name__})")
    st.stop()

if user["is_admin"]:
    st.subheader("팀이 없는 학생")
    with st.container(key="unassigned"):
        if view["unassigned"]:
            for m in view["unassigned"]:
                st.text(role_line(m))
        else:
            st.text("없음")
else:
    if not any(m["id"] == user["id"] for t in view["teams"] for m in t["members"]):
        st.info("아직 팀이 없음")

st.subheader("팀 목록")
if not view["teams"]:
    st.text("아직 명단이 올라오지 않음")
for team in view["teams"]:
    mine = any(m["id"] == user["id"] for m in team["members"])
    with st.container(key=f"team_{team['team_no']}", border=True):
        st.text(f"{team['name']}{' (내 팀)' if mine else ''} · {len(team['members'])}/4")
        if team["members"]:
            for m in team["members"]:
                st.text(role_line(m))
        else:
            st.text("팀원 없음")
