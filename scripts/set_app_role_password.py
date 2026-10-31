# 2026-10-31 15:25 KST
"""앱 전용 역할 tf_mp_app의 비밀번호를 무작위로 새로 정하고 .env를 바꿈. 비밀 값은 출력하지 않음

먼저 schema.sql을 적용해 역할을 만들어 둬야 함. 이 스크립트가 하는 일:
1. DATABASE_ADMIN_URL(없으면 DATABASE_URL)의 큰 권한 역할로 접속해 tf_mp_app의 비밀번호를 바꿈
2. .env의 DATABASE_ADMIN_URL에 큰 권한 주소를 남기고, DATABASE_URL을 tf_mp_app의 주소로 바꿈
공용 풀러에서는 사용자 이름이 "역할.프로젝트번호" 꼴이므로 기존 주소의 "postgres.프로젝트번호"에서 번호를 가져옴
다시 실행하면 비밀번호가 다시 바뀜(Streamlit Secrets와 GitHub Secrets도 새로 맞춰야 함)
"""
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from dotenv import dotenv_values  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.conninfo import conninfo_to_dict  # noqa: E402

ROLE = "tf_mp_app"
ENV = ROOT / ".env"


def app_url(admin_url, password):
    d = conninfo_to_dict(admin_url)
    user = d["user"]
    ref = user.split(".", 1)[1] if "." in user else None
    login = f"{ROLE}.{ref}" if ref else ROLE
    return f"postgresql://{quote(login, safe='.')}:{quote(password, safe='')}@{d['host']}:{d.get('port', 5432)}/{d.get('dbname', 'postgres')}"


def set_env(lines, name, value):
    out, done = [], False
    for line in lines:
        if line.split("=", 1)[0].strip() == name:
            out.append(f"{name}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{name}={value}")
    return out


def main():
    values = dotenv_values(ENV)
    admin_url = values.get("DATABASE_ADMIN_URL") or values.get("DATABASE_URL")
    if not admin_url:
        print("DATABASE_ADMIN_URL과 DATABASE_URL이 모두 없음")
        return 1
    if conninfo_to_dict(admin_url)["user"].split(".")[0] == ROLE:
        print(f"{ENV.name}에 큰 권한 주소가 없음: DATABASE_ADMIN_URL을 먼저 채울 것")
        return 1
    password = secrets.token_urlsafe(32)
    try:
        with psycopg.connect(admin_url, prepare_threshold=None, connect_timeout=30, autocommit=True) as conn:
            if not conn.execute("select 1 from pg_roles where rolname = %s", (ROLE,)).fetchone():
                print(f"역할 {ROLE} 없음: schema.sql을 먼저 적용할 것")
                return 1
            conn.execute(sql.SQL("alter role {} with password {}").format(sql.Identifier(ROLE), sql.Literal(password)))
    except Exception as e:
        print("비밀번호 변경 실패:", type(e).__name__)
        return 1
    lines = ENV.read_text(encoding="utf-8").splitlines()
    lines = set_env(lines, "DATABASE_ADMIN_URL", admin_url)
    lines = set_env(lines, "DATABASE_URL", app_url(admin_url, password))
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{ROLE}의 비밀번호를 바꾸고 .env의 DATABASE_URL과 DATABASE_ADMIN_URL을 고침")
    return 0


if __name__ == "__main__":
    sys.exit(main())
