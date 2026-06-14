"""
로또 당첨번호 수집 — 전체 역사(1회~최신회) 수집
초기 실행 시 수 분 소요 (1200+회), 이후 증분 업데이트
"""
import requests, json, time
from pathlib import Path

DIR = Path(__file__).parent / "data"
DIR.mkdir(parents=True, exist_ok=True)

HISTORY_PATH = DIR / "lotto_history.json"

# 기존 데이터 로드 (증분 업데이트 지원)
existing = {}
if HISTORY_PATH.exists():
    prev = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    for r in prev.get("data", []):
        existing[r["draw"]] = r

latest = requests.get(
    "https://smok95.github.io/lotto/results/latest.json", timeout=10
).json()["draw_no"]

print(f"최신 회차: {latest}회 | 기존 보유: {len(existing)}회")

new_count = 0
for n in range(latest, 0, -1):
    if n in existing:
        continue  # 이미 보유한 회차 스킵
    try:
        d = requests.get(
            f"https://smok95.github.io/lotto/results/{n}.json", timeout=10
        ).json()
        existing[n] = {
            "draw":    d["draw_no"],
            "date":    d["date"][:10],
            "numbers": sorted(d["numbers"]),
            "bonus":   d["bonus_no"],
        }
        new_count += 1
        if new_count % 100 == 0:
            print(f"  수집 중... {n}회 완료")
        time.sleep(0.03)
    except Exception as e:
        print(f"  오류 {n}회: {e}")

records = sorted(existing.values(), key=lambda x: -x["draw"])
json.dump(
    {
        "last_draw":     records[0]["draw"],
        "total_records": len(records),
        "data":          records,
    },
    open(HISTORY_PATH, "w", encoding="utf-8"),
    ensure_ascii=False, indent=2,
)
print(f"수집 완료: 총 {len(records)}회 (신규 {new_count}회, 최신={records[0]['draw']}회)")
