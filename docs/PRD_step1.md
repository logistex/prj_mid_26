<!-- 2026-10-30 21:40 KST -->
# PRD 1단계: DB 테이블, 로그인, 명단 올리기와 팀 만들기

## 1. 요약

- 1단계는 앱의 바탕을 만듦: DB 테이블(`tf_mp_` 접두사), 학번과 비밀번호 로그인, 관리자의 명단 올리기와 팀 만들기
- 이 단계가 끝나면 관리자가 CSV와 팀 수로 초기 상태를 만들고, 학생이 `1234`로 로그인해 팀 목록을 볼 수 있음
- 지원, 투표, 마감은 PRD_step2 1장(요약)에서, AI 배정과 확정은 PRD_step3 1장(요약)에서 다룸
- 3장 표(중간과제 공고 3장, 기능별 쉬운 해결과 어려운 해결) 가운데 1단계가 맡는 어려운 해결은 2개임
  - 마지막 정원에 2명이 동시에 들어감: DB 유일성 제약(PRD_step1 4장, DB 테이블)
  - DB(Supabase)가 일시정지되지 않게 함: 외부 예약 서비스로 매일 DB에 질의를 보냄(PRD_step1 7장, DB 일시정지 방지)
- 키 관리와 화면 `key` 규칙은 감점이 크므로(공고 6.3절 7번, 8번, 15번) 처음부터 지킴

## 2. 전제와 용어

- 이 문서에서 "공고"는 `중간과제 공고.pdf`를 가리킴. 절 번호는 "공고 2.7절(화면 이름 표)"처럼 문서 이름과 주제를 함께 씀
- 요청한 사람이 정한 사항
  - 이 앱의 테이블 이름은 모두 `tf_mp_`로 시작함. 같은 DB에 다른 앱의 `tf_` 테이블이 이미 있기 때문임. `tf_mp_`는 공고 6.3절(감점) 13번의 "`tf_`로 시작" 조건도 만족함
  - OpenRouter 모델 3개는 PRD_step3 5.1절(모델 3개)에서 확정함
  - 공고 3장(기능별 쉬운 해결과 어려운 해결) 표의 기능은 모두 어려운 해결로 만듦
  - 화면 `key`는 공고 2.7절(화면 이름 표)을 그대로 따름

| 용어 | 뜻 |
|---|---|
| 승인, 대기, 거절, 막힘 | 공고 2.4절(지원과 투표)의 결과 4가지. 막힘은 지원을 접수하지 않은 것이고 DB에 기록하지 않음 |
| 주 역할, 보조 역할 | 학생마다 주 역할 1개와 보조 역할 0~2개가 명단 CSV에 정해져 있음 |
| 필수 포함 역할 | 기획자와 웹 프로그래머. 서로 다른 학생이 1명씩 맡아야 함(공고 2.3절, 팀 규칙) |
| 상태(phase) | `open`(모집 중), `closed`(마감), `confirmed`(확정). 명단이 없으면 값이 없음 |

## 3. 기술 선택과 제약

### 3.1 사용 도구

| 용도 | 선택 | 까닭 |
|---|---|---|
| 화면 | Streamlit | 공고 4.4절(배포, 앱 잠자기, DB 일시정지)이 Streamlit Community Cloud 배포를 요구함 |
| DB 접속 | `psycopg` 3와 `psycopg_pool` | 연결을 한 번 만들어 재사용함(공고 4.2절, DB). 문서 확인함(context7: 풀은 `pool.connection()`으로 빌려 쓰고, 블록이 끝나면 커밋 또는 롤백함) |
| 비밀번호 해시 | `bcrypt` | 공고 6.3절(감점) 10번과 해시 설명이 `bcrypt`를 예로 듦 |
| 시험 | `pytest`와 Streamlit `AppTest` | `AppTest`는 key로 요소를 찾을 수 있음(context7로 확인함: `at.button(key=...)`) |

### 3.2 비밀 값

