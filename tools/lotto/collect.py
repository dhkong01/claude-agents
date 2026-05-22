import requests, json, time
from pathlib import Path

DIR = Path(__file__).parent / "data"
DIR.mkdir(parents=True, exist_ok=True)

latest = requests.get("https://smok95.github.io/lotto/results/latest.json", timeout=10).json()["draw_no"]
records = []
for n in range(latest, max(latest - 200, 0), -1):
    try:
        d = requests.get(f"https://smok95.github.io/lotto/results/{n}.json", timeout=10).json()
        records.append({"draw": d["draw_no"], "date": d["date"][:10],
                        "numbers": sorted(d["numbers"]), "bonus": d["bonus_no"]})
        time.sleep(0.05)
    except:
        pass

records.sort(key=lambda x: -x["draw"])
json.dump({"last_draw": records[0]["draw"], "total_records": len(records), "data": records},
          open(DIR / "lotto_history.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"수집: {len(records)}회 (최신={records[0]['draw']}회)")