# 2026-10-30 22:40 KST
"""팀 규칙. DB를 만지지 않는 순수 함수(PRD_step2 3장). 학생은 {id, main_role, sub_roles}를 가진 dict임"""

MAX_TEAM_SIZE = 4
REQUIRED_ROLES = ("기획자", "웹 프로그래머")


def roles_of(student):
    """학생 1명이 맡을 수 있는 역할 집합: 주 역할과 보조 역할의 합집합"""
    return {student["main_role"], *student["sub_roles"]}


def required_deficit(students):
    """필수 포함 역할(기획자, 웹 프로그래머) 2개 가운데 아직 채우지 못한 수.

    두 역할은 서로 다른 학생이 맡아야 하므로, 1명이 둘 다 맡을 수 있어도 1개만 채움
    """
    planners = {s["id"] for s in students if REQUIRED_ROLES[0] in roles_of(s)}
    webs = {s["id"] for s in students if REQUIRED_ROLES[1] in roles_of(s)}
    both = planners | webs
    if planners and webs and len(both) >= 2:
        filled = 2
    elif both:
        filled = 1
    else:
        filled = 0
    return 2 - filled


def join_violation(members, applicant):
    """applicant가 members의 팀에 들어갈 때 어기는 첫 규칙의 이유. 어기지 않으면 None

    PRD_step2 4.1절의 검사 순서: R1(정원), R2(주 역할 중복), R3(필수 포함 역할 점검)
    """
    if len(members) >= MAX_TEAM_SIZE:
        return "팀이 꽉 참"
    if any(m["main_role"] == applicant["main_role"] for m in members):
        return "같은 주 역할의 팀원이 있음"
    after = [*members, applicant]
    if required_deficit(after) > MAX_TEAM_SIZE - len(after):
        return "필수 포함 역할(기획자, 웹 프로그래머)을 맡을 학생의 자리가 모자람"
    return None