- 비밀 값은 3개: `OPENROUTER_API_KEY`, `DATABASE_URL`, `ADMIN_PASSWORD`
- 로컬에서는 `.env`(앱 파일과 같은 폴더), 배포에서는 Streamlit Secrets에서 읽음. `.env`는 `.gitignore`에 들어 있고 `.env.example`은 값 없이 추적함(저장소에서 확인함)
- 읽는 코드는 `mp/config.py` 1곳에 둠. 환경 변수를 먼저 보고 없으면 `st.secrets`를 봄
- 값을 화면, 로그, 오류 문구에 출력하지 않음(공고 6.3절, 감점 8번). 오류는 종류만 보여 줌. 예: "DB 연결 오류"
- 있는지 확인할 때는 "있음, 없음"만 출력함. `ADMIN_PASSWORD`가 없으면 앱은 관리자 계정을 만들지 않고 "ADMIN_PASSWORD 없음"만 안내함

### 3.3 DB 연결

- `.env`의 `DATABASE_URL`은 Supabase 연결 풀러 주소이고 포트는 6543임(확인함: 값 전체는 읽지 않고 스킴, `pooler` 포함 여부, 포트만 확인)
- 2026-10-30에 DB를 recipe4fridge 프로젝트로 옮겼음. 새 `DATABASE_URL`도 포트 6543의 연결 풀러임(확인함). 전체 시험 시간이 약 170초에서 852초로 늘었는데, 지역이 싱가포르인 것은 확인했으나 지연의 원인인지는 확인하지 않았음
- 6543 포트는 트랜잭션 풀링 방식이므로 접속 옵션에 `prepare_threshold=None`을 둠(미리 준비한 문장을 쓰지 않음). 동작은 구현 첫 단계에서 연결 시험으로 확인함(확인하지 않았음)
- 연결 풀은 `st.cache_resource`로 프로세스당 1개를 만듦. 크기는 최소 1개, 최대 5개로 시작함
- 한 화면을 그릴 때 질의 횟수와 연결 생성 횟수를 줄임(공고 4.2절, DB). 연결은 풀에서 빌려 쓰고 새로 만들지 않음

## 4. DB 테이블

### 4.1 이름과 파일

- 테이블 이름은 모두 `tf_mp_`로 시작함
- 테이블을 만드는 SQL은 저장소의 `schema.sql` 1개에 둠(공고 5절, DB 최소 참고안). Supabase 화면에서 직접 만든 SQL도 여기에 넣음
- `schema.sql`은 다시 실행해도 오류가 없게 `create table if not exists`를 씀. 실행은 `scripts/apply_schema.py`로 하고 앱이 시작할 때 자동 실행하지 않음
- 모든 테이블에서 RLS(행 수준 보안)를 켜고 정책은 만들지 않음. 각 `create table` 뒤에 `alter table ... enable row level security;`가 붙음(실제 `schema.sql` 참고). 앱은 `DATABASE_URL`로 소유자 역할에 직접 접속하므로 영향을 받지 않고, Supabase의 `anon`, `authenticated` 역할(공개 API 키)로는 어떤 행도 읽거나 쓸 수 없음. 2026-10-30 Supabase 점검에서 RLS가 꺼져 있다는 지적을 받아 추가함. 적용 전에는 `anon` 역할이 학생 9명(비밀번호 해시 열 포함)을 읽을 수 있었고, 적용 뒤에는 0명임(`set local role anon`으로 확인함)

### 4.2 1단계 테이블

```sql
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
```

- 지원과 투표 테이블은 PRD_step2 4장(지원)과 5장(투표)에서, AI 호출 기록 테이블은 PRD_step3 8장(기록)에서 같은 파일에 추가함

### 4.3 제약과 목적

| 제약 | 막는 일 | 공고의 근거 |
|---|---|---|
| `tf_mp_members` 기본 키 `(team_id, slot_no)` | 같은 정원에 2명이 들어감 | 공고 3장 표(마지막 자리에 두 명이 동시에 들어감), 공고 5절(DB 최소 참고안) |
| `tf_mp_members.student_id` 유일 | 한 학생이 2개 팀에 소속됨 | 공고 5절(DB 최소 참고안) |
| `slot_no between 1 and 4` | 5번째 정원 | 공고 5절(DB 최소 참고안) |
| `main_role`, `role`의 `check` | 6개 역할 밖의 값 | 공고 5절(DB 최소 참고안) |
| `is_admin = (main_role is null)` | 학생에게 역할이 없거나 관리자에게 역할이 있음 | 이 PRD의 판단 |
| `tf_mp_students.student_no` 유일 | 학번 중복 | 공고 5절(DB 최소 참고안) |
| RLS 켜고 정책 없음 | 공개 API 키(`anon`, `authenticated`)로 행을 읽거나 쓰는 일 | Supabase 보안 점검. 공고에는 없음 |

