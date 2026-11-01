# 2026-11-01 12:36 KST
"""연습 시나리오 화면의 판: 이전과 이후를 한 판에 겹쳐 바뀐 것만 표시함(PRD_step4 4.2절). 화면과 DB를 모름

팀마다 자리 4칸짜리 카드, 대기 중인 지원과 팀원의 투표, 팀이 없는 학생 줄을 모델로 만들고 HTML 문자열로 바꿈.
색만으로 뜻을 나타내지 않도록 +, −, 취소선, ○, ✕, ? 같은 기호와 글자를 함께 씀. 모델은 실행 기록의 전후 상태와 지원 경과로만 만들며
이 모듈에는 어떤 시나리오의 학번, 이름, 단계 번호도 쓰지 않음(중간과제 공고 6.3절 감점 19번)
"""
from html import escape

from . import rules
from .practice import application_outcomes, short_name

SLOTS = 4
VOTE_MARK = {"찬성": "○", "거부": "✕", None: "?"}
VOTE_CLASS = {"찬성": "pb-yes", "거부": "pb-no", None: "pb-none"}
VOTE_WORD = {"찬성": "찬성", "거부": "거부", None: "투표 전"}


def role_fillers(members):
    """필수 포함 역할(기획자, 웹 프로그래머)마다 맡은 팀원: [(역할, 팀원 또는 None, 보조 역할로 맡았는지)]

    두 역할은 서로 다른 팀원이 맡아야 하고, 맡은 팀원 수가 많은 쪽, 그다음 주 역할로 맡은 수가 많은 쪽, 그다음 팀원 순서를 따름
    """
    roles = rules.REQUIRED_ROLES
    options = [[m for m in members if role in rules.roles_of(m)] + [None] for role in roles]
    best, best_score = None, None
    for first in options[0]:
        for second in options[1]:
            if first is not None and first is second:
                continue
            picked = (first, second)
            score = (sum(p is not None for p in picked),
                     sum(1 for p, role in zip(picked, roles) if p is not None and p["main_role"] == role))
            if best_score is None or score > best_score:
                best, best_score = picked, score
    return [(role, p, p is not None and p["main_role"] != role) for role, p in zip(roles, best)]


def _same_main(members):
    """주 역할이 같은 팀원: [(역할, [이름])]"""
    groups = {}
    for m in members:
        groups.setdefault(m["main_role"], []).append(short_name(m["name"]))
    return [(role, names) for role, names in groups.items() if len(names) > 1]


def _role(person):
    role = person.get("main_role") or ""
    subs = person.get("sub_roles") or []
    return role + (f" (보조: {', '.join(subs)})" if subs else "")


def _names(*views):
    out = {}
    for v in views:
        for t in v["teams"]:
            for p in [*t["members"], *t["pending"]]:
                out[p["student_no"]] = p
        for u in v["unassigned"]:
            out[u["student_no"]] = u
    return out


def _vote_list(voters, votes_by_no):
    return [(short_name(v["name"]), votes_by_no.get(v["student_no"])) for v in voters]


def _pending_votes(entry, members):
    """대기 지원의 votes(투표한 학생의 DB id → 찬성, 거부)를 학번 기준으로 바꿈"""
    by_id = {m["id"]: m["student_no"] for m in members}
    return {by_id[i]: v for i, v in entry.get("votes", {}).items() if i in by_id}


