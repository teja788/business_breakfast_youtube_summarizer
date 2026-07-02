#!/usr/bin/env python3
"""Aggregate output/ into the split docs/data/*.json files for the dashboard.

Reads the already-produced pipeline outputs (no network, no API calls) and
emits six JSON files the browser fetches. Everything is DETERMINISTIC — plain
Python over the existing JSON/CSV, no LLM calls. Run after the daily pipeline,
or manually:  python build_dashboard_data.py

Emits under docs/data/:
  meta.json       — months, counts, latest episode, 7-day weekly digest
  scorecard.json  — scorecard rows (+sector) and per-analyst stats
  recs.json       — Kutumba Rao recommendation table (+spark/sector/symbol)
  episodes.json   — per-episode summary, takeaways and call arrays
  stocks.json     — per-stock dossier (mentions + scorecard + spark), by normKey
  search.json     — flat search docs (one per stock, one per episode)

Stock-name keying everywhere uses analyst_calls.norm_key().
"""
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from analyst_calls import is_buy, is_sell, norm_key

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
DOCS = ROOT / "docs"
DATA = DOCS / "data"

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


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# --------------------------------------------------------------------------- #
# tickers.json  (raw-name keyed) -> norm_key keyed lookup for symbol/sector
# --------------------------------------------------------------------------- #
def load_tickers_by_key():
    """norm_key -> {symbol, sector, raw_name} from tickers.json.

    tickers.json is keyed by the raw stock name; collapse to norm_key so any
    spelling variant resolves. Prefer a priceable entry (it carries the real
    symbol); fall back to whatever exists so sector still comes through.
    """
    raw = load_json(ROOT / "tickers.json") or {}
    by_key = {}
    for name, v in raw.items():
        k = norm_key(name)
        if not k:
            continue
        cand = {
            "symbol": v.get("symbol") or "",
            "sector": v.get("sector") or "",
            "raw_name": name,
            "priceable": bool(v.get("priceable")),
        }
        cur = by_key.get(k)
        if cur is None:
            by_key[k] = cand
            continue
        # Prefer priceable; otherwise fill blanks from this candidate.
        if cand["priceable"] and not cur["priceable"]:
            by_key[k] = cand
        else:
            if not cur["symbol"] and cand["symbol"]:
                cur["symbol"] = cand["symbol"]
            if not cur["sector"] and cand["sector"]:
                cur["sector"] = cand["sector"]
    return by_key


