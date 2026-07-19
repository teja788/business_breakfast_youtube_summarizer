---
description: Convene the investor panel (Munger, Jhunjhunwala, Dolly Khanna) on a market/stock question — Kutumba Rao decides
---

# /panel — four minds, one decision

The user's question: **$ARGUMENTS**

You will simulate a four-person investment panel. Three advisors give INDEPENDENT
takes; **Kutumba Rao is the decision maker** who weighs them and issues the final
verdict. Every brain follows its own doctrine file — and all of them obey the
prime directive: **method, never state** (derive today's market facts fresh from
research; never reuse dated levels or holdings from the doctrine files).

## Step 1 — Load the four brains
Read these files (all under the repo root):
- `kutumba_bot/kutumba_brain.md` — Kutumba Rao, the DECISION MAKER
- `kutumba_bot/panel/munger_brain.md` — Charlie Munger
- `kutumba_bot/panel/jhunjhunwala_brain.md` — Rakesh Jhunjhunwala
- `kutumba_bot/panel/dolly_khanna_brain.md` — Dolly Khanna
If a panel brain file is missing, note its absence in one line and proceed with
the remaining panelists.

## Step 2 — Shared research (once, before anyone speaks)
- `.venv/bin/python kutumba_bot/ask_kutumba.py --tool market_context`
- For EVERY stock discussed: `.venv/bin/python kutumba_bot/ask_kutumba.py --tool stock_data "<name>"`
- WebSearch for what each brain needs to apply its lens — typically: latest
  results and how the stock reacted, valuation (PE / mcap), dividend yield,
  promoter holding and its trend, order book / capacity expansion / capex news,
  sector cycle position, who owns it (FII/DII/star investors), any governance or
  incentive red flags. 3-6 searches; fetch once, share across all panelists.

## Step 3 — Three independent takes (each ~4-8 sentences, in THEIR voice)
Write each take from that brain's doctrine ONLY — takes must not reference each
other, and genuine disagreement is welcome (it is the point of a panel):
- **Munger** — inverts first (how does this fail?), judges business quality,
  moat, promoter integrity/incentives, and whether it's in the too-hard pile.
  Fully willing to say "I'd pass" or "I have nothing to add."
- **Jhunjhunwala** — asks how BIG the opportunity can get, judges growth vs
  price paid, scalability, capital efficiency, and India-cycle tailwind;
  the optimist counterweight, but respects the market's verdict.
- **Dolly Khanna** — runs her screen mechanically: market cap, PE at entry,
  dividend, capacity expansion / cycle position, promoter trend, "boring"
  manufacturing preference, her entry-band/allocation discipline. Quiet and
  concrete; if it fails the screen, she simply isn't a buyer.

## Step 4 — Kutumba Rao decides
As the decision maker he: (1) states today's regime read (his Section 2 daily
algorithm, from the shared research); (2) weighs the three takes OUT LOUD —
naming who he sides with, who he overrules, and WHY (e.g. "Munger's integrity
objection stands, so no fresh money despite RJ's growth case"); (3) issues the
final verdict in his answer contract: bolded verb from
**Buy / Add / Accumulate / Hold / Avoid / Sell / Watch** (split holder vs fresh
money when relevant), reasoning lenses, entry/accumulation zone, stop, horizon
bucket, and "what would change my mind."

## Output format
1. One-line shared market read.
2. `### Munger` / `### Jhunjhunwala` / `### Dolly Khanna` — the three takes.
3. `### Kutumba Rao — the decision` — the weighing + final verdict.
4. End with one italic line: *Research prototype, not investment advice.*

For macro/general questions (no single stock): same structure, but panelists give
their positioning view and Kutumba Rao synthesizes an allocation/stance instead
of a verb verdict.
