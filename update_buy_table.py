#!/usr/bin/env python3
"""
Maintain consolidated tables of Kutumba Rao's stock recommendations.

Data model
----------
Each processed episode drops a small machine-readable sidecar next to its
kutumba_rao markdown:

    output/kutumba_rao/<stem>.buys.json
    {
      "date": "2026-06-16",
      "video_id": "MCht7Xs4bL8",
      "title": "...",
      "recommendations": [
        {"stock": "CG Power", "action": "Add", "price": "target ~1,500", "note": "..."},
        {"stock": "Some Co",  "action": "Hold", "price": "", "note": "..."},
        ...
      ]
    }

Older sidecars used the key "buys" and had no "action" field (they only held
Buy/Add/Accumulate calls). Both shapes are read; a missing action defaults to
"Buy".

This script globs every *.buys.json, aggregates per stock, and (re)writes:

    output/kutumba_rao/recommendations.md      (human table, ALL actions)
    output/kutumba_rao/recommendations.csv     (machine table, ALL actions)
    output/kutumba_rao/buy_recommendations.md  (human table, BUY-type only)
    output/kutumba_rao/buy_recommendations.csv (machine table, BUY-type only)
    output/kutumba_rao/stock_history.txt       (per-stock FULL dated comments)

Each recommendation may carry a fuller ``detail`` field (the non-consolidated
comment); ``stock_history.txt`` uses it (falling back to ``note``).

Aggregation is per stock (case/punctuation-insensitive key):
  - Times mentioned = number of DISTINCT dates it was recommended
  - Last/First mentioned = newest/oldest of those dates
  - Latest action / Price / Summary = taken from that most recent episode
  - Action history = count per action across all dates (e.g. "Buy x2, Hold x1")

Idempotent: safe to run any time (the pipeline calls rebuild_buy_table()).
"""
from __future__ import annotations

import csv
import json
import re
import textwrap
from collections import Counter
from pathlib import Path

from analyst_calls import is_buy  # canonical buy-action matcher

DEFAULT_DIR = Path("output/kutumba_rao")
KRANTI_DIR = Path("output/kranti")


