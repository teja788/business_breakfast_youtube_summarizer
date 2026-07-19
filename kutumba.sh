#!/bin/bash
# Ask Kutumba from the terminal via Claude Code (Max-plan auth — NO API key needed).
#   ./kutumba.sh "Is Ather Energy still a buy at these levels?"
# Runs the /kutumba slash command headless; allows only the tools it needs.
set -euo pipefail
cd "$(dirname "$0")"
[ $# -ge 1 ] || { echo "usage: ./kutumba.sh \"your market/stock question\""; exit 1; }
exec claude -p "/kutumba $*" \
  --allowedTools "Read,WebSearch,Bash(.venv/bin/python kutumba_bot/ask_kutumba.py*)"
