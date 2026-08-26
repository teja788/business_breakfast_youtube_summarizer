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
3. **Translate/analyze** – a logged-in local **Codex CLI** or **Claude Code CLI**
   directly, with no model API key. `--ai-backend auto` prefers Codex and falls
   back to Claude Code. The Anthropic API is available only when explicitly selected.
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

AI flags:

- `--ai-backend auto` — default; use logged-in Codex CLI, then Claude Code.
- `--ai-backend codex|claude` — require that specific local agent.
- `--agent-model <model>` — optional local CLI model override.
- `--ai-workers N` — concurrent translation calls (`--claude-workers` remains
  as a deprecated alias).
- `--ai-backend anthropic --api-key ...` — explicit legacy API mode. Merely
  setting `ANTHROPIC_API_KEY` does not switch the default to paid API calls.
- `--transcript-only` — fetch and save captions without launching another agent;
  used when a Codex scheduled task will translate and analyze directly.

Discovery flags (the channel `/videos` tab is blocked from cloud IPs):
- `--video-ids id1,id2,...` — process specific videos, **skipping discovery**
  (title via oEmbed, date parsed from title).
- `--search-query "..."` — override the `ytsearch` fallback query used when the
  channel listing is blocked (default `"TV5 Money <keyword>"`).

## Local daily automation (no API key)

A Windows Task Scheduler job can run the pipeline **without an
`ANTHROPIC_API_KEY`**. `bb_summarizer.py` now performs translation and analysis
through a logged-in Codex or Claude Code CLI by default.

- **`RUNBOOK_daily.md`** — the exact steps the unattended agent follows.
- **`daily_claude.ps1`** — wrapper: unsets `ANTHROPIC_API_KEY`, runs `claude -p`
  headless against the Claude subscription login, logs to `logs/`.
- Each run rebuilds the tables/scorecard/dashboard, commits, and
  **`git push origin HEAD:main`** (local branch `master` → remote/GitHub-Pages
  branch `main`), which refreshes the live dashboard served from `docs/`.

Register the task (run as the logged-in user, needs the PC awake and git
credentials cached):

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-NoProfile -ExecutionPolicy Bypass -File "D:\Ravi\Experiments\business_breakfast_summarizer\daily_claude.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At 4pm
Register-ScheduledTask -TaskName "BusinessBreakfastDaily" -Action $action -Trigger $trigger -Force
```

## Automation (GitHub Actions, disabled)

The daily scheduled automation is **disabled as of 2026-07-02** (not in use).
`.github/workflows/daily.yml` remains for **manual dispatch only** (Actions tab
→ "Run workflow"); it runs `daily_update.sh`. To re-enable the schedule, first
configure a non-interactive logged-in Codex/Claude Code CLI on the runner and
confirm transcript acquisition works there (YouTube blocks data-center IPs;
kome.ai is flaky from CI — see PROJECT_NOTES.md), then restore the cron line under `on:`:
`- cron: "30 8 * * 1-5"  # 14:00 IST Mon-Fri`.

Output English file looks like:

```
# Business Breakfast | Stock Market News | June 17, 2026 | TV5 Money
# Uploaded: 2026-06-17
# https://youtu.be/<id>

Hello and welcome to the Business Breakfast. Today the stock market started with
gains. The Sensex is trading up 250 points at 78,500 ...
```
