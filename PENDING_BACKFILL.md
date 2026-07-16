# Pending backfill — 22 @tv5news episodes (2026 YTD)

**Status: NOT fetched.** Discovered and verified 2026-07-16; no transcripts pulled yet.

These are days the show aired but **@Tv5money never uploaded** — only `@tv5news` has a copy.
They are the dates the old kome.ai path could never fetch. From a laptop / residential IP,
`youtube-transcript-api` fetches them directly, so this is now unblocked.

All 22 were confirmed to be the **regular market show** (standard
`Business Breakfast | Stock/Share Market News | <date>` titling) — the one-off specials
(Nephrocare IPO, CII Summit) are deliberately excluded. 18 have a non-LIVE cut; 4 are LIVE-only.

## Ready-to-run

```bash
export PATH="$HOME/.local/bin:$PATH"   # see PROJECT_NOTES for the uv/.venv setup
# 1) transcripts only (each .te.txt is saved immediately; the trailing
#    'No Anthropic API key' RuntimeError per video is expected and harmless)
.venv/bin/python bb_summarizer.py --no-analyze --video-ids \
  KQqf1DoI-iI,jOTXi2DN-o8,h12Sw40oQmE,iWAYDRUbkVA,7X0ulSkDMKg,ncuPWvbrtDQ,p7CMRDWlwhc,Gj3r0hgLbJM,fHiJ8tP4e3E,M65-YhsaA2g,EXiCad8kDbM,IWx04m5X6Po,4YJ_aWnJpEs,UVAFAEbrD98,pjyttAYvQTU,-yKsVcjxO8s,Rbic6oFq1rE,-Dl4HOfKP2w,2Qm2F5-CitI,bw3fAXMEZak,vkse2ln-qBg,iY0DjESYRco
# 2) then translate/summarise/extract (one subagent per episode, per PROJECT_NOTES),
#    then: update_buy_table.py -> build_tickers.py -> scorecard.py -> build_dashboard_data.py
```

## The 22 episodes

| Date | Video ID (preferred) | Cut | Title | Alternate IDs |
|---|---|---|---|---|
| 2026-01-13 | `KQqf1DoI-iI` | non-LIVE | Business Breakfast | Stock Market News | January 13, 2026 | TV5 News | U2N3i6YtXrk |
| 2026-01-16 | `jOTXi2DN-o8` | non-LIVE | Business Breakfast | Stock/Share Market News | 16th January 2026 | TV5 News | 65w3_VYeJ48 |
| 2026-01-22 | `h12Sw40oQmE` | LIVE | LIVE : Business Breakfast | Stock/Share Market News | 22nd January 2026 | TV5 News | — |
| 2026-02-03 | `iWAYDRUbkVA` | non-LIVE | Business Breakfast | Stock/Share Market News | 3rd February 2026 | TV5 News | gGo_f2cubYM |
| 2026-02-04 | `7X0ulSkDMKg` | non-LIVE | Business Breakfast | Stock/Share Market News | 4th February 2026 | TV5 News | — |
| 2026-02-05 | `ncuPWvbrtDQ` | LIVE | LIVE : Business Breakfast | Stock/Share Market News | 5th February 2026 | TV5 News | — |
| 2026-03-11 | `p7CMRDWlwhc` | non-LIVE | Business Breakfast | Stock/Share Market News | 11th March 2026 | TV5 News | nEpNVbmrM48 |
| 2026-03-17 | `Gj3r0hgLbJM` | LIVE | LIVE : Business Breakfast | Stock/Share Market News | 17th March 2026 | TV5 News | — |
| 2026-03-20 | `fHiJ8tP4e3E` | non-LIVE | Business Breakfast | Stock/Share Market News | 20 March 2026 | TV5 News | B_jnijfJ-ZY |
| 2026-03-23 | `M65-YhsaA2g` | non-LIVE | Business Breakfast | Stock/Share Market News | 23 March 2026 | TV5 News | GYTmnkeIZ0M |
| 2026-04-22 | `EXiCad8kDbM` | non-LIVE | Business Breakfast | Stock/Share Market News | 22nd April 2026 | TV5 News | RBfwxZ7w9Hw |
| 2026-04-23 | `IWx04m5X6Po` | non-LIVE | Business Breakfast | Stock/Share Market News | 23rd April 2026 | TV5 News | Z1xQmn10dU4 |
| 2026-05-05 | `4YJ_aWnJpEs` | non-LIVE | Business Breakfast | Stock/Share Market News | 5th May 2026 | TV5 News | 6hOJ1ezcIiM |
| 2026-05-14 | `UVAFAEbrD98` | non-LIVE | Business Breakfast | Stock Market News | May 14, 2026 | TV5 News | 0EBjZvWVxb8 |
| 2026-05-15 | `pjyttAYvQTU` | non-LIVE | Business Breakfast | Stock/Share Market News | 15th May 2026 | TV5 News | cPWr9nQHJMM |
| 2026-06-10 | `-yKsVcjxO8s` | non-LIVE | Business Breakfast | Stock Market News | June 10, 2026 | TV5 Money | ewQPdQskfcE |
| 2026-06-11 | `Rbic6oFq1rE` | non-LIVE | Business Breakfast | Stock/Share Market News | 11th June 2026 | TV5 News | w_fmcqmoPHs |
| 2026-06-12 | `-Dl4HOfKP2w` | LIVE | LIVE : Business Breakfast | Stock/Share Market News | 12th June 2026 | TV5 News | — |
| 2026-06-15 | `2Qm2F5-CitI` | non-LIVE | Business Breakfast | Stock/Share Market News | 15th June 2026 | TV5 Money | R92FitwqrxE |
| 2026-06-17 | `bw3fAXMEZak` | non-LIVE | Business Breakfast | Stock Market News | June 17, 2026 | TV5 Money | 4fgCCXfunrw |
| 2026-07-06 | `vkse2ln-qBg` | non-LIVE | Business Breakfast | Stock Market News | July 6, 2026 | TV5 News | Z25uO9yQzsI |
| 2026-07-10 | `iY0DjESYRco` | non-LIVE | Business Breakfast | Stock/Share Market News | 10th July 2026 || TV5 News | — |

Note: Jun 10 / Jun 15 / Jun 17 say "TV5 Money" in the *title* but are uploaded on the
**TV5 News** channel — the @Tv5money uploads playlist genuinely never carried them.

## Confirmed EMPTY — do not chase (14 dates)

No Business Breakfast episode exists on **any** TV5 channel for these 2026 weekdays.
Each was searched with 3 title-format variants across both channels on 2026-07-16:

`2026-01-01`, `2026-01-15`, `2026-01-26`, `2026-03-03`, `2026-03-26`, `2026-03-31`, `2026-04-03`, `2026-04-14`, `2026-05-01`, `2026-05-04`, `2026-05-28`, `2026-06-26`, `2026-07-07`, `2026-07-08`

Most align with likely NSE holidays (Jan 26 Republic Day, Mar 3 Holi, Apr 3 Good Friday,
Apr 14 Ambedkar Jayanti, May 1 Maharashtra Day) — **inferred, not verified against the
official NSE calendar**. **2026-07-07 and 2026-07-08 have no holiday explanation**; the
show simply was not uploaded.

## Coverage arithmetic (as of 2026-07-16)

- 141 weekdays Jan 1 -> Jul 16
- 105 published by @Tv5money — **all 105 processed** (done, committed)
- 22 published by @tv5news only — **pending, this file**
- 14 never published anywhere — nothing to fetch
- => 127 of 127 published episodes once these 22 land.
