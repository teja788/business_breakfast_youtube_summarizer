#!/usr/bin/env python3
"""Aggregate output/ into docs/data.json for the static web dashboard.

Reads the already-produced pipeline outputs (no network, no API calls) and
emits a single JSON manifest the browser can fetch. Run after the daily
pipeline, or manually:  python build_dashboard_data.py
"""
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
DOCS = ROOT / "docs"

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
YT_RE = re.compile(r"https?://(?:youtu\.be/|www\.youtube\.com/watch\?v=)([\w-]+)")


def num(v):
    """CSV cell -> float or None."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def read_scorecard():
    path = OUT / "scorecard" / "scorecard.csv"
    rows = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append({
                    "analyst": r.get("analyst", ""),
                    "stock": r.get("stock", ""),
                    "symbol": r.get("symbol", ""),
                    "call_date": r.get("call_date", ""),
                    "action": r.get("actions", ""),
                    "entry": num(r.get("entry")),
                    "current": num(r.get("current")),
                    "return_pct": num(r.get("return_pct")),
                    "nifty_pct": num(r.get("nifty_pct")),
                    "alpha_pct": num(r.get("alpha_pct")),
                    "status": r.get("status", ""),
                })

    # Per-analyst stats computed from priced rows.
    stats = {}
    for analyst in sorted({r["analyst"] for r in rows if r["analyst"]}):
        priced = [r for r in rows if r["analyst"] == analyst and r["return_pct"] is not None]
        if not priced:
            stats[analyst] = {"priced": 0}
            continue
        rets = sorted(r["return_pct"] for r in priced)
        alphas = [r["alpha_pct"] for r in priced if r["alpha_pct"] is not None]
        wins = sum(1 for x in rets if x > 0)
        best = max(priced, key=lambda r: r["return_pct"])
        worst = min(priced, key=lambda r: r["return_pct"])
        mid = len(rets) // 2
        median = rets[mid] if len(rets) % 2 else (rets[mid - 1] + rets[mid]) / 2
        stats[analyst] = {
            "priced": len(priced),
            "wins": wins,
            "win_rate": round(100 * wins / len(priced), 1),
            "avg_return": round(sum(rets) / len(rets), 1),
            "median_return": round(median, 1),
            "avg_alpha": round(sum(alphas) / len(alphas), 1) if alphas else None,
            "best": {"stock": best["stock"], "return_pct": best["return_pct"]},
            "worst": {"stock": worst["stock"], "return_pct": worst["return_pct"]},
        }
    return {"rows": rows, "stats": stats}


def read_recommendations():
    path = OUT / "kutumba_rao" / "recommendations.csv"
    recs = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                recs.append({
                    "stock": r.get("Stock", ""),
                    "action": r.get("Latest action", ""),
                    "price": r.get("Price/level", ""),
                    "summary": r.get("Summary", ""),
                    "first": r.get("First suggested", ""),
                    "last": r.get("Last suggested", ""),
                    "times": r.get("Times suggested (days)", ""),
                    "history": r.get("Action history", ""),
                })
    return recs


def parse_summary(stem):
    path = OUT / "summary" / f"{stem}.summary.md"
    if not path.exists():
        return "", "", ""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else ""
    m = YT_RE.search(text)
    return text, title, (m.group(0) if m else "")


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def read_episodes():
    """Collect every episode stem across summary / kutumba / kranti outputs."""
    episodes = {}

    def slot(stem):
        return episodes.setdefault(stem, {
            "stem": stem,
            "date": (DATE_RE.match(stem).group(1) if DATE_RE.match(stem) else ""),
            "title": "",
            "youtube_url": "",
            "summary_md": "",
            "kutumba": [],
            "kranti": [],
        })

    # Kutumba Rao buy calls
    for p in (OUT / "kutumba_rao").glob("*.buys.json"):
        stem = p.name[: -len(".buys.json")]
        data = load_json(p) or {}
        e = slot(stem)
        e["kutumba"] = data.get("recommendations", [])
        if data.get("title"):
            e["title"] = data["title"]
        if data.get("video_id") and not e["youtube_url"]:
            e["youtube_url"] = f"https://youtu.be/{data['video_id']}"

    # Kranthi calls
    for p in (OUT / "kranti").glob("*.kranti.json"):
        stem = p.name[: -len(".kranti.json")]
        data = load_json(p) or {}
        slot(stem)["kranti"] = data.get("calls", [])

    # Summaries (also the canonical source for title + youtube link)
    for p in (OUT / "summary").glob("*.summary.md"):
        stem = p.name[: -len(".summary.md")]
        slot(stem)
    for stem, e in episodes.items():
        md, title, yt = parse_summary(stem)
        e["summary_md"] = md
        if title:
            e["title"] = title
        if yt:
            e["youtube_url"] = yt
        if not e["title"]:
            e["title"] = stem.split("__", 1)[-1].replace("_", " ")

    return sorted(episodes.values(), key=lambda e: e["date"], reverse=True)


def main():
    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scorecard": read_scorecard(),
        "recommendations": read_recommendations(),
        "episodes": read_episodes(),
    }
    DOCS.mkdir(exist_ok=True)
    (DOCS / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=None), encoding="utf-8"
    )
    sc = data["scorecard"]
    print(f"docs/data.json written")
    print(f"  scorecard rows : {len(sc['rows'])} ({', '.join(sc['stats'])})")
    print(f"  recommendations: {len(data['recommendations'])}")
    print(f"  episodes       : {len(data['episodes'])}")


if __name__ == "__main__":
    main()
