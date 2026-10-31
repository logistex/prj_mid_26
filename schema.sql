-- 2026-10-30 21:58 KST
-- 팀 편성 앱의 테이블. 이름은 모두 tf_mp_로 시작함. 다시 실행해도 오류가 없음
-- 1단계(학생, 팀, 팀원, 설정), 2단계(지원, 투표), 3단계(AI 호출 기록) 테이블
--
-- RLS(행 수준 보안): 모든 테이블에서 켜고 앱 전용 역할 tf_mp_app에만 모든 행을 허용하는 정책을 만듦(파일 끝).
-- Supabase의 anon, authenticated 역할(공개 API 키)에는 정책이 없으므로 어떤 행도 읽거나 쓸 수 없음
-- 앱은 DATABASE_URL로 tf_mp_app에 접속하고, 이 파일을 적용하는 일은 DATABASE_ADMIN_URL(큰 권한의 역할)로 함

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

-- 3단계: AI 호출 기록. 모델을 1번 부를 때마다 1행. 요청 내용은 저장하지 않고, 응답은 앞 500자와 토큰 수만 저장함
create table if not exists tf_mp_ai_logs (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  model      text not null,
  attempt_no smallint not null,
  outcome    text not null,
  seconds    numeric(6,1),
  detail     text,
  finish_reason     text,
  prompt_tokens     integer,
  completion_tokens integer,
  reasoning_tokens  integer,
  response_head     text
);
-- 이미 만든 테이블에는 원인 분석용 열을 더함(응답 앞 500자와 토큰 수)
alter table tf_mp_ai_logs add column if not exists finish_reason text;
alter table tf_mp_ai_logs add column if not exists prompt_tokens integer;
alter table tf_mp_ai_logs add column if not exists completion_tokens integer;
alter table tf_mp_ai_logs add column if not exists reasoning_tokens integer;
alter table tf_mp_ai_logs add column if not exists response_head text;
alter table tf_mp_ai_logs enable row level security;

-- 앱 전용 DB 역할(최소권한, docs/보안 점검.md 07번)
-- 권한: public 스키마 USAGE, 위 8개 테이블의 SELECT, INSERT, UPDATE, DELETE, 그 테이블들의 시퀀스 USAGE와 SELECT뿐임
-- CREATE 권한, 다른 테이블 권한, BYPASSRLS는 주지 않음. 비밀번호는 여기에 쓰지 않고 scripts/set_app_role_password.py가 정함
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'tf_mp_app') then
    create role tf_mp_app login nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
  end if;
end
$$;

alter role tf_mp_app nocreatedb nocreaterole nobypassrls;  -- NOSUPERUSER는 지정하지 않음(Supabase의 postgres는 슈퍼유저가 아니라 그 속성을 바꿀 수 없음. 새 역할은 기본이 슈퍼유저 아님)
revoke create on schema public from tf_mp_app;
grant usage on schema public to tf_mp_app;

do $$
declare
  t text;
  s text;
begin
  foreach t in array array['tf_mp_students','tf_mp_student_sub_roles','tf_mp_teams','tf_mp_members',
                           'tf_mp_settings','tf_mp_applications','tf_mp_votes','tf_mp_ai_logs']
  loop
    execute format('grant select, insert, update, delete on public.%I to tf_mp_app', t);
    execute format('drop policy if exists tf_mp_app_all on public.%I', t);
    execute format('create policy tf_mp_app_all on public.%I for all to tf_mp_app using (true) with check (true)', t);
    -- identity 열의 시퀀스(없는 테이블은 null)
    for s in select pg_get_serial_sequence(format('public.%I', t), a.attname)
             from pg_attribute a
             where a.attrelid = format('public.%I', t)::regclass and a.attidentity <> '' and not a.attisdropped
    loop
      if s is not null then
        execute format('grant usage, select on sequence %s to tf_mp_app', s);
      end if;
    end loop;
  end loop;
end
$$;
