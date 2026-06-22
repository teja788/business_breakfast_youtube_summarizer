import datetime as dt, json, time
from pathlib import Path
import bb_summarizer as bb

TARGETS = {"2026-01-02","2026-01-07","2026-01-08","2026-01-13","2026-01-16","2026-01-22",
"2026-02-03","2026-02-04","2026-02-05","2026-02-16","2026-02-19","2026-03-11","2026-03-17",
"2026-03-20","2026-03-23","2026-04-02","2026-04-16","2026-04-22","2026-04-23","2026-04-24",
"2026-05-05","2026-05-06","2026-05-07","2026-05-08","2026-05-12","2026-05-14","2026-05-15",
"2026-05-18","2026-06-11","2026-06-12","2026-06-15"}
OUT = Path("output")
args = bb.build_args(["--news-channel","", "--scan","300", "--days","175", "--kome-retries","2"])
matches = bb.discover_videos(args)
todo = sorted([m for m in matches if m["upload_date"].isoformat() in TARGETS], key=lambda m:m["upload_date"])
print(f"[fetch-missing] attempting {len(todo)} dates", flush=True)
meta_path = OUT/"_fetch_meta.json"
meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
fetched, failed = [], []
for m in todo:
    date = m["upload_date"]; got=None
    for c in m["candidates"]:
        tag = c["channel"]+("/live" if c["is_live"] else "")
        print(f"=== {date} | {c['id']} [{tag}] {c['title'][:60]}", flush=True)
        text = bb.get_transcript(c["id"], args)
        if text:
            stem = f"{date.isoformat()}__{bb.sanitize_filename(c['title'])}"
            p = OUT/"telugu_transcript"/f"{stem}.te.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            meta[stem]={"date":date.isoformat(),"video_id":c["id"],"title":c["title"],"chars":len(text)}
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
            print(f"[SAVED] {date} {c['id']} {len(text)} chars", flush=True)
            got=stem; break
        time.sleep(2)
    (fetched if got else failed).append(date.isoformat())
    time.sleep(3)
print("="*50, flush=True)
print("FETCHED:", ", ".join(fetched) or "(none)", flush=True)
print("FAILED :", ", ".join(failed) or "(none)", flush=True)