## 5. 기능 요구사항

### 5.1 관리자 계정

- 앱이 프로세스에서 처음 시작할 때 `student_no='admin'`인 계정을 만들거나 갱신함
- 이름은 `관리자`, `is_admin`은 참, `main_role`은 비움, 비밀번호 해시는 `ADMIN_PASSWORD`로 만듦
- 이미 있고 해시가 현재 `ADMIN_PASSWORD`와 맞으면 바꾸지 않음. 맞지 않으면 해시만 갱신함(공고 2.1절, 관리자 계정은 시작할 때 만들거나 갱신함)
- 명단을 다시 올려도 관리자 계정은 남김(PRD_step1 5.3절, 명단 올리기와 팀 만들기)

### 5.2 로그인

- 화면 요소와 `key`: `login_student_no`(`st.text_input`), `login_password`(`st.text_input`, 비밀번호 가림), `login_submit`(`st.form_submit_button`, `st.form` 안)
- `bcrypt.checkpw`가 참일 때만 로그인함. 학번과 비밀번호 중 무엇이 틀렸는지는 알리지 않음
- 성공하면 `result`에 `승인: 로그인함`, 실패하면 `막힘: 학번 또는 비밀번호가 맞지 않음`을 보여 줌
- 로그인한 사람은 `whoami` 컨테이너에 이름과 학번으로 보여 줌. 로그인하지 않았으면 "로그인하지 않음"
- 세션에는 계정의 `id`만 저장함. 관리자 여부는 세션 값을 믿지 않고 기능을 실행할 때마다 DB의 `is_admin`으로 확인함(공고 6.3절 11번, 학생 계정으로 관리자 기능을 쓸 수 있음)
- 계정이 DB에서 사라진 세션(명단을 새로 올린 경우)은 자동으로 로그아웃하고 "다시 로그인해야 함"을 보여 줌
- 로그아웃 단추(`logout`)를 둠. 공고 2.7절(화면 이름 표)에 없는 요소라서 이름은 자유임
- 72바이트를 넘는 비밀번호는 `bcrypt`가 처리하지 못할 수 있으므로 같은 `막힘` 안내로 처리함(`bcrypt` 판에 따라 오류가 날 수 있음. 구현할 때 확인함)

### 5.3 명단 올리기와 팀 만들기

- 관리자만 쓸 수 있음. 서비스 함수가 DB의 `is_admin`을 확인하고, 아니면 `막힘: 관리자만 할 수 있음`
- 화면 요소와 `key`: `admin_roster_file`(`st.file_uploader`, csv), `admin_team_count`(`st.number_input`, 최소 1, 기본 3), `admin_start`(`st.button`)
- CSV 형식(공고 2.6절, 명단 올리기): UTF-8이고 BOM이 있어도 읽음(`utf-8-sig`). 연습용 CSV 3개는 모두 BOM이 있음(확인함: 앞 3바이트 `ef bb bf`). 행 수는 쉬움 8명, 중간 12명, 어려움 16명임(확인함)
- 열은 `student_no,name,main_role,sub_roles` 4개. `sub_roles`는 `;`로 구분하고 없으면 빈 값임
- 검증 규칙(하나라도 어기면 아무것도 바꾸지 않고 `막힘: 이유`)

| 검사 | 막힘 안내 예 |
|---|---|
| 파일을 올리지 않음 | `막힘: 명단 CSV 파일을 올리지 않음` |
| 머리글이 4개 열과 다름 | `막힘: 열이 student_no,name,main_role,sub_roles가 아님` |
| 행의 열 수가 4개가 아님 | `막힘: 3행의 열 수가 4개가 아님` |
| 학번이나 이름이 빔 | `막힘: 5행의 학번이 비어 있음` |
| 학번 중복, 또는 학번이 `admin` | `막힘: 학번 2026101이 중복됨` |
| 역할이 6개 밖의 값 | `막힘: 4행의 역할 값이 올바르지 않음` |
| 보조 역할이 3개 이상 | `막힘: 4행의 보조 역할이 3개 이상임` |

