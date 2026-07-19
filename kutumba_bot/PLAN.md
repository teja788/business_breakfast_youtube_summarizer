# Kutumba Bot — Plan of Record

Goal: a CLI bot that **thinks like analyst Kutumba Rao** (TV5 Money "Business Breakfast").
It answers the user's free-form market/stock questions, **does its own live research
online**, and replies in his frame/voice with a clear verdict. His past calls are
**training material for his METHOD only** — the bot may contradict his old views.
NOT a lookup of his past stances.

## Decisions (user-confirmed 2026-07-19)
- **Data sources: BOTH** — (a) Anthropic server-side **web search tool** for news /
  results / qualitative; (b) **Yahoo Finance** for hard numbers (price, 52w range,
  history), reusing the plumbing in `scorecard.py` (`_series()`, v8 chart endpoint)
  and `build_tickers.py` (`yahoo_search()`, v1 search endpoint) + `tickers.json`
  (608 entries, name → NSE symbol + sector) for name→symbol resolution.
- **Interface (REVISED 2026-07-19): NO API key — Claude Max plan only** (user has no
  ANTHROPIC_API_KEY and wants subscription auth).
  - PRIMARY: `/kutumba <question>` slash command → `.claude/commands/kutumba.md`.
    Runs inside any Claude Code session (desktop app is Max-authenticated). Claude
    Code's engine reasons; built-in WebSearch researches; data tools via Bash:
    `.venv/bin/python kutumba_bot/ask_kutumba.py --tool market_context|stock_data "<name>"`.
  - OPTIONAL terminal one-shot: `./kutumba.sh "question"` wraps `claude -p "/kutumba ..."`.
    Needs one-time `npm install -g @anthropic-ai/claude-code` + `claude` browser login
    (CLI not yet installed on this machine — desktop app only).
  - The standalone API loop in ask_kutumba.py is KEPT but dormant (works if a key is
    ever exported); the file's `--tool` mode is what the Max-plan path uses.

## Architecture (3 components)
1. **The Brain** — `kutumba_bot/kutumba_brain.md`: distilled doctrine = system prompt.
   Built by 3 subagents mining `output/kutumba_rao/*.kutumba_rao.md` (116 episodes) by
   date slice, then synthesized. Sections: market-regime logic, macro thresholds,
   options/positioning reads, stock-evaluation checklist, risk rules, avoid/sell tells,
   sector themes, verbal tells ("value but no fancy", "exit on rallies", "hero or zero").
   **SYNTHESIS RULE (user directive 2026-07-19): method, never state.** The brain must
   contain his reusable CALIBRATIONS and decision procedures only — written as "how to
   derive today's X from fresh data" — NOT dated market anchors (no fixed Nifty levels,
   crude/rupee figures, sector-froth lists). Dated quotes in the distills are raw
   material to abstract FROM; a specific level may appear only as a worked illustration
   clearly marked as such. The bot derives each day's thresholds itself from research.
2. **Research tools** (agentic tool-use loop):
   - `web_search` — Anthropic native web search tool (server-side, cited).
   - `stock_data(name_or_symbol)` — resolve via tickers.json → else Yahoo v1 search
     (first .NS hit); fetch price now, 52w high/low, returns over 1w/1m/3m/1y via the
     v8 chart endpoint (adjclose). Optionally Nifty (^NSEI) for regime context.
3. **The agent loop** — `ask_kutumba.py`: system=Brain + answer contract (regime read
   first → verdict from his verb set Buy/Add/Accumulate/Hold/Avoid/Sell/Watch → his
   reasoning lenses → level+horizon+stop → "what would change my mind"). Tool-use loop
   via stdlib urllib POST to /v1/messages until end_turn.

## Status (complete as of 2026-07-19)
- [x] Corpus explored; scorecard reviewed (152 priced calls, 62% win, +8.0% alpha).
- [x] Distill Dec-2025→Feb-2026 → `kutumba_bot/distill_2025-12_2026-02.md`
- [x] Distill Mar→Apr 2026 → `kutumba_bot/distill_2026-03_2026-04.md` (full crash→recovery cycle)
- [x] Distill May→Jul 2026 → `kutumba_bot/distill_2026-05_2026-07.md`
- [x] Synthesized → `kutumba_bot/kutumba_brain.md` (method-only, no market state;
      10 sections: prime directive, identity, daily algorithm, regime machine,
      macro dashboard, options calibrations, 17-lens stock checklist, risk rules,
      rejection ladder, mental models/voice, answer contract)
- [x] `kutumba_bot/ask_kutumba.py` — data tools verified live; API loop dormant
- [x] `/kutumba` command + skill; `./kutumba.sh` wrapper (needs one-time CLI install)
- [x] Smoke-test of the flow (market question answered via tools + WebSearch in-session)
- [ ] (Optional later) eval: replay held-out episodes vs his actual calls / scorecard
- [ ] (Optional later) `npm i -g @anthropic-ai/claude-code` + login for terminal use

## Phase 2 — The Panel (started 2026-07-19)
User request: panel of **Charlie Munger, Rakesh Jhunjhunwala, Dolly Khanna** with
**Kutumba Rao as decision maker**. Same method-never-state rule for every brain.
- Brains in `kutumba_bot/panel/`: `munger_brain.md`, `jhunjhunwala_brain.md`,
  `dolly_khanna_brain.md` — distilled by web-research agents (each writes its own
  file). Dolly's sources: her blogspot https://dolly-bestpicks.blogspot.com/
  (real pick posts 2015-2026 with a formulaic "within 20% of CMP, 10-20%
  allocation" rule; authenticity unverified — caveat stated in doc) + disclosed
  >1% stakes via Trendlyne etc.
- Orchestration: `/panel` command (`.claude/commands/panel.md`, + skill) — shared
  research once, three independent voiced takes, Kutumba Rao weighs out loud and
  issues the final verdict in his answer contract.
- [x] 3 panel brains on disk (2026-07-19): munger 273 lines / jhunjhunwala 251 /
      dolly_khanna 265 — all research-grounded with cited sources, all
      method-never-state compliant. Panel COMPLETE; pending commit.

## Notes / risks
- Attribution noise: corpus already filtered to his-attributed content (ANALYZE_SPEC rules).
- Web search tool needs API access to server tools; if unavailable, fall back to
  DuckDuckGo-lite HTML fetch via urllib (flakier), or run search via yahoo news vertical.
- Track record context: 6-month bull tape; alpha (+8%) is the honest number.
- Personal-use tool; if ever shared publicly → SEBI RA territory, add disclaimers.
