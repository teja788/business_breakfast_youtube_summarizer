# The 20 @tv5news gap dates — BLOCKED: captions disabled, not in kome.ai's cache

**Status: not recoverable by any caption route as of 2026-07-16.**

## Coverage (2026 YTD, as of 2026-07-16)

| | count |
|---|--:|
| Weekdays Jan 1 -> Jul 16 | 141 |
| **Episodes processed (on disk)** | **107** |
| Blocked — @tv5news only, no captions (this file) | 20 |
| No episode published anywhere | 14 |

107 + 20 + 14 = 141. **107 is 100% of what is obtainable.**

## What was tried (2026-07-16)

- **38 candidate videos** covering these dates (every preferred cut AND every
  alternate LIVE cut) checked with `youtube-transcript-api`: **all `TranscriptsDisabled`.**
- `yt-dlp --list-subs` agrees independently: *"has no automatic captions / has no subtitles"*.
- **kome.ai** (the one source the parallel prefetch skips) also returns **nothing** for them.
- **Control**: an @Tv5money video fetched `te(auto)` fine in the same run. So this is
  **not** an IP block, throttling, or a parallelism artifact.

## IMPORTANT: caption availability DECAYS — fetch promptly

`2026-06-10` (`-yKsVcjxO8s`) and `2026-06-17` (`bw3fAXMEZak`) are **@tv5news uploads
(channel `UCAR3h_9fLV82N2FH4cE4RKw`) that WERE fetched successfully on 2026-06-19** and
are on disk today. The same IDs now return `TranscriptsDisabled`.

So @tv5news copies are **not** inherently caption-less — what was reachable a month ago
is gone now. kome.ai still returns `-yKsVcjxO8s` **only because it cached it back then**
(it returns nothing for any date that was never fetched — consistent with the known
"kome.ai cannot fetch cold videos" behaviour).

**Consequence: transcripts are a wasting asset.** Episodes should be pulled while fresh.
The daily automation is currently DISABLED (see PROJECT_NOTES), so gaps like these 20
become permanent. Had they been fetched within ~a month of airing, they'd be here.

## The 20 blocked dates

| Date | Preferred ID | Cut | Alternate IDs |
|---|---|---|---|
| 2026-01-13 | `KQqf1DoI-iI` | non-LIVE | U2N3i6YtXrk |
| 2026-01-16 | `jOTXi2DN-o8` | non-LIVE | 65w3_VYeJ48 |
| 2026-01-22 | `h12Sw40oQmE` | LIVE | — |
| 2026-02-03 | `iWAYDRUbkVA` | non-LIVE | gGo_f2cubYM |
| 2026-02-04 | `7X0ulSkDMKg` | non-LIVE | — |
| 2026-02-05 | `ncuPWvbrtDQ` | LIVE | — |
| 2026-03-11 | `p7CMRDWlwhc` | non-LIVE | nEpNVbmrM48 |
| 2026-03-17 | `Gj3r0hgLbJM` | LIVE | — |
| 2026-03-20 | `fHiJ8tP4e3E` | non-LIVE | B_jnijfJ-ZY |
| 2026-03-23 | `M65-YhsaA2g` | non-LIVE | GYTmnkeIZ0M |
| 2026-04-22 | `EXiCad8kDbM` | non-LIVE | RBfwxZ7w9Hw |
| 2026-04-23 | `IWx04m5X6Po` | non-LIVE | Z1xQmn10dU4 |
| 2026-05-05 | `4YJ_aWnJpEs` | non-LIVE | 6hOJ1ezcIiM |
| 2026-05-14 | `UVAFAEbrD98` | non-LIVE | 0EBjZvWVxb8 |
| 2026-05-15 | `pjyttAYvQTU` | non-LIVE | cPWr9nQHJMM |
| 2026-06-11 | `Rbic6oFq1rE` | non-LIVE | w_fmcqmoPHs |
| 2026-06-12 | `-Dl4HOfKP2w` | LIVE | — |
| 2026-06-15 | `2Qm2F5-CitI` | non-LIVE | R92FitwqrxE |
| 2026-07-06 | `vkse2ln-qBg` | non-LIVE | Z25uO9yQzsI |
| 2026-07-10 | `iY0DjESYRco` | non-LIVE | — |

## Confirmed EMPTY — no episode exists at all (14 dates)

Searched with 3 title-format variants across both channels; nothing published:

`2026-01-01`, `2026-01-15`, `2026-01-26`, `2026-03-03`, `2026-03-26`, `2026-03-31`, `2026-04-03`, `2026-04-14`, `2026-05-01`, `2026-05-04`, `2026-05-28`, `2026-06-26`, `2026-07-07`, `2026-07-08`

Most align with likely NSE holidays (Jan 26 Republic Day, Mar 3 Holi, Apr 3 Good Friday,
Apr 14 Ambedkar Jayanti, May 1 Maharashtra Day) — **inferred, not checked against the
official NSE calendar**. **2026-07-07 / 07-08 have no holiday explanation.**

## Only remaining route: Whisper ASR

`bb_summarizer.py --whisper`. Honest assessment: ~20 x ~1h of audio on a **quad-core
Intel MacBook Air with no CUDA** (many hours to over a day), and Whisper's **Telugu**
accuracy is materially worse than YouTube's Telugu auto-captions — it would quietly
pollute the buy table and scorecard with a lower-fidelity tier of data.
**Recommendation: not worth it.** If attempted, tag the output as ASR-derived.
