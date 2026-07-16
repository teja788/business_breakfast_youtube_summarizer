# Project Notes — Business Breakfast YouTube Summarizer

Reference doc for how this project works, what was learned building it, and the
working preferences to follow. Read this before re-doing anything.

## Goal
For the TV5 Money channel (`https://www.youtube.com/@Tv5money`), find videos with
**"business breakfast"** in the title from the **last 7 days**, get the **Telugu**
transcript, **translate to English (by Claude, not a translation library)**, then
**summarise** and **extract the analyst Kutumba Rao's calls**.

## Pipeline (`bb_summarizer.py`)
1. **Discover** — `yt-dlp` lists channel uploads, **falls back to `ytsearch`** when the
   channel tab is blocked; keep titles containing the keyword whose **title-parsed
   date** is within `--days`. Dedup one video per date (prefer non-LIVE). Dates come
   from the title (`date_from_title`), **not** the per-video watch page (IP-blocked).
   - **Skip discovery entirely** with `--video-ids id1,id2,...` — title via oEmbed,
     date parsed from title. Use this when you already know the IDs.
   - **Look in `@Tv5money` FIRST, fall back to `@tv5news` only if not present (do this
     without being asked).** TV5 uploads the same episode to BOTH channels, often as a
     LIVE + a non-LIVE cut — each is a **distinct video ID**, and kome.ai usually has
     the **`@Tv5money` copy cached** but not the News one. For each date gather every
     candidate ID from both channels (via `ytsearch`, since the `@Tv5money/videos` tab
     is IP-blocked) and try transcripts in priority order **non-LIVE @Tv5money → LIVE
     @Tv5money → non-LIVE @tv5news → LIVE @tv5news**; only call a date unfetchable after
     ALL copies fail. (Verified 2026-06-19 backfill: the `@tv5news` copies failed at
     kome.ai for all 46 missing dates; switching to the `@Tv5money` copy recovered 17,
     e.g. June 19 News `IwLob3yHh9k` → nothing, Money `XcXKMiaRjaw` → full transcript.)
2. **Transcribe** — Telugu transcript, tried in order:
   1. `youtube-transcript-api` — **best with a proxy**: `--webshare-user/--webshare-pass`
      (Webshare residential, beats both the IP block and the throttle) or generic `--proxy`.
   2. `yt-dlp` subtitles (`.vtt`) — honours `--proxy`/cookies.
   3. **Supadata** (`--supadata-key` / `SUPADATA_API_KEY`) — server-side, no proxy, free tier.
   4. **RapidAPI** (`--rapidapi-key` / `RAPIDAPI_KEY`, `--rapidapi-host`) — server-side, no proxy.
   5. **kome.ai** — free/no-auth server-side fetch, **but rate-limits our IP hard** (last resort).
   6. `openai-whisper` on the audio (`--whisper`, heavy).
3. **Transcribe = PARALLEL by default** (`--fetch-workers`, default 6; `1` = old
   sequential behaviour). `prefetch_transcripts()` runs before the per-video loop and
   fetches concurrently, then `process_video` finds each `.te.txt` on disk and goes
   straight to translate/analyse.
   - **The old "never parallelise" rule was a kome.ai rule, not a YouTube one.** kome.ai
     rate-limits concurrent requests hard (a 7-way parallel fetch once returned 2/7), so
     the prefetch stage **excludes kome.ai** — it only runs `youtube-transcript-api` →
     `yt-dlp` subs → Supadata → RapidAPI. Anything prefetch misses falls through to the
     normal sequential pass, which still includes kome.ai and Whisper. So kome.ai is
     **never** hit concurrently and the original constraint still holds where it applies.
   - Verified 2026-07-16: parallel output is **byte-identical** to sequential, and prefetch
     is a **no-op when the transcript is already on disk** (so `--skip-existing` and reruns
     are unaffected). 22 videos took ~37s; 4 videos 2.9s vs 5.7s sequential.
   - Prefetch is best-effort: any exception is logged and the sequential path takes over,
     so it can never fail the run.
