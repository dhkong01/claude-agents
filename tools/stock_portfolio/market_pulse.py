"""
시장동향(마켓 펄스) — 주요 지수, 나스닥/S&P500 상승·하락 종목수, 거시경제 지표.
PWA '시장동향' 탭 데이터 소스. → cache/market_pulse.json
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from data_utils import CACHE_DIR, YF_SESSION, batch_download, get_ndx100_tickers, get_sp500_tickers, market_today
from macro_analyzer import analyze_macro

INDEX_TICKERS = {
    "nasdaq":   ("^IXIC",     "나스닥종합", "US"),
    "dow":      ("^DJI",      "다우존스",   "US"),
    "sp500":    ("^GSPC",     "S&P500",    "US"),
    "kospi":    ("^KS11",     "코스피",     "ASIA"),
    "kosdaq":   ("^KQ11",     "코스닥",     "ASIA"),
    "nikkei":   ("^N225",     "니케이225",  "ASIA"),
    "shanghai": ("000001.SS", "상해종합",   "ASIA"),
    "shenzhen": ("399001.SZ", "심천성분",   "ASIA"),
}


def _fetch_index(ticker: str) -> dict | None:
    import yfinance as yf

    for attempt in (1, 2, 3):
        try:
            hist = yf.Ticker(ticker, session=YF_SESSION).history(period="5d")
            close = hist["Close"].dropna()
            if len(close) >= 2:
                price, prev = float(close.iloc[-1]), float(close.iloc[-2])
                return {
                    "price": round(price, 2),
                    "change": round(price - prev, 2),
                    "change_pct": round((price / prev - 1) * 100, 2),
                }
            err = "데이터 2건 미만"
        except Exception as e:
            err = str(e)
        if attempt < 3:  # 레이트리밋은 잠깐 기다리면 풀리는 경우가 많다
            time.sleep(3 * attempt)
    print(f"[market_pulse] {ticker} 조회 실패(3회 시도): {err}", file=sys.stderr)
    return None


def _calc_mfi(ticker: str = "SPY", period: int = 14) -> float | None:
    """자금흐름지수(Money Flow Index) — 가격뿐 아니라 거래량까지 반영해
    시장에 돈이 들어오는지/빠지는지를 가늠하는 기술적 지표(0~100).
    S&P500 대표 ETF(SPY)의 OHLCV로 직접 계산 — 외부 API 불필요."""
    import yfinance as yf

    try:
        hist = yf.Ticker(ticker, session=YF_SESSION).history(period=f"{period * 3}d")
        if hist.empty or len(hist) < period + 1:
            return None
        typical = (hist["High"] + hist["Low"] + hist["Close"]) / 3
        raw_mf = typical * hist["Volume"]
        direction = typical.diff()
        pos_mf = raw_mf.where(direction > 0, 0.0).tail(period).sum()
        neg_mf = raw_mf.where(direction < 0, 0.0).tail(period).sum()
        if neg_mf == 0:
            return 100.0
        money_flow_ratio = pos_mf / neg_mf
        return round(100 - 100 / (1 + money_flow_ratio), 1)
    except Exception as e:
        print(f"[market_pulse] MFI({ticker}) 계산 실패: {e}", file=sys.stderr)
        return None


def _mfi_signal(mfi: float | None) -> str:
    if mfi is None:
        return ""
    if mfi >= 80:
        return "과열"
    if mfi <= 20:
        return "침체"
    return "중립"


MIN_BREADTH_COVERAGE = 0.8    # 유니버스의 80%도 못 받으면 레이트리밋 등으로 신뢰 불가 → 직전값 폴백
GOOD_BREADTH_COVERAGE = 0.95  # 이 이상 받으면 재시도 중단 (상장폐지 등 소수 종목은 원래 못 받음)
BREADTH_RETRY_WAITS = (0, 20, 45)  # 시도별 사전 대기(초) — 레이트리밋이 풀리길 기다렸다 미수신 종목만 재요청
MAX_FALLBACK_AGE_DAYS = 5     # 직전값 폴백은 이 일수까지만 — 오래된 값을 '현재'처럼 보여주지 않기 위함


def _load_prev_breadth(min_total: int, today: str) -> dict | None:
    """직전 실행의 cache/market_pulse.json에서 브레드스를 읽는다 — 당일 조회가
    (Yahoo Finance 레이트리밋 등으로) 사실상 실패했을 때 '총 1종목' 같은
    의미 없는 결과를 화면에 그대로 노출하는 대신 직전값을 유지하기 위한 폴백.
    과거 캐시 자체가 이미 같은 방식으로 깨져 있었을 수도 있으므로(예: 수정 전
    코드가 '총 1종목'을 그대로 저장) 동일한 최소 기준(min_total)으로 검증한다
    — 그렇지 않으면 깨진 값이 폴백을 통해 계속 재생산된다.
    기준일(as_of)이 MAX_FALLBACK_AGE_DAYS보다 오래됐으면 폴백하지 않는다."""
    try:
        prev = json.loads((CACHE_DIR / "market_pulse.json").read_text(encoding="utf-8"))
        b = prev.get("breadth")
        if not b or (b.get("total") or 0) < min_total:
            return None
        as_of = b.get("as_of") or prev.get("date")
        age = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(as_of, "%Y-%m-%d")).days
        if age > MAX_FALLBACK_AGE_DAYS:
            print(f"[market_pulse] 직전 브레드스가 {age}일 전({as_of}) — 폴백 사용 안 함", file=sys.stderr)
            return None
        return {**b, "as_of": as_of, "status": "stale_fallback"}
    except Exception:
        return None


def _collect_changes(tickers: list[str]) -> tuple[dict, str | None, int]:
    """전일 대비 가격변화를 종목별로 수집한다. 미수신 종목만 대기 후 재요청해 병합.
    batch_download는 청크 단위 실패를 삼키므로(레이트리밋), 한 번에 끝내지 않고 재시도한다."""
    changes: dict[str, float] = {}
    as_of: str | None = None
    pending = list(tickers)
    attempts = 0
    for attempt, wait in enumerate(BREADTH_RETRY_WAITS, 1):
        if not pending:
            break
        if wait:
            print(f"[market_pulse] 브레드스 미수신 {len(pending)}종목 — {wait}초 후 재시도", file=sys.stderr)
            time.sleep(wait)
        attempts = attempt
        prices = batch_download(pending, period="5d")
        if not prices.empty and prices.shape[0] >= 2:
            day = str(prices.index[-1].date())
            as_of = as_of or day
            if day == as_of:  # 시도 간 기준 거래일이 어긋난 데이터는 섞지 않는다
                for t, v in (prices.iloc[-1] - prices.iloc[-2]).dropna().items():
                    changes[t] = float(v)
            else:
                print(f"[market_pulse] 기준일 불일치({day} ≠ {as_of}) — 이번 시도 결과 제외", file=sys.stderr)
        pending = [t for t in pending if t not in changes]
        print(
            f"[market_pulse] 브레드스 시도 {attempt}/{len(BREADTH_RETRY_WAITS)}: "
            f"누적 {len(changes)}/{len(tickers)}종목 수신",
            file=sys.stderr,
        )
        if len(changes) >= len(tickers) * GOOD_BREADTH_COVERAGE:
            break
    return changes, as_of, attempts


def _calc_breadth(tickers: list[str]) -> dict | None:
    """S&P500+NASDAQ100 유니버스의 전일 대비 상승/하락/보합 종목수.
    Yahoo Finance가 공유 IP(GitHub Actions)를 레이트리밋하면 대부분의 티커가
    조용히 누락돼도 호출부는 예외 없이 '성공'으로 끝나 '총 1종목' 같은 깨진
    결과가 그대로 커밋되는 사고가 있었다 — 재시도 후에도 응답 비율이 너무
    낮으면 None을 반환해 호출부가 신뢰 불가로 판단하게 한다."""
    changes, as_of, attempts = _collect_changes(tickers)
    total = len(changes)
    coverage = total / len(tickers) if tickers else 0.0

    if total == 0 or coverage < MIN_BREADTH_COVERAGE:
        print(
            f"[market_pulse] 브레드스 응답 {total}/{len(tickers)}종목({coverage:.0%}) — "
            "Yahoo Finance 레이트리밋 의심, 신뢰 불가로 판단",
            file=sys.stderr,
        )
        return None

    advancers = sum(1 for v in changes.values() if v > 0)
    decliners = sum(1 for v in changes.values() if v < 0)
    unchanged = total - advancers - decliners
    return {
        "total": total,
        "advancers": advancers,
        "decliners": decliners,
        "unchanged": unchanged,
        "adv_pct": round(advancers / total * 100, 1),
        "coverage": round(coverage * 100, 1),
        "as_of": as_of,
        "attempts": attempts,
        "status": "ok" if coverage >= GOOD_BREADTH_COVERAGE else "partial",
    }


def health_warnings(result: dict) -> list[str]:
    """조용히 지나가기 쉬운 부분 실패를 한 줄 메시지 목록으로 정리 (GitHub ::warning:: 용)."""
    warns: list[str] = []
    missing_idx = [v[1] for k, v in INDEX_TICKERS.items() if k not in result.get("indices", {})]
    if missing_idx:
        warns.append(f"지수 {len(result.get('indices', {}))}/{len(INDEX_TICKERS)}개만 수집 — 누락: {', '.join(missing_idx)}")

    b = result.get("breadth", {})
    status = b.get("status")
    if status == "stale_fallback":
        warns.append(f"시장 체감도(브레드스) 조회 실패 → 직전값 유지 (기준일 {b.get('as_of')}, 총 {b.get('total')}종목)")
    elif status == "failed":
        warns.append("시장 체감도(브레드스) 조회 실패 + 사용할 직전값 없음 → 화면에 '데이터 없음' 표시")
    elif status == "partial":
        warns.append(f"시장 체감도(브레드스) 일부 종목만 수신 ({b.get('coverage')}%, 총 {b.get('total')}종목)")

    m = result.get("macro", {})
    missing_macro = [k for k in ("phase", "vix", "yield2y", "yield10y", "yield30y", "fear_greed", "mfi")
                     if m.get(k) in (None, "", "N/A")]
    if missing_macro:
        warns.append(f"경제지표 누락: {', '.join(missing_macro)}")
    return warns


def analyze_market_pulse() -> dict:
    today = market_today()

    indices: dict = {}
    for key, (ticker, label, region) in INDEX_TICKERS.items():
        data = _fetch_index(ticker)
        if data:
            data["label"] = label
            data["region"] = region
            indices[key] = data

    universe = list(dict.fromkeys(get_sp500_tickers() + get_ndx100_tickers()))
    breadth = _calc_breadth(universe)
    if breadth is None:
        breadth = _load_prev_breadth(min_total=int(len(universe) * MIN_BREADTH_COVERAGE), today=today)
        if breadth is not None:
            print(f"[market_pulse] 브레드스 직전값 유지 (기준일 {breadth['as_of']}, 총 {breadth['total']}종목)", file=sys.stderr)
        else:
            breadth = {"total": 0, "advancers": 0, "decliners": 0, "unchanged": 0, "adv_pct": None,
                       "as_of": None, "status": "failed"}
    breadth["universe"] = "S&P500+NASDAQ100"

    macro = analyze_macro()
    signals = macro.get("signals", {})

    mfi = _calc_mfi("SPY")

    result = {
        "date": today,
        "indices": indices,
        "breadth": breadth,
        "macro": {
            "phase":        macro.get("phase", ""),
            "m_score":      macro.get("m_score"),
            "vix":          signals.get("vix_level"),
            "volatility":   signals.get("volatility"),
            "fear_greed":        signals.get("fear_greed_score"),
            "fear_greed_rating": signals.get("fear_greed_rating"),
            "yield2y":      signals.get("yield2y"),
            "yield10y":     signals.get("yield10y"),
            "yield30y":     signals.get("yield30y"),
            "rate_env":     signals.get("rate_env"),
            "dollar_trend": signals.get("dollar_trend"),
            "market_trend": signals.get("market_trend"),
            "mfi":          mfi,
            "mfi_signal":   _mfi_signal(mfi),
        },
    }
    (CACHE_DIR / "market_pulse.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    pulse = analyze_market_pulse()
    print(
        f"[market_pulse] 지수 {len(pulse['indices'])}개 · "
        f"브레드스 {pulse['breadth']['advancers']}상승/{pulse['breadth']['decliners']}하락"
        f"(총 {pulse['breadth']['total']}, {pulse['breadth'].get('status')}) · 국면 {pulse['macro']['phase']}",
        flush=True,
    )
    # 부분 실패를 로그 속에 묻어두지 않고 워크플로 요약(Annotations)에 노출한다.
    # 추세추종 본 파이프라인을 막지 않도록 종료 코드는 0 유지.
    for msg in health_warnings(pulse):
        print(f"::warning::시장동향: {msg}", flush=True)
