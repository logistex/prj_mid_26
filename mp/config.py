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


# OpenRouter 무료 텍스트 모델 3개. 1차, 2차, 3차 순으로 부름(PRD_step3 5.1절)
MODELS = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "cohere/north-mini-code:free",
    "poolside/laguna-s-2.1:free",
)
AI_TIMEOUT_SECONDS = 120  # 모델 1개마다 응답을 기다리는 전체 시간의 한도
AI_BASE_URL = "https://openrouter.ai/api/v1"


def validate_models(models):
    """무료 모델(:free로 끝남)만 허용하고, 자동 연결 라우터 openrouter/free는 쓰지 않음(공고 6.3절 14번)"""
    for m in models:
        if not m.endswith(":free") or m == "openrouter/free":
            raise ValueError(f"허용하지 않는 모델 이름: {m}")
    return tuple(models)


def ai_config():
    """(모델 목록, 시간 제한, 주소). 환경 변수 MP_AI_MODELS, MP_AI_TIMEOUT, MP_AI_BASE_URL은 시험에서 실패를 재현하려고만 씀"""
    raw = os.environ.get("MP_AI_MODELS")
    models = validate_models([m.strip() for m in raw.split(",") if m.strip()]) if raw else validate_models(MODELS)
    timeout = float(os.environ.get("MP_AI_TIMEOUT") or AI_TIMEOUT_SECONDS)
    base_url = os.environ.get("MP_AI_BASE_URL") or AI_BASE_URL
    return models, timeout, base_url
