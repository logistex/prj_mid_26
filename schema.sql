-- 2026-10-30 21:58 KST
-- 팀 편성 앱의 테이블. 이름은 모두 tf_mp_로 시작함. 다시 실행해도 오류가 없음
-- 1단계, 2단계 테이블. AI 호출 기록 테이블은 3단계에서 이 파일에 추가함
--
-- RLS(행 수준 보안): 모든 테이블에서 켜고 정책을 만들지 않음. 앱은 DATABASE_URL로 소유자 역할에 직접 접속하므로
-- RLS의 영향을 받지 않고, Supabase의 anon, authenticated 역할(공개 API 키)로는 어떤 행도 읽거나 쓸 수 없음

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
alter table tf_mp_students enable row level security;

create table if not exists tf_mp_student_sub_roles (
  student_id bigint not null references tf_mp_students(id) on delete cascade,
  role       text not null check (role in
               ('기획자','웹 프로그래머','프론트엔드 디자이너','테스터','보고서 작성자','발표자')),
  primary key (student_id, role)
);
alter table tf_mp_student_sub_roles enable row level security;

create table if not exists tf_mp_teams (
  id      bigint generated always as identity primary key,
  team_no int  not null unique check (team_no >= 1),
  name    text not null unique
);
alter table tf_mp_teams enable row level security;

-- 같은 (team_id, slot_no)와 같은 student_id는 DB가 중복을 막음(마지막 정원에 2명이 동시에 들어가는 경우)
create table if not exists tf_mp_members (
  team_id    bigint   not null references tf_mp_teams(id) on delete cascade,
  slot_no    smallint not null check (slot_no between 1 and 4),
  student_id bigint   not null unique references tf_mp_students(id) on delete cascade,
  primary key (team_id, slot_no)
);
alter table tf_mp_members enable row level security;

create table if not exists tf_mp_settings (
  key   text primary key,
  value text not null
);
alter table tf_mp_settings enable row level security;

-- 2단계: 지원과 투표
create table if not exists tf_mp_applications (
  id         bigint generated always as identity primary key,
  team_id    bigint not null references tf_mp_teams(id) on delete cascade,
  student_id bigint not null references tf_mp_students(id) on delete cascade,
  status     text   not null check (status in ('대기','승인','거절')),
  reason     text,
  created_at timestamptz not null default now(),
  decided_at timestamptz
);
alter table tf_mp_applications enable row level security;

-- 한 학생의 대기 지원은 1개까지
create unique index if not exists tf_mp_applications_one_pending
  on tf_mp_applications (student_id) where status = '대기';

create table if not exists tf_mp_votes (
  application_id bigint not null references tf_mp_applications(id) on delete cascade,
  voter_id       bigint not null references tf_mp_students(id) on delete cascade,
  vote           text   not null check (vote in ('찬성','거부')),
  created_at     timestamptz not null default now(),
  primary key (application_id, voter_id)
);
alter table tf_mp_votes enable row level security;