- 역할 문자열은 공백을 정리해 비교함(여러 칸 공백을 1칸으로). 공고의 예시가 이중 공백으로 인쇄되어 있어서 방어함. 보조 역할이 주 역할과 같으면 중복을 제거해 받아들임(공고에 규정이 없어 정한 기본값임)
- 초기화는 1개 트랜잭션으로 함. 중간에 실패하면 이전 상태를 유지함(공고 2.6절)
  1. `tf_mp_votes`, `tf_mp_applications`, `tf_mp_members`, `tf_mp_teams`를 비움
  2. `is_admin`이 거짓인 학생을 지움(보조 역할은 `cascade`로 함께 지워짐)
  3. `tf_mp_settings`의 `phase`, `proposal`, `assign_status`를 지우고 `phase='open'`을 넣음. `proposal`과 `assign_status`는 PRD_step3 6장(AI 대기 중 화면)이 저장하는 값이며, 앞 시나리오의 배정 안내가 남지 않게 함
  4. 팀 `팀1`~`팀N`을 만듦(`team_no`는 1~N, 이 번호가 `team_{n}`의 n임)
  5. 학생과 보조 역할을 넣음. 비밀번호는 모두 `1234`를 `bcrypt`(rounds 10)로 해시해 학생마다 따로 저장함(공고 2.2절)
- 성공하면 `result`에 `승인: 학생 8명과 빈 팀 3개로 처음 상태를 만듦` 같은 안내를 보여 줌

### 5.4 1단계 화면

- 로그인 전: 로그인 폼, `whoami`, `result`
- 학생: `whoami`, `result`, 팀 목록. 자기 팀의 이름 옆에 `내 팀`을 붙이고, 팀이 없으면 `아직 팀이 없음`을 보여 줌(공고 2.8절, 학생 화면)
- 관리자: `whoami`, `result`, 명단 올리기 영역, 팀 목록, `unassigned`(팀이 없는 학생의 이름과 역할)
- 팀 하나는 `st.container(key="team_{n}")`에 팀 이름, 인원(`2/4`), 팀원(이름, 주 역할, 보조 역할)을 보여 줌. 팀원이 없으면 `팀원 없음`
- `st.container`의 `key` 지정은 공고 2.7절(화면 이름 표)이 전제하는 방식임. 설치한 Streamlit 판에서 지원하는지는 구현 첫 단계에서 확인함(문서 질의로는 직접 확인하지 못했음)
- 화면의 자동 갱신은 1단계에 없음. 다른 사람의 변경 보기는 PRD_step2 8장(다른 사람의 변경 보기)에서 구현함

## 6. 화면 `key` 표 (1단계 요소)

| 화면 요소 | Streamlit 요소 | key |
|---|---|---|
| 학번 입력칸 | `st.text_input` | `login_student_no` |
| 비밀번호 입력칸 | `st.text_input` | `login_password` |
| 로그인 단추 | `st.form_submit_button` | `login_submit` |
| 로그인한 사람 표시 | `st.container` | `whoami` |
| 단추를 누른 결과 안내 | `st.container` | `result` |
| 팀 하나의 표시 | `st.container` | `team_1`, `team_2`, … |
| 명단 CSV 올리기 | `st.file_uploader` | `admin_roster_file` |
| 팀 수 | `st.number_input` | `admin_team_count` |
| 명단으로 처음 상태 만들기 | `st.button` | `admin_start` |
| 팀이 없는 학생 표시 | `st.container` | `unassigned` |

- 한글 key는 쓰지 않음. `result`의 첫 단어는 승인, 대기, 거절, 막힘 중 하나임(공고 2.7절)

## 7. DB 일시정지 방지 (3장 표의 어려운 해결)

