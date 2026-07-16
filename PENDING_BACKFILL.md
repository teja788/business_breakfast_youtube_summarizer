# The 22 @tv5news gap dates — BLOCKED: captions are disabled

**Status: NOT recoverable via any transcript API. Do not retry the caption route.**

## What was tried and what happened (2026-07-16)

These 22 dates are days Business Breakfast aired but **@Tv5money never uploaded** —
only `@tv5news` has a copy. The episodes are real and the video IDs below are correct.
**But every @tv5news copy has its caption track disabled**, so there is nothing for a
transcript API to fetch:

- **38 candidate videos** (all 22 dates, every preferred cut AND every alternate LIVE
  cut) were checked with `youtube-transcript-api`: **38/38 `TranscriptsDisabled`, 0 with captions.**
- Cross-checked independently with `yt-dlp --list-subs`: *"Rbic6oFq1rE has no automatic
  captions / has no subtitles"*.
- **Control in the same run**: @Tv5money `yJKgJAswL6A` returned `te(auto)` fine, and
  `yt-dlp` listed a full Telugu auto-caption track. So this is **not** an IP block, not
  rate limiting, and not a parallelism artifact — the @tv5news uploads simply have no captions.

This retroactively explains the note in PROJECT_NOTES that "the @tv5news copies failed at
kome.ai for all 46 missing dates; switching to the @Tv5money copy recovered 17". That was
never kome.ai being flaky — **@tv5news publishes without captions.** Any date where
@Tv5money has no copy is therefore unreachable by caption-scraping, from ANY IP or tool.

## The only remaining route: Whisper ASR on the audio

`bb_summarizer.py --whisper` transcribes downloaded audio instead of fetching captions.
Honest cost/benefit before anyone tries it:

- ~22 episodes x ~1 hour of audio each. This machine is a **quad-core Intel MacBook Air,
  no CUDA** — whisper runs on CPU at roughly real-time or worse, so realistically **many
  hours to over a day** of compute, plus ~22 audio downloads.
- Whisper's **Telugu** accuracy is materially worse than YouTube's own Telugu
  auto-captions, and the whole downstream product (analyst attribution, stock names,
  price levels) depends on transcript fidelity. Expect a noticeably lower-quality tier
  of data than the other 105 episodes, which would silently pollute the buy table and scorecard.
- Recommendation: **not worth it** unless these specific dates matter a lot. If it is
  attempted, tag the output so it is distinguishable from caption-derived episodes.

## The 22 dates (IDs verified correct; captions absent)

| Date | Preferred ID | Cut | Alternate IDs | Captions |
|---|---|---|---|---|
| 2026-01-13 | `KQqf1DoI-iI` | non-LIVE | U2N3i6YtXrk | none |
| 2026-01-16 | `jOTXi2DN-o8` | non-LIVE | 65w3_VYeJ48 | none |
| 2026-01-22 | `h12Sw40oQmE` | LIVE | — | none |
| 2026-02-03 | `iWAYDRUbkVA` | non-LIVE | gGo_f2cubYM | none |
| 2026-02-04 | `7X0ulSkDMKg` | non-LIVE | — | none |
| 2026-02-05 | `ncuPWvbrtDQ` | LIVE | — | none |
| 2026-03-11 | `p7CMRDWlwhc` | non-LIVE | nEpNVbmrM48 | none |
| 2026-03-17 | `Gj3r0hgLbJM` | LIVE | — | none |
| 2026-03-20 | `fHiJ8tP4e3E` | non-LIVE | B_jnijfJ-ZY | none |
| 2026-03-23 | `M65-YhsaA2g` | non-LIVE | GYTmnkeIZ0M | none |
| 2026-04-22 | `EXiCad8kDbM` | non-LIVE | RBfwxZ7w9Hw | none |
| 2026-04-23 | `IWx04m5X6Po` | non-LIVE | Z1xQmn10dU4 | none |
| 2026-05-05 | `4YJ_aWnJpEs` | non-LIVE | 6hOJ1ezcIiM | none |
| 2026-05-14 | `UVAFAEbrD98` | non-LIVE | 0EBjZvWVxb8 | none |
| 2026-05-15 | `pjyttAYvQTU` | non-LIVE | cPWr9nQHJMM | none |
| 2026-06-10 | `-yKsVcjxO8s` | non-LIVE | ewQPdQskfcE | none |
| 2026-06-11 | `Rbic6oFq1rE` | non-LIVE | w_fmcqmoPHs | none |
| 2026-06-12 | `-Dl4HOfKP2w` | LIVE | — | none |
| 2026-06-15 | `2Qm2F5-CitI` | non-LIVE | R92FitwqrxE | none |
| 2026-06-17 | `bw3fAXMEZak` | non-LIVE | 4fgCCXfunrw | none |
| 2026-07-06 | `vkse2ln-qBg` | non-LIVE | Z25uO9yQzsI | none |
| 2026-07-10 | `iY0DjESYRco` | non-LIVE | — | none |

Jun 10 / Jun 15 / Jun 17 say "TV5 Money" in the *title* but are uploaded on the
**TV5 News** channel — the @Tv5money uploads playlist genuinely never carried them.

## Confirmed EMPTY — no episode exists at all (14 dates)

Searched with 3 title-format variants across both channels; nothing published:

`2026-01-01`, `2026-01-15`, `2026-01-26`, `2026-03-03`, `2026-03-26`, `2026-03-31`, `2026-04-03`, `2026-04-14`, `2026-05-01`, `2026-05-04`, `2026-05-28`, `2026-06-26`, `2026-07-07`, `2026-07-08`

Most align with likely NSE holidays (Jan 26 Republic Day, Mar 3 Holi, Apr 3 Good Friday,
Apr 14 Ambedkar Jayanti, May 1 Maharashtra Day) — **inferred, not checked against the
official NSE calendar**. **2026-07-07 / 07-08 have no holiday explanation.**

## Coverage (as of 2026-07-16)

- 141 weekdays Jan 1 -> Jul 16
- **105 published by @Tv5money — all 105 processed.** This is 100% of what is
  obtainable via captions.
- 22 published by @tv5news only — **blocked, captions disabled** (Whisper-only)
- 14 never published anywhere — nothing to fetch