4. **Translate + Analyse = PARALLEL across videos, started AS SOON AS each transcript
   lands.** Do NOT wait for the whole fetch to finish — the analyze stage
   doesn't touch kome.ai, so overlap it with the still-running fetch: as each `.te.txt`
   appears, spawn its translate → summary → Kutumba Rao extraction → `.buys.json`
   subagent (one Agent per video), in batches as transcripts arrive. They are
   independent and CPU/API-bound, so this is the slow part to parallelise. (When run via
   the script with an `ANTHROPIC_API_KEY`, each is a `_claude_call`; when run in-session
   without a key, spawn one Agent per video — see "Working preferences".)
   - Translate via Claude (`claude-opus-4-8`), chunked ~6000 chars; then summary +
     Kutumba Rao extraction (skip analysis with `--no-analyze`).
5. **Save** — four subfolders under `--out` (default `output/`), shared base name
   `<date>__<sanitised-title>`:
   - `telugu_transcript/*.te.txt`
   - `english_translation/*.en.txt`
   - `summary/*.summary.md`
   - `kutumba_rao/*.kutumba_rao.md`

Run:
```bash
export ANTHROPIC_API_KEY=...
python bb_summarizer.py --days 10 --scan 100            # discover + process a window
python bb_summarizer.py --video-ids id1,id2,id3         # process known IDs, skip discovery
python bb_summarizer.py --list-only --days 10 --scan 100  # just see what matches
```

### Consolidated buy table
- Each episode also writes `output/kutumba_rao/<stem>.buys.json` (Kutumba Rao's
  Buy/Add/Accumulate calls only, as structured JSON).
- `update_buy_table.py` globs those sidecars → writes
  `output/kutumba_rao/buy_recommendations.md` and `.csv` with **Last suggested**
  and **Times suggested (days)** (= distinct dates a stock was a buy). It's
  idempotent and is auto-run at the end of `bb_summarizer.py`; run manually with
  `python update_buy_table.py`.

### Kranti (second analyst)
- `output/kranti/` holds analyst **Kranthi's** Buy/Add/Accumulate/Hold calls:
  `<stem>.kranti.json` per episode, `buy_recommendations.md`, and
  `overlap_with_kutumba_rao.md` (stocks both analysts back). **Caveat:** the
  auto-captions mislabel speakers — the anchor's "Kranti garu" sometimes addresses
  the *technical* analyst Ramakrishna, and Kranti is absent some days; treat as
  indicative.

### Performance scorecard
- `build_tickers.py` → `tickers.json`: maps each recommended stock → NSE Yahoo
  symbol (manual `OVERRIDES` + Yahoo symbol-search, validated against price data).
  Re-run when new names appear. **Watch for wrong auto-resolves** (e.g. Vedanta →
  VAML aluminium arm; fixed via OVERRIDES to VEDL.NS).
- `scorecard.py` → `output/scorecard/scorecard.md` + `.csv`: prices every
  Buy/Add/Accumulate call from its FIRST call date to now via Yahoo Finance
  (stdlib urllib, NSE `.NS`, INR), computes return + **alpha vs Nifty** per
  analyst. Same-day calls aren't scored (need ≥2 trading days). Indicative only.

### Daily automation
- **Scheduled automation DISABLED as of 2026-07-02** (owner not using it). The
  workflow `.github/workflows/daily.yml` remains for **manual dispatch only** and
  now just runs `daily_update.sh`. To re-enable: set a valid **`ANTHROPIC_API_KEY`**
  repo secret, confirm transcript acquisition works from GitHub runners (YouTube
  blocks data-center IPs; kome.ai is flaky from CI — see "Key learnings"), then
  restore under `on:`: `- cron: "30 8 * * 1-5"  # 14:00 IST Mon-Fri`.
