#!/usr/bin/env bash
# Daily Business Breakfast update: process any new episode(s), then refresh the
# consolidated buy table and the performance scorecard. Idempotent — already-done
# dates are skipped (--skip-existing). Safe to run manually or from CI/cron.
#
# Needs ANTHROPIC_API_KEY in the environment (the script's translate/analyze steps
# use it). yt-dlp needs a JS runtime (deno) on PATH.
# Fail loudly: a broken post-processing step must abort BEFORE we commit, so we
# never push stale/partial data as if it succeeded. (The price-fetching scripts
# handle transient Yahoo errors internally and still exit 0, so -e is safe here.)
set -euo pipefail
cd "$(dirname "$0")"

echo "== [1/5] discover + process new episodes (last 3 days, @Tv5money first) =="
python3 bb_summarizer.py --days 3 --scan 80 --skip-existing

echo "== [2/5] resolve tickers for any newly-recommended stocks (merge-preserve) =="
python3 build_tickers.py

echo "== [3/5] rebuild consolidated buy/recommendation tables =="
python3 update_buy_table.py

echo "== [4/5] refresh performance scorecard (re-prices all calls) =="
python3 scorecard.py

echo "== [5/5] rebuild web dashboard data (docs/data/*.json) =="
python3 build_dashboard_data.py

echo "== done =="
