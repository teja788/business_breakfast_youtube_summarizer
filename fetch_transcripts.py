#!/usr/bin/env python3
"""Fetch-only backfill driver (no ANTHROPIC_API_KEY needed).

Reuses bb_summarizer.discover_videos + get_transcript to pull Telugu transcripts
SEQUENTIALLY (kome.ai rate-limits concurrency) for every missing date in a window,
saving just the .te.txt plus a meta sidecar (date/video_id/title) so the in-session
translate/analyze step can run afterwards. Translation is intentionally NOT done here.
"""
import datetime as dt
import json
import time
from pathlib import Path

import bb_summarizer as bb

START = dt.date(2026, 1, 1)
TODAY = dt.date(2026, 6, 22)
OUT = Path("output")


def existing_dates() -> set[str]:
    te = OUT / "telugu_transcript"
    return {p.name.split("__", 1)[0] for p in te.glob("*.te.txt")}


def main() -> int:
    args = bb.build_args([
        "--news-channel", "",      # the deep-scan of the news channel hangs / is blocked
        "--scan", "300",
        "--days", "175",
        "--kome-retries", "2",     # uncached IDs never warm up -> fail fast
    ])
    matches = bb.discover_videos(args)

    have = existing_dates()
    todo = [m for m in matches
            if START <= m["upload_date"] <= TODAY
            and m["upload_date"].isoformat() not in have]
    todo.sort(key=lambda m: m["upload_date"])  # oldest first

    print(f"\n[backfill] {len(todo)} missing date(s) to attempt:")
    for m in todo:
        print(f"  {m['upload_date']}  {len(m['candidates'])} candidate(s)")

    meta_path = OUT / "_fetch_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    fetched, failed = [], []
    for m in todo:
        date = m["upload_date"]
        got = None
        for c in m["candidates"]:
            tag = c["channel"] + ("/live" if c["is_live"] else "")
            print(f"\n=== {date} | {c['title']} ({c['id']}) [{tag}] ===", flush=True)
            text = bb.get_transcript(c["id"], args)
            if text:
                stem = f"{date.isoformat()}__{bb.sanitize_filename(c['title'])}"
                p = OUT / "telugu_transcript" / f"{stem}.te.txt"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
                meta[stem] = {"date": date.isoformat(), "video_id": c["id"],
                              "title": c["title"], "chars": len(text)}
                print(f"[saved] {p}  ({len(text)} chars)", flush=True)
                got = stem
                break
            print("[try-next] no transcript on this copy.", flush=True)
            time.sleep(2)
        if got:
            fetched.append((date.isoformat(), got))
        else:
            failed.append(date.isoformat())
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        time.sleep(3)  # be gentle to kome between dates

    print("\n" + "=" * 60)
    print(f"[backfill] fetched {len(fetched)} / {len(todo)} ; failed {len(failed)}")
    print("FETCHED:", ", ".join(d for d, _ in fetched) or "(none)")
    print("FAILED :", ", ".join(failed) or "(none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
