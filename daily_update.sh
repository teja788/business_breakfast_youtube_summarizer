#!/usr/bin/env bash
# Daily Business Breakfast update: process any new episode(s), then refresh the
# consolidated buy table and the performance scorecard. Idempotent — already-done
# dates are skipped (--skip-existing). Safe to run manually or from CI/cron.
#
# Needs ANTHROPIC_API_KEY in the environment (the script's translate/analyze steps
# use it). yt-dlp needs a JS runtime (deno) on PATH.
set -uo pipefail
cd "$(dirname "$0")"

echo "== [1/4] discover + process new episodes (last 3 days, @Tv5money first) =="
python3 bb_summarizer.py --days 3 --scan 80 --skip-existing

echo "== [2/4] rebuild consolidated buy/recommendation tables =="
python3 update_buy_table.py || true

echo "== [3/4] refresh performance scorecard (re-prices all calls) =="
python3 scorecard.py || true

echo "== [4/4] rebuild web dashboard data (docs/data.json) =="
python3 build_dashboard_data.py || true

echo "== done =="
