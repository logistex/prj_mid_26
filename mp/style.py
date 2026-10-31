# 2026-10-31 10:12 KST
"""화면 모양을 다듬는 CSS(디자인 2차). 요소의 key는 그대로 두고 st-key-<key> 클래스로만 고름

st-key- 클래스의 위치와 이름은 스트림릿 판 사이에 안정적이지 않다고 문서가 밝히므로 requirements.txt의 판(1.66.1) 기준임.
CSS가 먹지 않아도 화면의 기능과 글은 그대로이고 모양만 기본 단추로 보임
"""

CSS = """
<style>
/* 모든 단추의 높이를 44px 이상으로 함(공고 2.7절의 key는 건드리지 않음) */
.stButton > button, .stFormSubmitButton > button { min-height: 44px; }
/* 기존 팀과 지원, 투표를 모두 지우는 단추는 기본 단추와 다르게 빨간 테두리로 구별함 */
.st-key-admin_start button { border-color: #b42318; color: #b42318; }
.st-key-admin_start button:hover, .st-key-admin_start button:focus-visible {
    border-color: #b42318; color: #ffffff; background-color: #b42318;
}
</style>
"""
