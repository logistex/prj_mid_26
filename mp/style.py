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

# "시나리오 실행" 탭이 열려 있는 동안에만 본문 폭을 넓힘(centered 레이아웃의 본문은 736px라 좌우 분할이 좁음). 다른 화면은 그대로임
WIDE_CSS = """
<style>
[data-testid="stMainBlockContainer"] { max-width: 1400px !important; }
</style>
"""

# 연습 시나리오 탭의 시간 줄과 이전, 이후를 겹친 판(PRD_step4 4.2절). 이 탭이 열려 있는 동안에만 내보냄.
# 색만으로 뜻을 나타내지 않으므로 +, −, 취소선, ○, ✕, ? 같은 기호와 글자가 따로 있음. 색은 .streamlit/config.toml의 theme 값을 따름
PRACTICE_CSS = """
<style>
/* 시간 줄: 한 단계가 한 칸. 지금 보는 단계는 파란 굵은 테두리, 다음 차례는 점선, 아직 실행하지 않은 단계는 흐리게 */
[class*="st-key-practice_row_"] { border: 1px solid #c9d3e3; border-radius: 10px; padding: 2px 8px 6px; margin-bottom: 6px; background: #ffffff; }
[class*="st-key-practice_row_sel_"] { border: 2px solid #2457c5; background: #e8eef7; padding: 1px 7px 5px; }
[class*="st-key-practice_row_next_"] { border: 2px dashed #2457c5; }
[class*="st-key-practice_row_wait_"], [class*="st-key-practice_row_stop_"] { opacity: 0.6; background: #f7f9fc; }
[class*="st-key-practice_row_"] button { border: none; background: transparent; justify-content: flex-start; text-align: left; padding-left: 0; }
[class*="st-key-practice_row_"] button > div { width: 100%; justify-content: flex-start !important; }
[class*="st-key-practice_row_"] button span { width: 100%; justify-content: flex-start !important; }
[class*="st-key-practice_row_"] button p { text-align: left; white-space: normal; }
/* 오른쪽 끝의 실행 단추 */
.st-key-practice_run_next button { white-space: normal; }

/* 판: 팀 카드와 팀이 없는 학생 */
.pb-legend { font-size: 0.85rem; color: #4b5563; margin: 0.2rem 0 0.6rem; }
.pb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; }
.pb-card, .pb-unassigned { border: 1px solid #c9d3e3; border-radius: 10px; padding: 8px 10px; background: #ffffff; }
.pb-card.pb-changed { border: 3px solid #2457c5; padding: 6px 8px; }
.pb-card header, .pb-unassigned header { display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px; }
.pb-count { color: #4b5563; font-size: 0.85rem; }
.pb-flag { margin-left: auto; font-size: 0.75rem; font-weight: 700; color: #ffffff; background: #2457c5; border-radius: 6px; padding: 1px 8px; }
.pb-card ul.pb-slots { list-style: none; margin: 0 !important; padding: 0 !important; display: flex; flex-direction: column; gap: 4px; }
.pb-slots li { margin: 0 !important; }
.pb-slot { border: 1px solid #e3e8f0; border-radius: 6px; padding: 4px 8px; min-height: 34px; background: #f7f9fc; }
.pb-sign { display: inline-block; width: 1.2em; font-weight: 700; }
.pb-new { background: #e6f4ea; color: #17692e; border-color: #8fcaa0; }
.pb-gone { background: #fdecea; color: #b42318; border-color: #f0aaa2; }
.pb-empty { background: #ffffff; border: 1px dashed #8a95a5; color: #4b5563; }
.pb-role { color: #4b5563; font-size: 0.8rem; }
.pb-tag { margin-left: 6px; font-size: 0.72rem; border: 1px solid currentColor; border-radius: 6px; padding: 0 5px; white-space: nowrap; }
.pb-chip { margin-top: 6px; border-radius: 8px; padding: 5px 8px; }
.pb-pending { border: 2px dashed #9a4a00; background: #fff8ee; color: #1f2933; }
.pb-rejected { border: 2px dashed #b42318; background: #fff5f4; color: #b42318; }
.pb-blocked { border: 1px dashed #4b5563; background: #f3f4f6; color: #4b5563; }
.pb-votes { display: flex; flex-wrap: wrap; gap: 2px 10px; margin-top: 2px; font-size: 0.85rem; }
.pb-yes { color: #17692e; font-weight: 600; }
.pb-no { color: #b42318; font-weight: 600; }
.pb-none { color: #4b5563; }
.pb-why { margin-top: 2px; font-size: 0.82rem; }
.pb-sr { position: absolute; left: -9999px; }
.pb-unassigned { margin-top: 10px; }
.pb-people { display: flex; flex-wrap: wrap; gap: 6px; }
.pb-person { border: 1px solid #e3e8f0; border-radius: 16px; padding: 2px 10px; background: #f7f9fc; }
.pb-person.pb-new { border-color: #8fcaa0; background: #e6f4ea; }
.pb-person.pb-gone { border-color: #f0aaa2; background: #fdecea; }
</style>
"""
