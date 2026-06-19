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
2. **Transcribe** — Telugu transcript, tried in order:
   1. `youtube-transcript-api` — **best with a proxy**: `--webshare-user/--webshare-pass`
      (Webshare residential, beats both the IP block and the throttle) or generic `--proxy`.
   2. `yt-dlp` subtitles (`.vtt`) — honours `--proxy`/cookies.
   3. **Supadata** (`--supadata-key` / `SUPADATA_API_KEY`) — server-side, no proxy, free tier.
   4. **RapidAPI** (`--rapidapi-key` / `RAPIDAPI_KEY`, `--rapidapi-host`) — server-side, no proxy.
   5. **kome.ai** — free/no-auth server-side fetch, **but rate-limits our IP hard** (last resort).
   6. `openai-whisper` on the audio (`--whisper`, heavy).
3. **Transcribe = SEQUENTIAL, one video at a time** (kome.ai rate-limits concurrent
   requests hard). **Never parallelise the transcript fetch.**
4. **Translate + Analyse = PARALLEL across videos.** Once the transcripts are on disk,
   fan the per-video translate → summary → Kutumba Rao extraction → `.buys.json` out to
   **parallel subagents (one per video)**. They are independent and CPU/API-bound, so
   this is the slow part to parallelise. (When run via the script with an
   `ANTHROPIC_API_KEY`, each is a `_claude_call`; when run in-session without a key,
   spawn one Agent per video — see "Working preferences".)
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
- **Fetch transcripts ONE BY ONE, never in parallel** — kome.ai rate-limits
  concurrent requests hard (a 7-way parallel fetch only returned 2/7; sequential
  works). User preference.
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
- **Parallelise translation + downstream steps; keep transcript fetch sequential.**
  Fetch the Telugu transcripts one-by-one (kome.ai), then run the per-video
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
