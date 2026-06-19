# Business Breakfast – TV5 Money Telugu → English

Finds **"Business Breakfast"** videos uploaded in the **last 7 days** on the
[TV5 Money](https://www.youtube.com/@Tv5money) YouTube channel, pulls the Telugu
transcript, translates it to **English**, and saves both versions.

## Pipeline

1. **Discover** – list recent channel uploads, keep titles containing
   `business breakfast` uploaded within `--days` (default 7).
2. **Transcribe** – Telugu transcript, tried in order:
   1. [`youtube-transcript-api`](https://github.com/jdepoix/youtube-transcript-api) (caption tracks)
   2. [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) subtitle download (`.vtt`)
   3. [`openai-whisper`](https://github.com/openai/whisper) on the audio (`--whisper`, slow)
3. **Translate** – Telugu → English via [`deep-translator`](https://github.com/nidhaloff/deep-translator) (Google), chunked.
4. **Save** – `output/<date>__<title>.te.txt` (original) and `.en.txt` (English).

## Install

```bash
pip install -r requirements.txt          # whisper is optional/heavy
# yt-dlp needs a JS runtime for YouTube – install deno once:
curl -fsSL https://deno.land/install.sh | sh
```

## ⚠️ YouTube access (important)

YouTube blocks unauthenticated requests from **data-center / cloud IPs**
(*"Sign in to confirm you're not a bot"* / `RequestBlocked`). On a normal **home
machine this runs as-is**. From a server / Codespace you must supply cookies or a
residential proxy:

```bash
# easiest: read cookies straight from your local browser
python bb_summarizer.py --cookies-from-browser chrome

# or export a Netscape cookies.txt (e.g. "Get cookies.txt" extension) and:
python bb_summarizer.py --cookies cookies.txt

# or route through a residential proxy
python bb_summarizer.py --proxy http://user:pass@host:port
```

## Usage

```bash
# 1) See which videos match, no transcript work
python bb_summarizer.py --list-only

# 2) Do ONE video end-to-end and print the English preview  ← start here
python bb_summarizer.py --limit 1

# 3) All matching videos from the last 7 days, Whisper fallback on
python bb_summarizer.py --whisper
```

Key flags: `--days 7`, `--keyword "business breakfast"`, `--scan 80`
(uploads/search hits to scan — raise for longer windows), `--limit N`,
`--out output`, `--whisper`/`--whisper-model`.

Discovery flags (the channel `/videos` tab is blocked from cloud IPs):
- `--video-ids id1,id2,...` — process specific videos, **skipping discovery**
  (title via oEmbed, date parsed from title).
- `--search-query "..."` — override the `ytsearch` fallback query used when the
  channel listing is blocked (default `"TV5 Money <keyword>"`).

Output English file looks like:

```
# Business Breakfast | Stock Market News | June 17, 2026 | TV5 Money
# Uploaded: 2026-06-17
# https://youtu.be/<id>

Hello and welcome to the Business Breakfast. Today the stock market started with
gains. The Sensex is trading up 250 points at 78,500 ...
```
