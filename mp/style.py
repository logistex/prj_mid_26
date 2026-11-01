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
/* 누를 수 있는 것은 진한 테두리, 채운 바탕, 아래쪽 그림자, 오른쪽 끝의 동작 기호를 늘 보이게 하고(마우스를 올리면 더 진해짐),
   상황을 알리는 글(결과, 꼬리표)은 테두리, 바탕, 그림자 없이 기호와 색 글자만 씀 */
[class*="st-key-practice_row_"] { position: relative; margin-bottom: 8px; gap: 0; }
[class*="st-key-practice_row_"] .stElementContainer:has(.pv-card, .pv-result) { margin: 0; }
[class*="st-key-practice_row_go_"] .stElementContainer:has(.pv-result) { position: static; }
.pv-result { font-weight: 700; white-space: nowrap; }
.pv-yes { color: #17692e; } .pv-no { color: #b42318; } .pv-wait { color: #9a4a00; } .pv-none { color: #4b5563; } .pv-next { color: #2457c5; }
/* 실행했고 지금 보이지 않는 단계: 칸 전체가 단추. 결과는 첫 줄 오른쪽에 고정하고 단추 위에 겹치되 눌림은 단추로 넘김 */
[class*="st-key-practice_row_go_"] button {
    border: 2px solid #1f2937; background: #dfe7f5; box-shadow: 0 3px 0 #1f2937; border-radius: 10px;
    padding: 9px 9.5rem 9px 12px; min-height: 48px; justify-content: flex-start; text-align: left; cursor: pointer;
}
[class*="st-key-practice_row_go_"] button:hover { background: #cbd8ee; box-shadow: 0 5px 0 #111827; }
[class*="st-key-practice_row_go_"] button > div, [class*="st-key-practice_row_go_"] button span { width: 100%; justify-content: flex-start !important; }
[class*="st-key-practice_row_go_"] button p { text-align: left; white-space: normal; }
[class*="st-key-practice_row_go_"] button::after {
    content: "보기 ›"; position: absolute; right: 14px; top: 9px; font-weight: 700; color: #1f2937; white-space: nowrap;
}
[class*="st-key-practice_row_go_"] .pv-result { position: absolute; right: 5.2rem; top: 9px; pointer-events: none; }
/* 지금 오른쪽에 보이는 단계: 굵은 파란 테두리, 옅은 파란 바탕, 왼쪽 끝의 ▶. 단추가 아님 */
.pv-card { display: flex; align-items: flex-start; gap: 6px; padding: 9px 12px; border-radius: 10px; }
.pv-mark { width: 1.1em; flex: none; color: #2457c5; font-weight: 700; }
.pv-text { flex: 1; min-width: 0; }
[class*="st-key-practice_row_sel_"] .pv-card { border: 3px solid #2457c5; background: #e8eef7; padding: 7px 10px; }
/* 아직 실행하지 않은 단계: 흐리게 두고 누를 수 없음 */
[class*="st-key-practice_row_next_"] .pv-card, [class*="st-key-practice_row_wait_"] .pv-card, [class*="st-key-practice_row_stop_"] .pv-card {
    opacity: 0.55; border-bottom: 1px solid #d8dee9; border-radius: 0;
}
[class*="st-key-practice_row_next_"] .pv-card .pv-result { opacity: 1; }
/* 오른쪽의 동작 단추: 실행, 이전과 다음 */
.st-key-practice_run_next button, .st-key-practice_prev button, .st-key-practice_next button {
    border: 2px solid #1f2937; box-shadow: 0 3px 0 #1f2937; font-weight: 700; white-space: normal;
}
.st-key-practice_run_next button:not(:disabled):hover, .st-key-practice_prev button:not(:disabled):hover,
.st-key-practice_next button:not(:disabled):hover { box-shadow: 0 5px 0 #111827; cursor: pointer; }
.st-key-practice_run_next button::after { content: "›"; margin-left: 8px; }
.st-key-practice_prev button:disabled, .st-key-practice_next button:disabled { box-shadow: none; border-color: #c9d3e3; }

/* 판: 팀 카드와 팀이 없는 학생 */
.pb-total { font-size: 0.9rem; margin: 0.2rem 0 0.3rem; }
.pb-need { font-size: 0.82rem; margin: -2px 0 6px; line-height: 1.5; }
.pb-legend { font-size: 0.85rem; color: #4b5563; margin: 0.2rem 0 0.6rem; }
.pb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; }
.pb-card, .pb-unassigned { border: 1px solid #c9d3e3; border-radius: 10px; padding: 8px 10px; background: #ffffff; }
.pb-card.pb-changed { border: 3px solid #2457c5; padding: 6px 8px; }
.pb-card header, .pb-unassigned header { display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px; }
.pb-count { color: #4b5563; font-size: 0.85rem; }
.pb-flag { margin-left: auto; font-size: 0.8rem; font-weight: 700; color: #2457c5; }
.pb-card ul.pb-slots { list-style: none; margin: 0 !important; padding: 0 !important; display: flex; flex-direction: column; gap: 4px; }
.pb-slots li { margin: 0 !important; }
.pb-slot { border: 1px solid #e3e8f0; border-radius: 6px; padding: 4px 8px; min-height: 34px; background: #f7f9fc; }
.pb-sign { display: inline-block; width: 1.2em; font-weight: 700; }
.pb-new { background: #e6f4ea; color: #17692e; border-color: #8fcaa0; }
.pb-gone { background: #fdecea; color: #b42318; border-color: #f0aaa2; }
.pb-empty { background: #ffffff; border: 1px dashed #8a95a5; color: #4b5563; }
.pb-role { color: #4b5563; font-size: 0.8rem; }
.pb-tag { margin-left: 6px; font-size: 0.78rem; font-weight: 700; white-space: nowrap; }
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