def build_board(before, after, rows, record_rows):
    """실행 전과 후의 상태, 하위 단계의 행과 실행 기록으로 판 모델을 만듦"""
    people = _names(before, after)
    outcomes = application_outcomes(rows, record_rows)
    bt = {t["team_no"]: t for t in before["teams"]}
    teams = []
    for ta in after["teams"]:
        no = ta["team_no"]
        tb = bt.get(no, {"members": [], "pending": []})
        slots, apps = [], []
        after_nos = {m["student_no"] for m in ta["members"]}
        before_nos = {m["student_no"] for m in tb["members"]}
        pend_before = {p["student_no"]: p for p in tb["pending"]}
        pend_after = {p["student_no"]: p for p in ta["pending"]}
        mine = [o for o in outcomes if (o.team_no or _outcome_team(before, after, o.student_no)) == no]

        for m in tb["members"]:
            slots.append({"state": "same" if m["student_no"] in after_nos else "gone", "name": short_name(m["name"]),
                          "role": _role(m), "votes": None})
        for m in ta["members"]:
            if m["student_no"] in before_nos:
                continue
            votes_by_no = _pending_votes(pend_before.get(m["student_no"], {}), tb["members"])
            for o in mine:
                if o.student_no == m["student_no"]:
                    votes_by_no.update(dict(o.votes))
            votes = _vote_list(tb["members"], votes_by_no) if votes_by_no else None
            slots.append({"state": "proposed" if m.get("proposed") else "new", "name": short_name(m["name"]), "role": _role(m),
                          "votes": votes})

        for p in ta["pending"]:
            apps.append({"state": "pending", "new": p["student_no"] not in pend_before, "name": short_name(p["name"]),
                         "role": _role(p), "votes": _vote_list(ta["members"], _pending_votes(p, ta["members"]))})
        shown = set(pend_after)
        for p in tb["pending"]:  # 결과가 났는데 팀원이 되지 못한 지원(거절됨)
            if p["student_no"] in shown or p["student_no"] in after_nos:
                continue
            votes_by_no = _pending_votes(p, tb["members"])
            reason = ""
            for o in mine:
                if o.student_no == p["student_no"]:
                    votes_by_no.update(dict(o.votes))
                    reason = o.reason or reason
            if not reason and before["phase"] != after["phase"]:
                reason = "모집을 마감함"  # 대기 지원이 전후 상태 사이에 사라졌고 이 사이에 모집이 마감됨
            apps.append({"state": "rejected", "new": False, "name": short_name(p["name"]), "role": _role(p),
                         "votes": _vote_list(tb["members"], votes_by_no), "reason": reason})
            shown.add(p["student_no"])
        for o in mine:
            if o.student_no in shown or o.student_no in after_nos:
                continue
            person = people.get(o.student_no, {"name": o.student_no, "main_role": "", "sub_roles": []})
            if o.status == "거절":
                apps.append({"state": "rejected", "new": False, "name": short_name(person["name"]), "role": _role(person),
                             "votes": _vote_list(tb["members"], dict(o.votes)), "reason": o.reason})
            elif o.status == "막힘":
                apps.append({"state": "blocked", "new": False, "name": short_name(person["name"]), "role": _role(person),
                             "votes": [], "reason": o.first_message})

        shown_slots = len(slots)
        slots.extend({"state": "empty"} for _ in range(max(0, SLOTS - shown_slots)))
        changed = (any(s["state"] in ("new", "proposed", "gone") for s in slots)
                   or any(a["state"] in ("rejected", "blocked") or a["new"] for a in apps)
                   or any(_pending_votes(p, tb["members"]) != _pending_votes(pend_before[no2], tb["members"])
                          for no2, p in pend_after.items() if no2 in pend_before))
        fillers = [{"role": role, "who": short_name(p["name"]) if p else None, "sub": sub}
                   for role, p, sub in role_fillers(ta["members"])]
        teams.append({"team_no": no, "name": ta["name"], "count": len(ta["members"]), "changed": changed,
                      "slots": slots, "apps": apps, "roles": fillers, "dups": _same_main(ta["members"])})

    ua, ub = {u["student_no"]: u for u in after["unassigned"]}, {u["student_no"]: u for u in before["unassigned"]}
    unassigned = [{"state": "same" if no in ub else "new", "name": short_name(u["name"]), "role": _role(u)} for no, u in ua.items()]
    unassigned += [{"state": "gone", "name": short_name(u["name"]), "role": _role(u)} for no, u in ub.items() if no not in ua]
    confirmed = after["phase"] == "confirmed"
    total = {
        "loose": len([u for u in unassigned if u["state"] != "gone"]),
        "size": sum(1 for t in after["teams"] if not rules.MIN_TEAM_SIZE <= len(t["members"]) <= rules.MAX_TEAM_SIZE),
        "dup": sum(1 for t in teams if t["dups"]),
        "required": sum(1 for t in teams if any(r["who"] is None for r in t["roles"])),
    }
    return {"teams": teams, "unassigned": unassigned, "confirmed": confirmed, "total": total}


def _outcome_team(before, after, student_no):
    for view in (before, after):
        for t in view["teams"]:
            if any(p["student_no"] == student_no for p in t["pending"]):
                return t["team_no"]
    return None


def state_board(view):
    """바뀐 것을 표시하지 않는 지금 상태의 판(아직 실행한 단계가 없을 때)"""
    return build_board(view, view, (), [])


# ---- HTML ----

def _votes_html(votes):
    if not votes:
        return ""
    items = "".join(
        f'<span class="pb-vote {VOTE_CLASS[v]}" title="{VOTE_WORD[v]}">{escape(name)} {VOTE_MARK[v]}'
        f'<span class="pb-sr"> {VOTE_WORD[v]}</span></span>' for name, v in votes)
    return f'<div class="pb-votes">{items}</div>'


def _slot_html(s):
    if s["state"] == "empty":
        return '<li class="pb-slot pb-empty"><span class="pb-sign"> </span>빈 자리</li>'
    name, role = escape(s["name"]), escape(s["role"])
    if s["state"] == "gone":
        return (f'<li class="pb-slot pb-gone"><span class="pb-sign">−</span><s>{name}</s> '
                f'<span class="pb-role">{role}</span><span class="pb-tag">빠짐</span></li>')
    sign, tag = ("+", "새 팀원") if s["state"] == "new" else ("+", "배정안") if s["state"] == "proposed" else (" ", "")
    cls = "pb-new" if sign == "+" else "pb-same"
    tag_html = f'<span class="pb-tag">{tag}</span>' if tag else ""
    return (f'<li class="pb-slot {cls}"><span class="pb-sign">{sign}</span><b>{name}</b> '
            f'<span class="pb-role">{role}</span>{tag_html}{_votes_html(s.get("votes"))}</li>')


