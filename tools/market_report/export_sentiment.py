#!/usr/bin/env python3
"""시장 심리 지표 4종 -> <DATA>/sentiment.json  (QQQ 사이클 탭 하단에 표시)

  - cnn    : CNN 공포·탐욕지수 (production.dataviz.cnn.io 공개 JSON, 약 1년 일별 이력 포함)
  - semi   : 반도체 공포·탐욕지수 — 공식 지수가 없어 필라델피아 반도체지수(^SOX)로 "자체 산출"
             (CNN 방식을 응용한 5개 항목의 평균, 각 항목은 최근 1년 내 백분위 0~100)
  - crypto : 크립토 공포·탐욕지수 (alternative.me 공개 API)
  - vix    : VIX (yfinance ^VIX)
각 지표는 따로 수집하며, 하나가 실패하면 기존 파일에 있던 그 지표만 그대로 남긴다(전부 실패하면 종료 코드 1).
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

try:
    import yfinance as yf
except ImportError:
    yf = None

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ["MR_DATA_DIR"]).resolve() if os.environ.get("MR_DATA_DIR") else ROOT / "docs" / "data"
OUT = DATA / "sentiment.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Referer": "https://edition.cnn.com/", "Accept": "application/json"}
HIST = 250  # 차트용 최근 N개 일별 값


def log(msg):
    print("[sentiment] " + msg, file=sys.stderr)


def rating(score):
    """CNN 기준 구간 -> 영문 키"""
    if score < 25: return "extreme_fear"
    if score < 45: return "fear"
    if score < 55: return "neutral"
    if score < 75: return "greed"
    return "extreme_greed"


def r1(v):
    return None if v is None else round(float(v), 1)


# ---------- CNN ----------
def fetch_cnn():
    r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers=UA, timeout=25)
    r.raise_for_status()
    j = r.json()
    fg = j["fear_and_greed"]
    hist = []
    for p in j["fear_and_greed_historical"]["data"]:
        d = dt.datetime.fromtimestamp(p["x"] / 1000, dt.timezone.utc).strftime("%Y%m%d")
        if hist and hist[-1][0] == d:
            hist[-1][1] = r1(p["y"])
        else:
            hist.append([d, r1(p["y"])])
    hist = hist[-HIST:]
    score = float(fg["score"])
    return {
        "score": r1(score), "rating": rating(score), "asOf": fg.get("timestamp"),
        "prev": {"day": r1(fg.get("previous_close")), "week": r1(fg.get("previous_1_week")),
                 "month": r1(fg.get("previous_1_month")), "year": r1(fg.get("previous_1_year"))},
        "hist": hist,
    }


# ---------- 크립토 ----------
def fetch_crypto():
    r = requests.get("https://api.alternative.me/fng/?limit=380&format=json", timeout=25)
    r.raise_for_status()
    rows = r.json()["data"]  # 최신순
    pts = [(dt.datetime.fromtimestamp(int(x["timestamp"]), dt.timezone.utc).strftime("%Y%m%d"), float(x["value"])) for x in rows]
    pts.sort()
    full = [[d, r1(v)] for d, v in pts]
    hist = full[-365:]  # 크립토는 주말도 값이 있어 365일치
    vals = [v for _, v in full]
    score = vals[-1]

    def back(n):
        return vals[-1 - n] if len(vals) > n else None
    return {
        "score": r1(score), "rating": rating(score), "asOf": hist[-1][0],
        "prev": {"day": back(1), "week": back(7), "month": back(30), "year": back(364)},
        "hist": hist,
    }


# ---------- VIX ----------
def fetch_vix():
    df = yf.Ticker("^VIX").history(period="2y", auto_adjust=False).dropna(subset=["Close"])
    dates = [d.strftime("%Y%m%d") for d in df.index]
    vals = [float(c) for c in df["Close"]]
    last = vals[-1]
    year = vals[-252:]

    def back(n):
        return r1(vals[-1 - n]) if len(vals) > n else None
    return {
        "value": r1(last), "asOf": dates[-1], "prevClose": back(1),
        "chg": r1(last - vals[-2]), "pct": r1((last / vals[-2] - 1) * 100),
        "week": back(5), "month": back(21), "year": back(252),
        "hi52": r1(max(year)), "lo52": r1(min(year)),
        "hist": [[d, r1(v)] for d, v in zip(dates, vals)][-HIST:],
    }


# ---------- 반도체 (자체 산출) ----------
def pct_rank(series, window=252):
    """각 시점의 값이 직전 window 개 값(자신 포함) 중 몇 % 위치인지(0~100)"""
    return series.rolling(window, min_periods=int(window * 0.6)).apply(
        lambda w: (w[:-1] < w[-1]).sum() / max(len(w) - 1, 1) * 100.0, raw=True)


def fetch_semi():
    import pandas as pd
    sox = yf.Ticker("^SOX").history(period="4y", auto_adjust=False).dropna(subset=["Close"])["Close"]
    qqq = yf.Ticker("QQQ").history(period="4y", auto_adjust=False).dropna(subset=["Close"])["Close"]
    sox.index = sox.index.tz_localize(None).normalize()
    qqq.index = qqq.index.tz_localize(None).normalize()
    qqq = qqq.reindex(sox.index).ffill()

    ma125 = sox.rolling(125).mean()
    mom = sox / ma125 - 1                                   # 1) 모멘텀: 125일 이동평균 대비
    hi, lo = sox.rolling(252, min_periods=150).max(), sox.rolling(252, min_periods=150).min()
    strength = (sox - lo) / (hi - lo) * 100                 # 2) 가격 강도: 52주 범위 내 위치 (그대로 0~100)
    delta = sox.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn)                         # 3) RSI(14) (그대로 0~100)
    vol = sox.pct_change().rolling(20).std()                # 4) 변동성: 20일 실현변동성 (높을수록 공포 -> 반전)
    rel = sox.pct_change(20) - qqq.pct_change(20)           # 5) 상대강도: 20일 수익률 - QQQ

    parts = {
        "mom": ("모멘텀", "125일선 대비", pct_rank(mom), mom),
        "strength": ("가격 강도", "52주 범위 내 위치", strength, strength),
        "rsi": ("RSI(14)", "과매수·과매도", rsi, rsi),
        "vol": ("변동성", "20일 변동성(낮을수록 탐욕)", 100 - pct_rank(vol), vol),
        "rel": ("상대강도", "20일 수익률 − QQQ", pct_rank(rel), rel),
    }
    df = pd.concat({k: v[2] for k, v in parts.items()}, axis=1).dropna()
    score = df.mean(axis=1)
    full = [[d.strftime("%Y%m%d"), r1(v)] for d, v in score.items()]
    hist = full[-HIST:]
    vals = [v for _, v in full]
    cur = float(score.iloc[-1])

    def back(n):
        return vals[-1 - n] if len(vals) > n else None

    def raw(k, v):
        if k in ("mom",): return "%+.1f%%" % (v * 100)
        if k == "vol": return "일 %.1f%%" % (v * 100)
        if k == "rel": return "%+.1f%%p" % (v * 100)
        return "%.0f" % v
    out_parts = []
    for k, (name, desc, sc, rw) in parts.items():
        out_parts.append({"name": name, "desc": desc, "score": r1(df[k].iloc[-1]), "raw": raw(k, float(rw.loc[df.index[-1]]))})
    return {
        "score": r1(cur), "rating": rating(cur), "asOf": hist[-1][0], "symbol": "^SOX",
        "price": r1(sox.iloc[-1]), "parts": out_parts,
        "prev": {"day": back(1), "week": back(5), "month": back(21), "year": back(252)},
        "hist": hist,
    }


def main():
    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            old = {}
    jobs = [("cnn", fetch_cnn, False), ("semi", fetch_semi, True), ("crypto", fetch_crypto, False), ("vix", fetch_vix, True)]
    res, ok = {}, 0
    for key, fn, need_yf in jobs:
        try:
            if need_yf and yf is None:
                raise RuntimeError("yfinance 없음")
            res[key] = fn()
            ok += 1
            log("%s OK" % key)
        except Exception as e:  # 한 지표 실패가 나머지를 막지 않는다
            log("%s 실패: %s" % (key, e))
            if old.get(key):
                res[key] = old[key]
                res[key]["stale"] = True
    if not ok:
        log("모든 지표 수집 실패 - 기존 파일 유지")
        return 1
    res["version"] = 1
    res["generatedAt"] = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log("wrote %s (%d bytes)" % (OUT, OUT.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
