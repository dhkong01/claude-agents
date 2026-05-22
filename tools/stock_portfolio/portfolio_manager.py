"""
Portfolio state management and quarterly rebalancing.
State persisted in portfolio.json.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

PORTFOLIO_PATH = Path(__file__).parent / "portfolio.json"


def load() -> dict:
    if PORTFOLIO_PATH.exists():
        return json.loads(PORTFOLIO_PATH.read_text())
    return {"holdings": [], "last_rebalance": None, "next_rebalance": None, "history": []}


def save(data: dict) -> None:
    PORTFOLIO_PATH.write_text(json.dumps(data, indent=2, default=str))


def rebalance_due(portfolio: dict) -> bool:
    nxt = portfolio.get("next_rebalance")
    if not nxt:
        return True
    return datetime.now().date() >= datetime.fromisoformat(nxt).date()


def apply_rebalance(portfolio: dict, new_stocks: list[dict]) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    next_rb = (datetime.now() + timedelta(days=91)).strftime("%Y-%m-%d")

    old = {h["ticker"] for h in portfolio.get("holdings", [])}
    new = {s["ticker"] for s in new_stocks}

    portfolio.setdefault("history", []).append(
        {"date": today, "holdings": portfolio.get("holdings", []), "action": "rebalance"}
    )
    weight = round(1.0 / len(new_stocks), 4)
    portfolio["holdings"] = [
        {
            "ticker": s["ticker"],
            "entry_date": today,
            "rs_rating": round(s.get("rs_rating", 0), 1),
            "canslim_score": s.get("canslim_score", 0),
            "final_score": round(s.get("final_score", 0), 2),
            "weight": weight,
            "sector": s.get("sector", "Unknown"),
        }
        for s in new_stocks
    ]
    portfolio["last_rebalance"] = today
    portfolio["next_rebalance"] = next_rb

    return {
        "portfolio": portfolio,
        "trades": {"sell": sorted(old - new), "buy": sorted(new - old), "hold": sorted(old & new)},
    }


def summary(portfolio: dict) -> str:
    h = portfolio.get("holdings", [])
    if not h:
        return "포트폴리오 비어있음"
    lines = [f"=== 현재 포트폴리오 ({portfolio.get('last_rebalance', '?')}) ==="]
    for s in h:
        lines.append(
            f"  {s['ticker']:8s}  RS={s.get('rs_rating',0):5.1f}"
            f"  CANSLIM={s.get('canslim_score',0):3d}/70"
            f"  비중={s.get('weight',0.2)*100:.0f}%"
            f"  섹터={s.get('sector','?')}"
        )
    lines.append(f"다음 리밸런싱: {portfolio.get('next_rebalance', '미설정')}")
    return "\n".join(lines)