- 무엇을 함: 외부 예약 서비스가 매일 1번 DB에 질의를 보냄. 공고는 1주일 동안 요청이 적으면 일시정지된다고 설명함(공고 4.4절, 배포와 앱 잠자기와 DB 일시정지)
- 방법: GitHub Actions의 예약 실행(`.github/workflows/keepalive.yml`, 매일 1회)이 `scripts/keepalive.py`를 실행해 `select count(*) from tf_mp_settings` 정도의 가벼운 질의를 보냄
- `DATABASE_URL`은 저장소의 GitHub Secrets에 등록함. 키 입력은 사람이 직접 해야 하므로 Claude가 대신 입력하지 않음. 워크플로 파일에는 값을 쓰지 않고 로그에도 출력하지 않음
- 저장소가 비공개여도 예약 실행은 동작함(확인하지 않았음: 배포 뒤 첫 실행 기록으로 확인함)
- 마감(11/2 23:59) 뒤 커밋은 감점이므로(공고 6.3절 1번) 이 파일은 마감 전에 커밋하고 실행 기록을 확인함
- 보조 수단: 11/2에 배포한 앱으로 로그인해 명단을 올리고 지원과 투표를 몇 번 해 봄(앱을 쓰는 것이 곧 DB 요청임)

## 8. 시험

| 번호 | 시험 | 방법 | 통과 기준 |
|---|---|---|---|
| 1 | `schema.sql` 2회 실행 | `scripts/apply_schema.py` 2번 | 오류 없음, 테이블 5개 |
| 2 | 제약 | SQL로 직접 넣어 봄 | `slot_no=5`, 같은 학생 2개 팀, 같은 정원 2번, 역할 오류, 학번 중복이 모두 거부됨 |
| 3 | 마지막 정원 동시 | 스레드 2개가 같은 `(team_id, slot_no)`에 삽입 | 1개만 성공함 |
| 4 | CSV 검증 | `pytest` | PRD_step1 5.3절(명단 올리기와 팀 만들기)의 검증 표 7개 행이 각각 해당 안내로 막힘. BOM 있음과 없음 모두 읽음 |
| 5 | 연습용 CSV 3개 | 관리자로 올림 | 학생 8, 12, 16명과 팀 3, 4, 4개가 만들어짐. 학생이 `1234`로 로그인됨 |
| 6 | 로그인 | `AppTest` | 비밀번호가 틀리면 막힘, 맞으면 승인. 학번만으로는 로그인되지 않음 |
| 7 | 권한 | 학생 계정으로 `admin_start` 서비스 호출 | `막힘: 관리자만 할 수 있음`이고 DB가 그대로임 |
| 8 | 다시 올리기 | 같은 CSV를 2번 올림 | 관리자 계정이 남고 팀과 학생이 초기 상태임 |
| 9 | 키 노출 | 소스와 화면에서 `DATABASE_URL`, `OPENROUTER_API_KEY` 값 검색 | 코드에 값이 없고 화면 텍스트에 `postgresql://`와 `sk-or-`가 없음 |
| 10 | key 존재 | `AppTest` 또는 브라우저 | PRD_step1 6장(화면 key 표)의 key가 해당 화면에 모두 있음 |
| 11 | 일시정지 방지 | 예약 실행 기록 | 배포 뒤 첫 실행이 성공함(미룸: 배포 뒤 확인 항목으로 구현 계획에 올림) |


## 9. 완료 기준

- PRD_step1 8장(시험)의 시험 1~10이 통과함. 시험 11은 배포 뒤에 확인함
- 코드와 `schema.sql`에 비밀 값이 없고 `git status`에 `.env`가 나타나지 않음
- 1단계 완료를 배포까지 마친 것으로 말하지 않음. 배포 뒤 확인은 구현 계획 4.5절(배포와 제출)에 있음

## 10. 정한 기본값과 확인 필요

| 항목 | 기본값 | 확인 필요 여부 |
|---|---|---|
| 팀 수 입력 범위 | 1 이상 | 공고는 3~4개 팀을 예고함(공고 6.3절 8번). 제한하지 않음 |
| 보조 역할이 주 역할과 같은 경우 | 중복 제거 후 받아들임 | 공고에 규정 없음 |
| `schema.sql` 실행 시점 | 사람이 `apply_schema.py`로 1번 실행 | 앱 시작 때 자동 실행으로 바꿀지 |
| `st.container(key=)` 지원 | 지원한다고 가정 | 구현 첫 단계에서 확인 |
