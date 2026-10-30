# 2026-10-30 21:58 KST
"""명단 CSV 검증 시험(PRD_step1 8장 시험 4). DB를 쓰지 않음"""
import pytest

from conftest import DATA
from mp.roster import RosterError, parse_roster

HEADER = "student_no,name,main_role,sub_roles\n"


@pytest.mark.parametrize("name,count", [("쉬움", 8), ("중간", 12), ("어려움", 16)])
def test_practice_csv_reads_with_bom(name, count):
    data = (DATA / f"{name}.csv").read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    students = parse_roster(data)
    assert len(students) == count


def test_sub_roles_split_by_semicolon():
    students = {s["student_no"]: s for s in parse_roster((DATA / "중간.csv").read_bytes())}
    assert students["2026201"]["sub_roles"] == ["발표자", "테스터"]
    assert students["2026204"]["sub_roles"] == []


def test_reads_without_bom():
    students = parse_roster((HEADER + "1,가,기획자,\n").encode("utf-8"))
    assert students == [{"student_no": "1", "name": "가", "main_role": "기획자", "sub_roles": []}]


def test_role_whitespace_is_normalized():
    students = parse_roster((HEADER + "1,가,기획자,보고서  작성자\n").encode("utf-8"))
    assert students[0]["sub_roles"] == ["보고서 작성자"]


def test_sub_role_equal_to_main_is_dropped():
    students = parse_roster((HEADER + "1,가,기획자,기획자;발표자\n").encode("utf-8"))
    assert students[0]["sub_roles"] == ["발표자"]


@pytest.mark.parametrize(
    "body,expected",
    [
        ("student_no,name,main_role\n1,가,기획자\n", "열이"),
        (HEADER + "1,가,기획자\n", "2행의 열 수가 4개가 아님"),
        (HEADER + ",가,기획자,\n", "2행의 학번이 비어 있음"),
        (HEADER + "1,,기획자,\n", "2행의 이름이 비어 있음"),
        (HEADER + "admin,가,기획자,\n", "admin은 쓸 수 없음"),
        (HEADER + "1,가,기획자,\n1,나,테스터,\n", "학번이 중복됨: 1"),
        (HEADER + "1,가,마법사,\n", "2행의 역할 값이 올바르지 않음"),
        (HEADER + "1,가,기획자,마법사\n", "2행의 역할 값이 올바르지 않음"),
        (HEADER + "1,가,기획자,발표자;테스터;웹 프로그래머\n", "2행의 보조 역할이 3개 이상임"),
        (HEADER, "명단에 학생이 없음"),
        ("", "비어 있음"),
    ],
)
def test_invalid_roster_is_rejected(body, expected):
    with pytest.raises(RosterError) as e:
        parse_roster(body.encode("utf-8"))
    assert expected in str(e.value)


def test_non_utf8_is_rejected():
    with pytest.raises(RosterError) as e:
        parse_roster((HEADER + "1,가,기획자,\n").encode("cp949"))
    assert "UTF-8" in str(e.value)