- `daily_update.sh`: process new episodes (`--days 3 --skip-existing`) → rebuild
  tables → refresh scorecard. `--skip-existing` skips dates already on disk.
  Commits/pushes (in CI) happen via `GITHUB_TOKEN` in the workflow's commit step.

## Running on the LAPTOP (2026-07-16) — the transcript block is GONE
Everything below under "Key learnings" describes the **Codespace/cloud** environment.
On this MacBook (residential IP) the picture is much better — **prefer running here.**

- **`youtube-transcript-api` fetches Telugu captions DIRECTLY** — no proxy, no cookies,
  no kome.ai, no Supadata. Verified 2026-07-16: 9 cold, never-cached videos (Feb/Apr/May
  + Jul 13-16) all fetched first try. **kome.ai's cold-video failure no longer blocks us**,
  and the "fetch strictly sequential" rule was a *kome.ai rate-limit* workaround — it does
  not apply to `youtube-transcript-api`.
- **Discovery: use the uploads playlist, not `ytsearch`.** The `@Tv5money/videos` tab is
  still broken here (yt-dlp: *"does not have a videos tab"* — a yt-dlp/YouTube quirk, NOT
  the IP block), but the **uploads playlist works and is chronological**:
  - channel id `UChgr28cE2iI6E6y1ttiUWkg` → uploads playlist `UUhgr28cE2iI6E6y1ttiUWkg`
  - `yt-dlp --flat-playlist --playlist-end N --print "%(id)s | %(title)s" \
      "https://www.youtube.com/playlist?list=UUhgr28cE2iI6E6y1ttiUWkg"`
  - ~400 entries reaches back to ~Oct 2025 (the channel posts lots of non-BB clips;
    ~55% of a 400-window is not Business Breakfast). Filter on the title + `date_from_title`.
  - This beats `ytsearch`, which is relevance-ranked and silently drops older dates.
