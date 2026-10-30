-- 2026-10-30 21:58 KST
-- 팀 편성 앱의 테이블. 이름은 모두 tf_mp_로 시작함. 다시 실행해도 오류가 없음
-- 1단계 테이블. 지원, 투표, AI 호출 기록 테이블은 2단계, 3단계에서 이 파일에 추가함

create table if not exists tf_mp_students (
  id            bigint generated always as identity primary key,
  student_no    text not null unique,
  name          text not null,
  main_role     text check (main_role in
                  ('기획자','웹 프로그래머','프론트엔드 디자이너','테스터','보고서 작성자','발표자')),
  password_hash text not null,
  is_admin      boolean not null default false,
  check (is_admin = (main_role is null))
);

create table if not exists tf_mp_student_sub_roles (
  student_id bigint not null references tf_mp_students(id) on delete cascade,
  role       text not null check (role in
               ('기획자','웹 프로그래머','프론트엔드 디자이너','테스터','보고서 작성자','발표자')),
  primary key (student_id, role)
);

create table if not exists tf_mp_teams (
  id      bigint generated always as identity primary key,
  team_no int  not null unique check (team_no >= 1),
  name    text not null unique
);

-- 같은 (team_id, slot_no)와 같은 student_id는 DB가 중복을 막음(마지막 정원에 2명이 동시에 들어가는 경우)
create table if not exists tf_mp_members (
  team_id    bigint   not null references tf_mp_teams(id) on delete cascade,
  slot_no    smallint not null check (slot_no between 1 and 4),
  student_id bigint   not null unique references tf_mp_students(id) on delete cascade,
  primary key (team_id, slot_no)
);

create table if not exists tf_mp_settings (
  key   text primary key,
  value text not null
);
