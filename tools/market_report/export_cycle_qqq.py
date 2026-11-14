#!/usr/bin/env python3
"""QQQ 사이클 추적 데이터 -> <DATA>/cycle_qqq.json

2018년 하반기(고점 이후 조정 -> 12월 저점 -> 이듬해 4월 고점 회복) 경로와, 2026년 10월 고점 이후 QQQ 경로를
"고점 이후 거래일 수"를 가로축으로 겹쳐 그리기 위한 데이터를 만든다. 종가는 yfinance(QQQ, 배당 미조정).

  - ref : 2018~19 경로. 2018-08-29 종가 = 100, 2018-10-03 부터(= 2026 고점일과 같은 0일차) END_DAY 일차까지
  - cur : 2026~27 경로. 2026-10-06 종가 = 100, 오늘까지 (END_DAY 를 넘으면 더 늘리지 않는다)
  - cal : 0..END_DAY 일차에 대응하는 2026~27 미국 거래일(휴장일 반영) — 아직 오지 않은 날짜 포함
실패하면 기존 파일을 그대로 두고 종료 코드 1로 끝난다(워크플로우에서는 실패해도 이어서 진행).
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    yf = None

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ["MR_DATA_DIR"]).resolve() if os.environ.get("MR_DATA_DIR") else ROOT / "docs" / "data"
OUT = DATA / "cycle_qqq.json"
KST = dt.timezone(dt.timedelta(hours=9))

SYMBOL = "QQQ"
CUR_PEAK = "2026-10-06"      # 2026 고점일(= 0일차, 값 100)
REF_PEAK = "2018-08-29"      # 2018 고점일(값 100 기준)
REF_START = "2018-10-03"     # 2018 경로의 0일차 (고점 직후 급락이 시작된 날)
END_DAY = 137                # 추적 종료: 고점 후 137거래일 = 2027-04-23
# 해당 일차에 대응해야 하는 날짜 — 휴장일 목록이 어긋났는지 확인하는 용도(경고만)
CAL_EXPECT = {20: "2026-11-03", 40: "2026-12-02", 56: "2026-12-24", 80: "2027-02-01", 100: "2027-03-02", 120: "2027-03-31", 137: "2027-04-23"}  # 120일차: 3/26 성금요일 휴장 반영
# NYSE 휴장일 (2026 하반기 ~ 2027)
HOLIDAYS = {
    "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
    "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}
FOMC_CUR = ["2026-12-09"]    # 2026 FOMC (결정일)
FOMC_REF = ["2018-12-19"]    # 2018 FOMC
REF_EVENTS = [("2018-11-07", "선거 후 반등", "above"), ("2019-01-04", "파월 선회", "right")]


def log(msg):
    print("[cycle_qqq] " + msg, file=sys.stderr)


def fetch(start, end):
    """-> (날짜 ISO 리스트, 종가 리스트). 아직 마감 전인 오늘 봉은 뺀다."""
    df = yf.Ticker(SYMBOL).history(start=start, end=end, auto_adjust=False)
    df = df.dropna(subset=["Close"])
    dates = [d.date().isoformat() for d in df.index]
    closes = [float(c) for c in df["Close"]]
    if dates:
        now = dt.datetime.now(df.index.tz)  # 거래소(뉴욕) 현지 시각
        if dates[-1] == now.date().isoformat() and now.time() < dt.time(16, 5):
            dates.pop(); closes.pop()
    return dates, closes


def trading_calendar(start_iso, n):
    d = dt.date.fromisoformat(start_iso)
    out = []
    while len(out) <= n:
        if d.weekday() < 5 and d.isoformat() not in HOLIDAYS:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def md(iso):
    return f"{int(iso[5:7])}/{int(iso[8:10])}"


def path(dates, closes, start, base_date):
    base = closes[dates.index(base_date)]
    i0 = dates.index(start)
    ds, cs = dates[i0:i0 + END_DAY + 1], closes[i0:i0 + END_DAY + 1]
    return ds, [round(c / base * 100, 2) for c in cs], [round(c, 2) for c in cs]


def main():
    if yf is None:
        log("yfinance 없음 - 기존 파일 유지")
        return 1
    today = dt.datetime.now(KST).date()
    try:
        rd, rc = fetch("2018-08-20", "2019-06-15")
        cd, cc = fetch("2026-09-20", (today + dt.timedelta(days=2)).isoformat())
        r_dates, r_val, r_close = path(rd, rc, REF_START, REF_PEAK)
        c_dates, c_val, c_close = path(cd, cc, CUR_PEAK, CUR_PEAK)
    except Exception as e:  # 네트워크·데이터 누락
        log(f"수집 실패: {e!r} - 기존 파일 유지")
        return 1
    if len(r_dates) < END_DAY + 1:
        log(f"2018 경로가 {END_DAY}일차까지 없음({len(r_dates)}) - 기존 파일 유지")
        return 1

    cal = trading_calendar(CUR_PEAK, END_DAY)
    for k, v in CAL_EXPECT.items():
        if cal[k] != v:
            log(f"경고: 거래일 달력 불일치 {k}일차 {cal[k]} != {v} (휴장일 목록 확인 필요)")
    for i, d in enumerate(c_dates):
        if cal[i] != d:
            log(f"경고: 실제 거래일 {d} != 달력 {cal[i]} ({i}일차)")
            break

    # 표시용 지점(라벨): ref = 이벤트·저점·고점 회복, cur = 지금까지의 저점·현재
    marks = []
    lo = min(range(len(r_val)), key=lambda i: r_val[i])
    for date, label, pos in REF_EVENTS:
        if date in r_dates:
            i = r_dates.index(date)
            marks.append({"s": "ref", "day": i, "v": r_val[i], "date": date, "label": label, "pos": pos})
    marks.append({"s": "ref", "day": lo, "v": r_val[lo], "date": r_dates[lo], "pos": "right",
                  "label": f"{md(r_dates[lo])} 저점 {r_val[lo]:.1f} ({r_val[lo] - 100:+.0f}%)"})
    rec = next((i for i in range(lo, len(r_val)) if r_val[i] >= 100), None)
    if rec is not None:
        marks.append({"s": "ref", "day": rec, "v": r_val[rec], "date": r_dates[rec], "label": "고점 회복", "pos": "above"})
    last = len(c_val) - 1
    clo = min(range(len(c_val)), key=lambda i: c_val[i])
    if clo != last and clo > 0:
        marks.append({"s": "cur", "day": clo, "v": c_val[clo], "date": c_dates[clo], "label": f"{md(c_dates[clo])} {c_val[clo]:.1f}", "pos": "below"})
    marks.append({"s": "cur", "day": last, "v": c_val[last], "date": c_dates[last], "label": f"현재 {c_val[last]:.1f}", "pos": "right"})

    fomc = {
        "cur": [{"date": d, "day": cal.index(d)} for d in FOMC_CUR if d in cal],
        "ref": [{"date": d, "day": r_dates.index(d)} for d in FOMC_REF if d in r_dates],
    }
    out = {
        "version": 1,
        "generatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "symbol": SYMBOL, "endDay": END_DAY, "endDate": cal[END_DAY],
        "cur": {"peak": CUR_PEAK, "peakClose": cc[cd.index(CUR_PEAK)], "dates": c_dates, "v": c_val, "close": c_close},
        "ref": {"peak": REF_PEAK, "peakClose": rc[rd.index(REF_PEAK)], "start": REF_START, "dates": r_dates, "v": r_val},
        "cal": cal, "fomc": fomc, "marks": marks,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    log(f"저장 {OUT} (cur {len(c_val)}일 · ref {len(r_val)}일 · {c_dates[-1]} 현재 {c_val[-1]:.1f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
