# 2026-10-30 21:58 KST
"""비밀 값 읽기와 공통 상수. 비밀 값은 어디에도 출력하지 않음"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ROLES = (
    "기획자",
    "웹 프로그래머",
    "프론트엔드 디자이너",
    "테스터",
    "보고서 작성자",
    "발표자",
)

DEFAULT_STUDENT_PASSWORD = "1234"
ADMIN_STUDENT_NO = "admin"


def get_secret(name):
    """환경 변수를 먼저 보고, 없으면 st.secrets를 봄. 없으면 None"""
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:
        return None
    return value or None


def has_secret(name):
    return get_secret(name) is not None
