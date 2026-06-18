# Project Notes — Business Breakfast YouTube Summarizer

Reference doc for how this project works, what was learned building it, and the
working preferences to follow. Read this before re-doing anything.

## Goal
For the TV5 Money channel (`https://www.youtube.com/@Tv5money`), find videos with
**"business breakfast"** in the title from the **last 7 days**, get the **Telugu**
transcript, **translate to English (by Claude, not a translation library)**, then
**summarise** and **extract the analyst Kutumba Rao's calls**.

## Pipeline (`bb_summarizer.py`)
1. **Discover** — `yt-dlp` lists channel uploads; keep titles containing the keyword
   uploaded within `--days` (default 7).
2. **Transcribe** — Telugu transcript, tried in order:
   1. `youtube-transcript-api` — **best with a proxy**: `--webshare-user/--webshare-pass`
      (Webshare residential, beats both the IP block and the throttle) or generic `--proxy`.
   2. `yt-dlp` subtitles (`.vtt`) — honours `--proxy`/cookies.
   3. **Supadata** (`--supadata-key` / `SUPADATA_API_KEY`) — server-side, no proxy, free tier.
   4. **RapidAPI** (`--rapidapi-key` / `RAPIDAPI_KEY`, `--rapidapi-host`) — server-side, no proxy.
   5. **kome.ai** — free/no-auth server-side fetch, **but rate-limits our IP hard** (last resort).
   6. `openai-whisper` on the audio (`--whisper`, heavy).
3. **Translate** — Claude (`claude-opus-4-8`) via stdlib `urllib` → `_claude_call(system, user)`. Chunked ~6000 chars.
4. **Analyse** — Claude summary + Kutumba Rao extraction (skip with `--no-analyze`).
5. **Save** — four subfolders under `--out` (default `output/`), shared base name
   `<date>__<sanitised-title>`:
   - `telugu_transcript/*.te.txt`
   - `english_translation/*.en.txt`
   - `summary/*.summary.md`
   - `kutumba_rao/*.kutumba_rao.md`

Run: `export ANTHROPIC_API_KEY=...; python bb_summarizer.py --limit 1`

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
- **What DOES work from the blocked IP:** `yt-dlp ytsearch...` (flat search), the
  YouTube **oEmbed** endpoint (title/author), and **kome.ai** (transcript, server-side).
- **kome.ai throttles** — it fetches on demand and the first call often returns
  "Transcripts aren't available…"; **retry with backoff** (default 8 tries). Some
  videos genuinely have no captions.
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
- Default model: `claude-opus-4-8`.
- Output layout is the four folders above; keep the shared `<date>__<title>` base name.

## Files
- `bb_summarizer.py` — the pipeline
- `requirements.txt` — only `yt-dlp` (whisper optional, commented)
- `README.md` — usage
- `output/<four folders>/` — results