def _key(name: str) -> str:
    """Normalise a stock name so 'CG Power' == 'cg power.' across runs."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _norm_action(action: str) -> str:
    """Tidy an action label; empty -> 'Buy' (legacy sidecars had no action)."""
    a = (action or "").strip()
    if not a:
        return "Buy"
    # Title-case but keep common multi-word labels readable.
    return a[:1].upper() + a[1:]


def load_recommendation_records(kdir: Path) -> list[dict]:
    """Flatten every sidecar into one row per (stock, episode)."""
    rows = []
    for f in sorted(kdir.glob("*.buys.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        date = doc.get("date", "")
        items = doc.get("recommendations")
        if items is None:                       # legacy key
            items = doc.get("buys", [])
        for b in items:
            stock = (b.get("stock") or "").strip()
            if not stock:
                continue
            rows.append({
                "stock": stock,
                "action": _norm_action(b.get("action")),
                "date": date,
                "video_id": doc.get("video_id", ""),
                "price": (b.get("price") or "").strip(),
                "note": (b.get("note") or "").strip(),
                # Fuller, non-consolidated comment when available; else the note.
                "detail": (b.get("detail") or b.get("note") or "").strip(),
            })
    return rows


# Back-compat alias.
load_buy_records = load_recommendation_records


def load_kranti_records(kdir: Path = KRANTI_DIR) -> list[dict]:
    """Flatten every *.kranti.json sidecar into the same row shape as
    load_recommendation_records (Kranthi calls have no price/detail fields)."""
    rows = []
    for f in sorted(Path(kdir).glob("*.kranti.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        date = doc.get("date", "")
        for c in doc.get("calls", []):
            stock = (c.get("stock") or "").strip()
            if not stock:
                continue
            note = (c.get("note") or "").strip()
            rows.append({
                "stock": stock,
                "action": _norm_action(c.get("action")),
                "date": date,
                "video_id": "",
                "price": "",
                "note": note,
                "detail": note,
            })
    return rows


def aggregate(rows: list[dict]) -> list[dict]:
    """One entry per stock with count-of-days, latest details, action history."""
    by_stock: dict[str, dict] = {}
    for r in rows:
        k = _key(r["stock"])
        agg = by_stock.setdefault(k, {
            "stock": r["stock"], "dates": set(), "latest_date": "",
            "action": "", "price": "", "note": "", "actions": Counter(),
        })
        agg["dates"].add(r["date"])
        agg["actions"][r["action"]] += 1
        if r["date"] >= agg["latest_date"]:        # ISO dates sort lexically
            agg["latest_date"] = r["date"]
            agg["stock"] = r["stock"]               # prefer latest spelling
            agg["action"] = r["action"]
            agg["price"] = r["price"]
            agg["note"] = r["note"]
    out = []
    for agg in by_stock.values():
        dates = sorted(d for d in agg["dates"] if d)
        history = ", ".join(f"{a} x{n}" for a, n in agg["actions"].most_common())
        out.append({
            "stock": agg["stock"],
            "action": agg["action"],
            "price": agg["price"],
            "note": agg["note"],
            "first_suggested": dates[0] if dates else "",
            "last_suggested": dates[-1] if dates else "",
            "times_suggested": len(dates),
            "action_history": history,
            "all_dates": ",".join(dates),
        })
    # most-recently-suggested first, then most-frequently
    out.sort(key=lambda e: (e["last_suggested"], e["times_suggested"]), reverse=True)
    return out


def write_csv(entries: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Stock", "Latest action", "Price/level", "Summary",
                    "First suggested", "Last suggested", "Times suggested (days)",
                    "Action history", "All dates"])
        for e in entries:
            w.writerow([e["stock"], e["action"], e["price"], e["note"],
                        e["first_suggested"], e["last_suggested"],
                        e["times_suggested"], e["action_history"], e["all_dates"]])


def write_md(entries: list[dict], path: Path, *, title: str, subtitle: str) -> None:
    lines = [
        f"# {title}",
        "",
        "_Auto-generated by `update_buy_table.py` from `*.buys.json` sidecars._  ",
        f"_{subtitle}_",
        "",
        "| Stock | Latest action | Price / level | What he said | Last suggested "
        "| Times (days) | Action history |",
        "|-------|---------------|---------------|--------------|----------------"
        "|--------------|----------------|",
    ]
    for e in entries:
        note = e["note"].replace("|", "\\|").replace("\n", " ")
        price = e["price"].replace("|", "\\|") or "—"
        action = e["action"].replace("|", "\\|") or "—"
        hist = e["action_history"].replace("|", "\\|")
        lines.append(f"| {e['stock']} | {action} | {price} | {note} "
                     f"| {e['last_suggested']} | {e['times_suggested']} | {hist} |")
    lines.append("")
    lines.append(f"_Total stocks: {len(entries)}._")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_stock_history_txt(rows: list[dict], path: Path, width: int = 78) -> None:
    """Per-stock plain-text history: every stock (alphabetical) with its full,
    non-consolidated comment for each date. Written as a neat, wrapped .txt."""
    # Group rows by normalised stock key; keep a display name (latest spelling).
    by_stock: dict[str, dict] = {}
    for r in rows:
        k = _key(r["stock"])
        g = by_stock.setdefault(k, {"name": r["stock"], "latest": "", "items": []})
        g["items"].append(r)
        if r["date"] >= g["latest"]:
            g["latest"] = r["date"]
            g["name"] = r["stock"]                  # prefer latest spelling

    body_indent = " " * 6          # under each dated entry
    wrapper = textwrap.TextWrapper(
        width=width, initial_indent=body_indent, subsequent_indent=body_indent)

    out: list[str] = [
        "KUTUMBA RAO - PER-STOCK COMMENT HISTORY",
        "=" * width,
        "Auto-generated by update_buy_table.py from the *.buys.json sidecars.",
        "Each stock (alphabetical) lists his full comment for every date he",
        "discussed it. Action = his stance that day; level = as stated then,",
        "not a live quote.",
        "",
        f"{len(by_stock)} stocks.",
        "",
    ]
    for k in sorted(by_stock, key=lambda x: by_stock[x]["name"].lower()):
        g = by_stock[k]
        items = sorted(g["items"], key=lambda r: r["date"])
        out.append(g["name"])
        out.append("-" * width)
        for r in items:
            level = f"  (level: {r['price']})" if r["price"] else ""
            out.append(f"  {r['date']}  [{r['action']}]{level}")
            for para in (r["detail"] or "(no comment)").split("\n"):
                out.append(wrapper.fill(para))
            out.append("")
        out.append("")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def rebuild_buy_table(kdir: Path = DEFAULT_DIR) -> int:
    """Regenerate recommendations.{md,csv} (all actions) and buy_recommendations.{md,csv}
    (buy-type only). Returns the stock count of the all-actions table."""
    kdir = Path(kdir)
    rows = load_recommendation_records(kdir)

    # All-actions tables.
    all_entries = aggregate(rows)
    write_csv(all_entries, kdir / "recommendations.csv")
    write_md(all_entries, kdir / "recommendations.md",
             title="Kutumba Rao — all recommendations (consolidated)",
             subtitle="All calls: Buy / Add / Accumulate / Hold / Reduce / Sell / "
                      "Avoid / Book Profit / Watch. Price = as stated on the last "
                      "date suggested (not a live quote).")

    # Buy-type-only tables (backward compatible).
    buy_rows = [r for r in rows if is_buy(r["action"])]
    buy_entries = aggregate(buy_rows)
    write_csv(buy_entries, kdir / "buy_recommendations.csv")
    write_md(buy_entries, kdir / "buy_recommendations.md",
             title="Kutumba Rao — BUY recommendations (consolidated)",
             subtitle="Buy = Buy / Add / Accumulate calls only. Price = as stated on "
                      "the last date suggested (not a live quote).")

    # Per-stock full dated comment history (plain text).
    write_stock_history_txt(rows, kdir / "stock_history.txt")
    # Drop the older markdown version if it lingers from a previous run.
    (kdir / "stock_history.md").unlink(missing_ok=True)

    return len(all_entries)


def rebuild_kranti_table(kdir: Path = KRANTI_DIR) -> int:
    """Regenerate Kranthi's consolidated tables from the *.kranti.json sidecars.
    Returns the stock count of the all-actions table."""
    kdir = Path(kdir)
    rows = load_kranti_records(kdir)

    all_entries = aggregate(rows)
    write_csv(all_entries, kdir / "recommendations.csv")
    write_md(all_entries, kdir / "recommendations.md",
             title="Kranthi — all recommendations (consolidated)",
             subtitle="All calls: Buy / Add / Accumulate / Hold / Reduce / Sell / "
                      "Avoid / Book Profit / Watch. Auto-generated from the "
                      "*.kranti.json sidecars; speaker attribution in the "
                      "auto-captions is imperfect, ambiguous calls are excluded "
                      "at extraction time.")

    buy_rows = [r for r in rows if is_buy(r["action"])]
    buy_entries = aggregate(buy_rows)
    write_csv(buy_entries, kdir / "buy_recommendations.csv")
    write_md(buy_entries, kdir / "buy_recommendations.md",
             title="Kranthi — BUY recommendations (consolidated)",
             subtitle="Buy = Buy / Add / Accumulate calls only. Auto-generated "
                      "from the *.kranti.json sidecars.")

    return len(all_entries)


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Rebuild Kutumba Rao + Kranthi recommendation tables.")
    p.add_argument("--dir", default=str(DEFAULT_DIR), help="kutumba_rao output dir")
    p.add_argument("--kranti-dir", default=str(KRANTI_DIR), help="kranti output dir")
    args = p.parse_args(argv)
    n = rebuild_buy_table(Path(args.dir))
    k = rebuild_kranti_table(Path(args.kranti_dir))
    print(f"Wrote recommendations.md/.csv + buy_recommendations.md/.csv "
          f"({n} Kutumba Rao stocks, {k} Kranthi stocks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
