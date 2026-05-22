import json, numpy as np
from pathlib import Path
from scipy.special import softmax

DIR = Path(__file__).parent / "data"
records = json.load(open(DIR/"lotto_history.json", encoding="utf-8"))["data"]

all_nums = [n for r in records for n in r["numbers"]]
freq = {i: all_nums.count(i) for i in range(1,46)}
counts = np.array([freq[i] for i in range(1,46)], dtype=float)
weights = softmax((counts - counts.mean()) / (counts.std()+1e-8))
w_dict = {str(i+1): round(float(weights[i]),6) for i in range(45)}

recent10 = [n for r in records[:10] for n in r["numbers"]]
recent20 = [n for r in records[:20] for n in r["numbers"]]
hot  = [i for i in range(1,46) if recent10.count(i) >= 3]
cold = [i for i in range(1,46) if i not in recent20]

bands = {"1-9":range(1,10),"10-19":range(10,20),"20-29":range(20,30),
         "30-39":range(30,40),"40-45":range(40,46)}
band_avg = {k: round(float(np.mean([sum(1 for n in r["numbers"] if n in v) for r in records])),2)
            for k,v in bands.items()}

odd_ratios = [sum(1 for n in r["numbers"] if n%2==1) for r in records]
best_odd = max(set(odd_ratios), key=odd_ratios.count)

out = {"based_on":len(records),"weights":w_dict,"hot":hot,"cold":cold,
       "band_avg":band_avg,"rec_odd":best_odd,"freq":freq}
json.dump(out, open(DIR/"lotto_analysis.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"분석 완료: hot={hot}, cold={cold[:5]}, 추천홀수={best_odd}")