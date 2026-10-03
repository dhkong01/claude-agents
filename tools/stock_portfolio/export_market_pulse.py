"""
시장동향 데이터 내보내기 — cache/market_pulse.json + news_app의 대가 인사이트를
병합해 docs/data/market_pulse.json 생성 (PWA '시장동향' 탭에서 사용).
"""
import json
import sys
from pathlib import Path

BASE_DIR  = Path(__file__).parent
CACHE_DIR = BASE_DIR / "cache"
REPO_ROOT = BASE_DIR.parent.parent
DOCS_DATA = REPO_ROOT / "docs" / "data"
DOCS_DATA.mkdir(parents=True, exist_ok=True)

# 대가 인사이트는 별도 워크플로(news_daily)가 생성하는 news_app 캐시를 읽기만 한다
# (교차 디렉터리 읽기 — 쓰기는 하지 않으므로 두 워크플로의 커밋 충돌 없음).
GURU_CACHE = REPO_ROOT / "tools" / "news_app" / "cache" / "guru_insights.json"


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except Exception:
        return None


def export_market_pulse() -> bool:
    pulse = _read(CACHE_DIR / "market_pulse.json")
    if not pulse:
        print("[export] market_pulse.json 없음", file=sys.stderr)
        return False

    guru = _read(GURU_CACHE) or {}
    out = {
        **pulse,
        "guru_insights": guru.get("insights", []),
        "guru_date": guru.get("date"),
    }

    dest = DOCS_DATA / "market_pulse.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] market_pulse.json → {dest} (대가 인사이트 {len(out['guru_insights'])}건)")
    return True


if __name__ == "__main__":
    export_market_pulse()