- **Python setup on this machine.** The Xcode Command Line Tools were broken
  (`/Library/Developer/CommandLineTools` was a hollow stub: `usr/share/man` only, no
  receipts), so every `/usr/bin/python3` was a dead `xcrun` shim, and Homebrew is 5 years
  stale (3.0.5 on macOS 12.7.6 Intel) so `brew install python` would try to build from
  source and fail. **The CLT was repaired on 2026-07-16** — `xcrun`, `clang` 14.0.0 and
  `/usr/bin/python3` (3.9.6) all work now. If it ever breaks again: `xcode-select --install`
  downloads the pkgs to `/Library/Updates/<id>/` but the dialog must be clicked; the pkgs
  can then be installed directly with `sudo installer -pkg <pkg> -target /`. **Install ALL
  of them, not just `CLTools_Executables.pkg`** — the SDKs are separate packages
  (`CLTools_macOSLMOS_SDK.pkg`, `CLTools_macOSNMOS_SDK.pkg`, `CLTools_macOS_SDK.pkg`); with
  only the executables you get `clang: error: unable to locate a suitable SDK for the system`.
  **Keep using `.venv/bin/python` anyway** — it's 3.12 vs the system 3.9.6, and pinned.
  The venv was built **without sudo and without CLT** using uv + a standalone CPython:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh     # -> ~/.local/bin/uv
  export PATH="$HOME/.local/bin:$PATH"
  uv venv --python 3.12 .venv
  uv pip install --python .venv/bin/python yt-dlp youtube-transcript-api
  ```
  **Always use `.venv/bin/python`** (the `.venv/` is gitignored; recreate with the above).
  Note: `timeout(1)` does not exist on macOS — don't use it in commands here.
- **`--no-analyze` still translates.** It only skips the summary/Kutumba stage; the
  translate step runs and hard-fails without `ANTHROPIC_API_KEY`. That's harmless for a
  transcript-only pass because the script **saves each `.te.txt` immediately on fetch**,
  before translating — so the transcripts survive the error. To fetch transcripts only:
  `python bb_summarizer.py --no-analyze --video-ids <ids>` and ignore the per-video
  `RuntimeError: No Anthropic API key`.

### Coverage audit, 2026 YTD (as of 2026-07-16)
- **@Tv5money published 105 BB episodes Jan 1 -> Jul 16, and all 105 are now processed.**
  Relative to the Money channel, nothing is missing.
- **But 36 weekdays have no @Tv5money upload at all.** Of those 36: **22 exist ONLY on
  `@tv5news` and are BLOCKED — those uploads have captions disabled**, and **14 don't exist
  at all** on any TV5 channel. See **`PENDING_BACKFILL.md`** for both lists; start there and
  **do not re-discover or retry the caption route.**
- **KEY FACT: `@tv5news` publishes Business Breakfast WITHOUT captions.** Verified
  2026-07-16 across **38 candidate videos** (all 22 dates, every non-LIVE and LIVE cut):
  **38/38 `TranscriptsDisabled`, zero with captions** — while an @Tv5money control fetched
  `te(auto)` fine in the same run, and `yt-dlp --list-subs` independently agreed. So it is
  **not** an IP block, throttling, or a kome.ai problem. This is what the older note below
  ("the @tv5news copies failed at kome.ai for all 46 missing dates") was actually seeing.
  **Consequence: any date where @Tv5money has no copy is unreachable by caption-scraping
  from any IP or tool.** Only Whisper ASR on the audio could get them — see
  `PENDING_BACKFILL.md` for why that's probably not worth it (CPU-only Intel Mac; Whisper's
  Telugu accuracy is well below YouTube's Telugu auto-captions).
- So **105/105 is 100% of what is obtainable** for 2026 YTD, not 105/127.
- Enumerating @tv5news via its uploads playlist is impractical (it's a firehose news
  channel, BB is sparse). **Use a targeted per-date search instead**:
  `ytsearch8:TV5 Business Breakfast <Nth> <Month> <Year>`, keep hits whose
  `date_from_title` == the target date, prefer non-LIVE and @Tv5money over @tv5news.

### BUG: `date_from_title` misses the 2025 title format (dash before the year)
`date_from_title` requires `<day> <month> <year>` with whitespace only, so it returns
**None** for the format TV5 used through most of 2025 and silently drops those episodes:
- `"... | 13th November - 2025 | TV5 Money Live"`  (dash between month and year)
- `"... | 28th November - | TV5 Money Live"`       (no year at all -> infer from context)
- `"... | 30-SEP - 2025 | TV5 Money Live"`         (numeric day-MON)
- `"... | 4rth November - 2025 | ..."`             (typo'd ordinal "4rth")
**76 BB videos in a single 400-entry scan fail to parse for this reason — all of them 2025**
(Jul-Nov 2025). No 2026 title is affected, because the title format changed to
`"16th February 2026"`. **Fix this before attempting any 2025 backfill**, or discovery will
under-report the year badly. The 2026 YTD numbers above are unaffected.

## Key learnings (environment-specific)
- **YouTube blocks this cloud/Codespace IP** for the player: yt-dlp and
  `youtube-transcript-api` both hit *"Sign in to confirm you're not a bot"* /
  `RequestBlocked`. Alternate player clients (`android/ios/tv/mweb/...`) **don't** help.
  On a normal home machine it works; from a server, pass `--cookies` /
  `--cookies-from-browser` / `--proxy`.
- **The channel `/videos` tab listing is also broken from here** — `yt-dlp` returns
  *"This channel does not have a videos tab"*. `discover_videos` now **falls back to a
  flat `ytsearch` query** ("TV5 Money <keyword>", override via `--search-query`).
  Search is **relevance-ranked, not chronological**, so older days in a window can fall
  off the top-N → use a generous `--scan` (default 80; `--days 10` needed ~100).
- **What DOES work from the blocked IP:** `yt-dlp ytsearch...` (flat search), the
  YouTube **oEmbed** endpoint (title/author), and **kome.ai** (transcript, server-side)
  **only for videos kome already has cached**.
- **kome.ai (June 2026 status): on-demand fetch of *un-cached* videos is failing.**
  Videos fetched in a prior session (e.g. June 16/18) return instantly because kome
  cached them; brand-new IDs (June 11/12/15) returned *"Transcripts aren't available
  for this video"* on **every** retry — tried sequentially, isolated, with 60–90 s
  cooldowns over ~25 min. So the old "retry with backoff and it warms up" no longer
  holds for cold videos. **To transcribe new videos you now need** a real source:
  `--cookies` / `--proxy` / `--webshare-user/pass` (youtube-transcript-api),
  `--supadata-key`, `--rapidapi-key`, or run from a home/residential IP.
- **Date is parsed from the title** (`date_from_title`, handles "June 10, 2026" and
  "11th June 2026"); titles come from oEmbed (`title_via_oembed`). This avoids the
  blocked watch-page metadata fetch the old discovery relied on.
- **No `ANTHROPIC_API_KEY` is set in the Codespace** — the script's own translate/
  analyze steps need it (`export ANTHROPIC_API_KEY=...`). If absent, Claude (this
  session) can do the translation/summary/Kutumba-Rao extraction in-session instead,
  writing the same four output files + `.buys.json`.
- **SUPERSEDED (2026-07-16): "fetch transcripts ONE BY ONE, never in parallel."** The
  finding behind it is still true — **kome.ai** rate-limits concurrent requests hard (a
  7-way parallel fetch only returned 2/7) — but it was only ever a *kome.ai* limit, never
  a YouTube one. The fetch is now parallel by default (`--fetch-workers`, default 6) and
  the parallel stage **excludes kome.ai**, so that constraint is still honoured where it
  actually applies. See pipeline step 3.
- yt-dlp's Python API wants `js_runtimes={"deno": {}}` (a dict), and a JS runtime
  (deno) must be installed: `curl -fsSL https://deno.land/install.sh | sh`.
