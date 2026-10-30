# 2026-10-30 21:58 KST
"""명단 CSV 읽기와 검증. 하나라도 어기면 RosterError를 일으키고 아무것도 바꾸지 않음"""
import csv
import io

from .config import ADMIN_STUDENT_NO, ROLES

HEADER = ["student_no", "name", "main_role", "sub_roles"]


class RosterError(Exception):
    pass


def _norm(text):
    return " ".join(text.split())


def parse_roster(data):
    """CSV 바이트를 [{student_no, name, main_role, sub_roles}]로 바꿈. BOM이 있어도 읽음"""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RosterError("파일이 UTF-8이 아님")
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        raise RosterError("명단 파일이 비어 있음")
    if [h.strip() for h in header] != HEADER:
        raise RosterError("열이 student_no,name,main_role,sub_roles가 아님")

    students = []
    seen = set()
    for row in reader:
        n = reader.line_num
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != 4:
            raise RosterError(f"{n}행의 열 수가 4개가 아님")
        student_no, name, main_role, subs = (cell.strip() for cell in row)
        if not student_no:
            raise RosterError(f"{n}행의 학번이 비어 있음")
        if not name:
            raise RosterError(f"{n}행의 이름이 비어 있음")
        if student_no == ADMIN_STUDENT_NO:
            raise RosterError(f"{n}행의 학번 admin은 쓸 수 없음")
        if student_no in seen:
            raise RosterError(f"학번이 중복됨: {student_no}")
        seen.add(student_no)

        main_role = _norm(main_role)
        if main_role not in ROLES:
            raise RosterError(f"{n}행의 역할 값이 올바르지 않음")
        tokens = [_norm(t) for t in subs.split(";") if t.strip()]
        if len(tokens) > 2:
            raise RosterError(f"{n}행의 보조 역할이 3개 이상임")
        if any(t not in ROLES for t in tokens):
            raise RosterError(f"{n}행의 역할 값이 올바르지 않음")
        sub_roles = [t for i, t in enumerate(tokens) if t != main_role and t not in tokens[:i]]
        students.append(
            {"student_no": student_no, "name": name, "main_role": main_role, "sub_roles": sub_roles}
        )
    if not students:
        raise RosterError("명단에 학생이 없음")
    return students