def _app_html(a):
    name, role = escape(a["name"]), escape(a["role"])
    if a["state"] == "pending":
        tag = "새 지원 · 대기" if a["new"] else "대기 중인 지원"
        return (f'<div class="pb-chip pb-pending"><b>{tag}</b> {name} <span class="pb-role">{role}</span>'
                f'{_votes_html(a["votes"])}</div>')
    why = f'<div class="pb-why">까닭: {escape(a["reason"])}</div>' if a.get("reason") else ""
    if a["state"] == "rejected":
        return (f'<div class="pb-chip pb-rejected"><span class="pb-sign">−</span><s>{name}</s> '
                f'<span class="pb-role">{role}</span><span class="pb-tag">거절된 지원</span>{_votes_html(a["votes"])}{why}</div>')
    return (f'<div class="pb-chip pb-blocked"><b>지원 막힘</b> {name} <span class="pb-role">{role}</span>{why}</div>')


WAIT_WORD = "남음"
OK_MARK = '<span class="pb-yes">○</span>'
BAD_MARK = '<span class="pb-no">✕</span>'


def _open_mark(confirmed, count=None):
    """아직 채우지 못한 것의 표시: 확정하기 전에는 회색 글자, 확정한 뒤에는 빨간 ✕"""
    more = f"({count}팀)" if count else ""
    return f'<span class="pb-no">✕{more}</span>' if confirmed else f'<span class="pb-none">{WAIT_WORD}{more}</span>'



def _need_row(name, mark, text=""):
    """역할 이름 칸과 기호 칸의 폭이 고정이라 카드 안의 세 줄과 카드 사이에서 ○, ✕가 같은 세로선에 놓임"""
    return (f'<div class="pb-row"><span class="pb-rname">{escape(name)}</span> <span class="pb-mk">{mark}</span> '
            f'<span class="pb-rtext">{text}</span></div>')


def _team_need_html(t, confirmed):
    rows = []
    for r in t["roles"]:
        if r["who"] is None:
            rows.append(_need_row(r["role"], BAD_MARK if confirmed else '<span class="pb-none">필요</span>'))
        else:
            rows.append(_need_row(r["role"], OK_MARK, escape(r["who"]) + ("(보조)" if r["sub"] else "")))
    if t["dups"]:
        same = "; ".join(f'{escape(role)}({escape(", ".join(names))})' for role, names in t["dups"])
        rows.append(_need_row("주 역할 중복", BAD_MARK, same))
    else:
        rows.append(_need_row("주 역할 중복", OK_MARK, "없음"))
    return f'<div class="pb-need">{"".join(rows)}</div>'


def _total_html(model):
    total, confirmed = model["total"], model["confirmed"]

    def mark(bad, wait_ok=True):
        if not bad:
            return OK_MARK
        return _open_mark(confirmed, bad) if wait_ok else f'{BAD_MARK}({bad}팀)'

    parts = [f'팀이 없는 학생 {total["loose"]}명', f'인원 2~4명 {mark(total["size"])}',
             f'주 역할 중복 없음 {mark(total["dup"], wait_ok=False)}', f'필수 포함 역할 {mark(total["required"])}']
    return f'<p class="pb-total"><b>전체</b>: {" · ".join(parts)}</p>'


def board_html(model):
    cards = []
    confirmed = model["confirmed"]
    for t in model["teams"]:
        flag = '<span class="pb-flag">◆ 바뀜</span>' if t["changed"] else ""
        slots = "".join(_slot_html(s) for s in t["slots"])
        apps = "".join(_app_html(a) for a in t["apps"])
        cards.append(
            f'<section class="pb-card{" pb-changed" if t["changed"] else ""}">'
            f'<header><b>{escape(t["name"])}</b> <span class="pb-count">{t["count"]}/4</span>{flag}</header>'
            f'{_team_need_html(t, confirmed)}'
            f'<ul class="pb-slots">{slots}</ul>{apps}</section>')
    chips = []
    for u in model["unassigned"]:
        name, role = escape(u["name"]), escape(u["role"])
        if u["state"] == "gone":
            chips.append(f'<span class="pb-person pb-gone"><span class="pb-sign">−</span><s>{name}</s></span>')
        elif u["state"] == "new":
            chips.append(f'<span class="pb-person pb-new"><span class="pb-sign">+</span><b>{name}</b> '
                         f'<span class="pb-role">{role}</span></span>')
        else:
            chips.append(f'<span class="pb-person"><b>{name}</b> <span class="pb-role">{role}</span></span>')
    rest = "".join(chips) or '<span class="pb-role">없음</span>'
    legend = ('<p class="pb-legend">+ 새로 들어옴 · − 빠짐이나 거절(취소선) · 점선 칩 = 대기 중인 지원 · '
              '투표 ○ 찬성, ✕ 거부, ? 아직 투표하지 않음(회색)</p>')
    return (f'{_total_html(model)}{legend}<div class="pb-grid">{"".join(cards)}</div>'
            f'<section class="pb-unassigned"><header><b>팀이 없는 학생</b> '
            f'<span class="pb-count">{sum(1 for u in model["unassigned"] if u["state"] != "gone")}명</span></header>'
            f'<div class="pb-people">{rest}</div></section>')