# --------------------------------------------------------------------------- #
# scorecard.csv
# --------------------------------------------------------------------------- #
def read_scorecard(tickers=None):
    """Build {rows, stats}. Each row gets a 'sector' from tickers.json."""
    tickers = tickers or {}
    path = OUT / "scorecard" / "scorecard.csv"
    rows = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                stock = r.get("stock", "")
                sector = tickers.get(norm_key(stock), {}).get("sector", "")
                rows.append({
                    "analyst": r.get("analyst", ""),
                    "stock": stock,
                    "symbol": r.get("symbol", ""),
                    "sector": sector,
                    "call_date": r.get("call_date", ""),
                    "last_buy_date": r.get("last_buy_date", "") or r.get("call_date", ""),
                    "exit_date": r.get("exit_date", ""),
                    "position": r.get("position", ""),
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


# --------------------------------------------------------------------------- #
# recommendations.csv  (Kutumba Rao consolidated table)
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# summaries / episodes  (kutumba + kranti calls + summary md)
# --------------------------------------------------------------------------- #
def parse_summary(stem):
    path = OUT / "summary" / f"{stem}.summary.md"
    if not path.exists():
        return "", "", ""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else ""
    m = YT_RE.search(text)
    return text, title, (m.group(0) if m else "")


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


# --------------------------------------------------------------------------- #
# deterministic text helpers
# --------------------------------------------------------------------------- #
def _names_list(calls):
    """Distinct, order-preserving stock display names from a call array."""
    seen, out = set(), []
    for c in calls:
        s = (c.get("stock") or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _split_actions(calls):
    """(buys, sells) display-name lists for an episode's calls."""
    buys, sells, bseen, sseen = [], [], set(), set()
    for c in calls:
        s = (c.get("stock") or "").strip()
        if not s:
            continue
        a = c.get("action")
        if is_buy(a) and s not in bseen:
            bseen.add(s)
            buys.append(s)
        if is_sell(a) and s not in sseen:
            sseen.add(s)
            sells.append(s)
    return buys, sells


def episode_takeaways(ep):
    """Deterministic short bullets, e.g.
    'Kutumba Rao: 2 buys (A, B), 1 sell (C)'. Omit an analyst with no calls."""
    out = []
    for label, calls in (("Kutumba Rao", ep["kutumba"]), ("Kranthi", ep["kranti"])):
        if not calls:
            continue
        buys, sells = _split_actions(calls)
        parts = []
        if buys:
            parts.append(f"{len(buys)} buy{'s' if len(buys) != 1 else ''} ({', '.join(buys)})")
        if sells:
            parts.append(f"{len(sells)} sell{'s' if len(sells) != 1 else ''} ({', '.join(sells)})")
        if not parts:
            # Calls existed but none were buys/sells (e.g. all holds).
            parts.append(f"{len(calls)} call{'s' if len(calls) != 1 else ''} ({', '.join(_names_list(calls))})")
        out.append(f"{label}: {', '.join(parts)}")
    return out


MD_STRIP_RE = re.compile(r"[#*_`>\-]+")


def strip_md(text, limit):
    """Flatten markdown to plain-ish text and truncate."""
    text = re.sub(r"https?://\S+", "", text or "")
    text = MD_STRIP_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


# --------------------------------------------------------------------------- #
# spark: distinct episode-dates per month a stock was mentioned in any call
# --------------------------------------------------------------------------- #
def build_spark_index(episodes):
    """norm_key -> {YYYY-MM -> set(episode dates)} across ALL calls."""
    idx = defaultdict(lambda: defaultdict(set))
    for ep in episodes:
        date = ep["date"]
        if not date:
            continue
        month = date[:7]
        for c in ep["kutumba"] + ep["kranti"]:
            k = norm_key(c.get("stock", ""))
            if k:
                idx[k][month].add(date)
    return idx


def spark_for(idx, key, months):
    """[count of distinct dates in months[i]] aligned to meta.months."""
    per_month = idx.get(key, {})
    return [len(per_month.get(m, ())) for m in months]


def month_range(first, last):
    """Contiguous list of YYYY-MM strings from first to last inclusive,
    so gap months without episodes still appear on the sparkline axis."""
    y, m = int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# --------------------------------------------------------------------------- #
# weekly digest  (last 7 calendar days ending at generated_at date)
# --------------------------------------------------------------------------- #
def weekly_digest(episodes, today):
    since = today - timedelta(days=6)  # 7 calendar days inclusive
    since_s = since.isoformat()
    window = [e for e in episodes if e["date"] and since_s <= e["date"] <= today.isoformat()]

    lines = []
    if not window:
        return {"since": since_s, "lines": ["No new episodes in the last 7 days."]}

    # Per-analyst buy/sell tallies over the window.
    for label, attr in (("Kutumba Rao", "kutumba"), ("Kranthi", "kranti")):
        buys, sells, bseen, sseen = [], [], set(), set()
        for e in window:
            for c in e[attr]:
                s = (c.get("stock") or "").strip()
                if not s:
                    continue
                k = norm_key(s) or s  # dedupe spelling variants of one stock
                if is_buy(c.get("action")) and k not in bseen:
                    bseen.add(k)
                    buys.append(s)
                if is_sell(c.get("action")) and k not in sseen:
                    sseen.add(k)
                    sells.append(s)
        if buys:
            shown = ", ".join(buys[:5]) + (" …" if len(buys) > 5 else "")
            lines.append(f"{label}: {len(buys)} new buy call{'s' if len(buys) != 1 else ''} — {shown}")
        if sells:
            shown = ", ".join(sells[:5]) + (" …" if len(sells) > 5 else "")
            lines.append(f"{label}: {len(sells)} sell{'s' if len(sells) != 1 else ''} — {shown}")

    # Most discussed across the window (by distinct-episode mentions).
    mention_eps = defaultdict(set)
    disp = {}
    for e in window:
        for c in e["kutumba"] + e["kranti"]:
            s = (c.get("stock") or "").strip()
            if not s:
                continue
            k = norm_key(s)
            mention_eps[k].add(e["date"])
            disp.setdefault(k, s)
    top = sorted(mention_eps.items(), key=lambda kv: (-len(kv[1]), disp[kv[0]]))[:2]
    top = [(k, n) for k, n in top if len(n) >= 1]
    if top:
        parts = [f"{disp[k]} ({len(n)} mention{'s' if len(n) != 1 else ''})" for k, n in top]
        lines.append("Most discussed: " + ", ".join(parts))

    if not lines:
        lines = [f"{len(window)} new episode{'s' if len(window) != 1 else ''}, no fresh buy/sell calls."]
    return {"since": since_s, "lines": lines[:6]}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today = datetime.now(timezone.utc).date()

    tickers = load_tickers_by_key()
    episodes = read_episodes()
    recs = read_recommendations()
    scorecard = read_scorecard(tickers)

    ep_months = sorted({e["date"][:7] for e in episodes if e["date"]})
    months = month_range(ep_months[0], ep_months[-1]) if ep_months else []
    spark_idx = build_spark_index(episodes)

    DATA.mkdir(parents=True, exist_ok=True)

    def write(name, obj):
        (DATA / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=None), encoding="utf-8"
        )

    # --- scorecard rows grouped by stock norm_key (reused by stocks.json) ---
    sc_by_key = defaultdict(list)
    for r in scorecard["rows"]:
        sc_by_key[norm_key(r["stock"])].append({
            "analyst": r["analyst"],
            "call_date": r["call_date"],
            "last_buy_date": r["last_buy_date"],
            "exit_date": r["exit_date"],
            "position": r["position"],
            "status": r["status"],
            "entry": r["entry"],
            "current": r["current"],
            "return_pct": r["return_pct"],
            "nifty_pct": r["nifty_pct"],
            "alpha_pct": r["alpha_pct"],
        })

    # ----- 1. meta.json -----
    scored = len(scorecard["rows"])
    n_recs = len(recs)
    latest = episodes[0] if episodes else None
    meta = {
        "generated_at": generated_at,
        "months": months,
        "counts": {
            "episodes": len(episodes),
            "recommendations": n_recs,
            "scored": scored,
        },
        "latest": {
            "date": latest["date"],
            "title": latest["title"],
            "stem": latest["stem"],
            "youtube_url": latest["youtube_url"],
        } if latest else None,
        "weekly_digest": weekly_digest(episodes, today),
    }
    write("meta.json", meta)

    # ----- 2. scorecard.json -----
    write("scorecard.json", {
        "generated_at": generated_at,
        "rows": scorecard["rows"],
        "stats": scorecard["stats"],
    })

    # ----- 3. recs.json -----
    rec_rows = []
    for r in recs:
        k = norm_key(r["stock"])
        t = tickers.get(k, {})
        rec_rows.append({
            "stock": r["stock"],
            "normKey": k,
            "symbol": t.get("symbol", ""),
            "sector": t.get("sector", ""),
            "action": r["action"],
            "price": r["price"],
            "summary": r["summary"],
            "first": r["first"],
            "last": r["last"],
            "times": r["times"],
            "history": r["history"],
            "spark": spark_for(spark_idx, k, months),
        })
    write("recs.json", {"generated_at": generated_at, "rows": rec_rows})

    # ----- 4. episodes.json -----
    ep_rows = []
    for e in episodes:
        ep_rows.append({
            "date": e["date"],
            "title": e["title"],
            "stem": e["stem"],
            "youtube_url": e["youtube_url"],
            "summary_md": e["summary_md"],
            "takeaways": episode_takeaways(e),
            "kutumba": e["kutumba"],
            "kranti": e["kranti"],
        })
    write("episodes.json", {"generated_at": generated_at, "episodes": ep_rows})

    # ----- 5. stocks.json -----
    # Join per-episode calls (mentions) + tickers (symbol/sector) + scorecard.
    stocks = {}
    name_counts = defaultdict(Counter)  # normKey -> Counter(raw spellings)
    for e in episodes:
        for label, attr in (("Kutumba Rao", "kutumba"), ("Kranthi", "kranti")):
            for c in e[attr]:
                raw = (c.get("stock") or "").strip()
                k = norm_key(raw)
                if not k:
                    continue
                name_counts[k][raw] += 1
                st = stocks.setdefault(k, {"mentions": []})
                st["mentions"].append({
                    "date": e["date"],
                    "analyst": label,
                    "action": c.get("action", ""),
                    "price": c.get("price", ""),
                    "note": c.get("note", ""),
                    "detail": c.get("detail", ""),
                    "stem": e["stem"],
                })

    stocks_out = {}
    for k, st in stocks.items():
        # Most common raw spelling as display name (ties broken alphabetically).
        common = name_counts[k].most_common()
        name = sorted(common, key=lambda kv: (-kv[1], kv[0]))[0][0] if common else k
        t = tickers.get(k, {})
        mentions = sorted(st["mentions"], key=lambda m: m["date"])
        stocks_out[k] = {
            "name": name,
            "symbol": t.get("symbol", ""),
            "sector": t.get("sector", ""),
            "spark": spark_for(spark_idx, k, months),
            "mentions": mentions,
            "scorecard": sc_by_key.get(k, []),
        }
    write("stocks.json", {"generated_at": generated_at, "stocks": stocks_out})

    # ----- 6. search.json -----
    docs = []
    for k, s in stocks_out.items():
        notes = " ".join(
            " ".join(x for x in (m.get("note", ""), m.get("detail", "")) if x)
            for m in s["mentions"]
        )
        text = " ".join(x for x in (s["name"], s["symbol"], s["sector"]) if x)
        text = (text + " " + notes).strip()
        docs.append({
            "id": f"stock:{k}",
            "type": "stock",
            "title": s["name"],
            "text": re.sub(r"\s+", " ", text)[:600],
            "ref": k,
        })
    for e in episodes:
        names = " ".join(_names_list(e["kutumba"] + e["kranti"]))
        text = (strip_md(e["summary_md"], 1200) + " " + names).strip()
        title = f"{e['date']} {e['title']}".strip()
        docs.append({
            "id": f"ep:{e['stem']}",
            "type": "episode",
            "title": title,
            "text": re.sub(r"\s+", " ", text),
            "ref": e["stem"],
        })
    write("search.json", {"generated_at": generated_at, "docs": docs})

    # Stop emitting the monolithic file — frontend now reads the split files.
    legacy = DOCS / "data.json"
    removed_legacy = legacy.exists()
    if removed_legacy:
        legacy.unlink()

    # ----- report -----
    print(f"Wrote {DATA}/ (6 files)")
    print(f"  meta.json      : episodes={len(episodes)} recs={n_recs} scored={scored} months={months}")
    print(f"  scorecard.json : rows={len(scorecard['rows'])} analysts={list(scorecard['stats'])}")
    print(f"  recs.json      : rows={len(rec_rows)}")
    print(f"  episodes.json  : episodes={len(ep_rows)}")
    print(f"  stocks.json    : stocks={len(stocks_out)} "
          f"with_scorecard={sum(1 for s in stocks_out.values() if s['scorecard'])} "
          f"with_sector={sum(1 for s in stocks_out.values() if s['sector'])}")
    print(f"  search.json    : docs={len(docs)} "
          f"(stock={sum(1 for d in docs if d['type']=='stock')}, "
          f"episode={sum(1 for d in docs if d['type']=='episode')})")
    if removed_legacy:
        print("  removed legacy docs/data.json")


if __name__ == "__main__":
    main()
