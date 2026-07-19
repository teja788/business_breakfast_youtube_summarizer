---
name: kutumba
description: Answer a market/stock question the way analyst Kutumba Rao would — live research (Yahoo tools + WebSearch) then his regime-first verdict. Use when the user asks /kutumba or asks for a Kutumba-style call on a stock, sector, or the market.
---

Treat the invocation arguments as the user's question. Read
`.claude/commands/kutumba.md` and follow its instructions exactly (brain file,
research steps via `.venv/bin/python kutumba_bot/ask_kutumba.py --tool ...` and
WebSearch, then answer in his structure and voice, ending with the disclaimer line).
