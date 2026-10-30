# 2026-10-30 21:58 KST
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "tests" / "data"


import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def remove_fake_ai_log_rows():
    """시험이 tf_mp_ai_logs에 남긴 가짜 모델 행(fake/..., m1:free 같은 이름)을 시험이 끝난 뒤 지움

    이 기록은 README의 AI 호출 실패 사례 근거로 쓰이므로 실제 모델 행만 남겨야 함
    """
    yield
    try:
        from mp.config import get_secret
        from mp.db import make_pool

        url = get_secret("DATABASE_URL")
        if not url:
            return
        pool = make_pool(url, max_size=1)
        with pool.connection() as conn:
            if conn.execute("select to_regclass('tf_mp_ai_logs')").fetchone()[0] is not None:
                conn.execute("delete from tf_mp_ai_logs where model like 'fake/%' or model ~ '^m[0-9]:free$'")
        pool.close()
    except Exception:
        pass