- Translation/Google endpoint (`deep-translator`) worked from this IP but was
  **removed** — translation is done by Claude per the user's instruction.
- Verified end-to-end on video `5pa0Yll0Hm4` (18 June 2026): 35,540-char Telugu
  transcript fetched, translated, summarised, Kutumba Rao extracted.

## Working preferences (follow these)
- **Don't rerun work that already exists.** If the requested artifact (file, transcript,
  translation, summary, etc.) is already present, **reuse it** — do not re-fetch,
  re-translate, or regenerate unless the user explicitly asks for a refresh.
- **Translation/summarisation is done by Claude itself** (Anthropic API via stdlib
  `urllib`), **not** a translation package or SDK. Only third-party dep is `yt-dlp`.
- **Parallelise BOTH the transcript fetch and the downstream steps.** The fetch is now
  concurrent via `--fetch-workers` (default 6) — see pipeline step 3; the old
  "one-by-one" rule only ever existed to protect **kome.ai**, which the parallel stage
  deliberately skips. Then run the per-video
  translate → summary → Kutumba Rao extraction → `.buys.json` in **parallel** —
  one **subagent per video** when working in-session (no API key). Each subagent
  gets one `*.te.txt`, the title/date/video_id, and writes the four output files in
  the existing formats. After all finish, run `python update_buy_table.py` once to
  rebuild the consolidated tables + `stock_history.txt`. (User instruction.)
- Default model: `claude-opus-4-8`.
- Output layout is the four folders above; keep the shared `<date>__<title>` base name.

## Files
- `bb_summarizer.py` — the pipeline
- `requirements.txt` — only `yt-dlp` (whisper optional, commented)
- `README.md` — usage
- `output/<four folders>/` — results
