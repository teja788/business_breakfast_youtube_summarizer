# Daily Business Breakfast runbook (no API key)

You are running unattended. Follow these steps exactly. Do NOT ask questions.
This runbook is executed by a Codex scheduled task, so Codex itself performs
translation and analysis without an API key. The Python pipeline is invoked with
`--transcript-only` to avoid launching a nested Codex/Claude CLI process.

Working directory: the repo root (this file's folder).

## Step 1 — Discover recent episodes

Run:

    .venv\Scripts\python.exe bb_summarizer.py --list-only --days 4 --scan 80

This prints lines like `2026-08-19  <video_id>  <title>`. Collect the (date, id).

## Step 2 — Find which dates are NEW

For each discovered date, check if this file already exists:

    output/english_translation/<date>__*.en.txt

Skip any date that already has an `.en.txt`. Keep only the NEW (date, id) pairs.
If there are no new episodes, write "no new episodes" to the log and STOP
(do not run post-processing, do not commit).

## Step 3 — Download Telugu transcripts for the new episodes

Run once with all new ids, comma-separated (no spaces):

    .venv\Scripts\python.exe bb_summarizer.py --transcript-only --video-ids <id1>,<id2>,... --days 4

Confirm a non-empty `output/telugu_transcript/<date>__*.te.txt` exists for every
new date. If a transcript is unavailable after all channel copies and configured
fallbacks, record the date and reason, continue with other dates, and report it.

## Step 4 — Translate and analyze directly as the scheduled Codex agent

For EACH new transcript, read it fully (in parts if necessary) and produce these
5 files. Use the most recent episode as the format template. The `<stem>` is the
transcript filename without `.te.txt`.

1. `output/english_translation/<stem>.en.txt`
   - 4 header lines: `# <title>`, `# Uploaded: <date>`, `# https://youtu.be/<id>`,
     `# Telugu -> English translation by Codex` (or `Claude Code`). Blank line. Then the full,
     faithful English translation. Preserve ALL numbers, tickers, company names,
     levels, prices. Do not summarize. Mark speakers `[Name:]` when identifiable
     (anchor Vasanth, Kutumba Rao, Kranthi, Ramakrishna).

2. `output/summary/<stem>.summary.md`
   - 3 header lines (title, Uploaded, url), blank line, then sections
     `## Global backdrop`, `## Indian markets`, `## Analysts/segments`,
     `## Note on stock calls`. Bullets, **bold** key items, keep all numbers.

3. `output/kutumba_rao/<stem>.kutumba_rao.md`
   - 3 header lines, blank line. State if Kutumba Rao is present/absent. Sections
     `## Market view` and `## Stock calls`. ATTRIBUTION IS CRITICAL: Kutumba Rao
     is ONE person; Kranthi, Vasanth (anchor), Ramakrishna (technical) are
     DIFFERENT people. Only attribute what the transcript explicitly gives him.
     Put other analysts' calls under a closing "## Closing note -- calls by OTHER
     analysts (NOT Kutumba Rao; excluded from buys.json)".

4. `output/kutumba_rao/<stem>.buys.json`
   - `{"date","video_id","title","recommendations":[...]}`. Each rec:
     `{"stock","action","price","note","detail"}`. action in
     Buy/Add/Accumulate/Hold/Avoid/Sell/Watch. ONLY Kutumba Rao's calls; empty
     array if absent/unnamed. Plain ASCII ("Rs", not the rupee sign).

5. `output/kranti/<stem>.kranti.json`
   - `{"date","analyst":"Kranthi","stem","calls":[...]}`. Each call:
     `{"stock","action","note"}`. action in
     Buy/Add/Accumulate/Hold/Avoid/Sell/Reduce/Book Profit/Watch. ONLY Kranthi's
     calls; empty array if absent. Plain ASCII.

## Step 5 — Post-processing (deterministic, no API key)

Run these IN ORDER. If any FAILS, stop and report — do not commit partial data.

    .venv\Scripts\python.exe build_tickers.py
    .venv\Scripts\python.exe update_buy_table.py
    .venv\Scripts\python.exe scorecard.py
    .venv\Scripts\python.exe build_dashboard_data.py

## Step 6 — Commit and push

    git add -A
    git commit -m "Add <dates> episode(s); refresh tables/scorecard/dashboard"
    git push origin HEAD:main

The local branch is `master`; the remote (and GitHub Pages) branch is `main`, so
push with `HEAD:main`. This must be a clean fast-forward — NEVER use `--force`.
If the push is rejected (remote moved ahead), stop and report; do not force.
If `git commit` says nothing to commit, skip the push. The push refreshes the
live dashboard (served from `docs/` on `main`).

## Done

Print a one-line summary: which dates were added and how many calls each analyst
gave.
