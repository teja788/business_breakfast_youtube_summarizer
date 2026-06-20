# Analyze-spec — Business Breakfast transcript → 4 output files

You process ONE episode end-to-end. You are given: `STEM`, `DATE` (YYYY-MM-DD),
`VIDEO_ID`, `TITLE`. The working dir is the repo root
`/workspaces/business_breakfast_youtube_summarizer`. All paths below are relative to it.

## Input
Read the Telugu transcript at `output/telugu_transcript/<STEM>.te.txt`.
It is auto-generated captions (spelling noise, run-ons). The show is TV5 Money's
"Business Breakfast" — Indian stock-market morning show. The key analyst is
**Kutumba Rao** (fundamental/markets + viewer stock Q&A).

### CRITICAL — analyst attribution (read carefully)
**Kutumba Rao is ONE specific person.** These are DIFFERENT people and are NOT
Kutumba Rao: **Kranthi / Kranti** (a separate fundamental analyst — the project even
keeps his calls in a separate folder), **Vasanth** (anchor/analyst), **Ramakrishna**
(technical analyst). Do NOT treat Kranthi's, Vasanth's, or Ramakrishna's calls as
Kutumba Rao's, even if one of them is "the fundamental analyst answering viewer Q&A"
that day. The captions have NO speaker labels, so attribute conservatively:
- A stock call goes in `buys.json` ONLY if the transcript makes clear it is **Kutumba
  Rao's own** call (he is named/addressed and giving that view).
- If Kutumba Rao is **not named / not present** in the episode, then
  `"recommendations": []` — even if other analysts gave many calls. Capture those
  other-analyst calls in the prose `kutumba_rao.md` closing note for the human reader,
  but keep them OUT of buys.json.
- When genuinely unsure whether a call is his, EXCLUDE it from buys.json.

Derive `HUMANDATE` from DATE as `D Month YYYY` (no leading zero), e.g. 2026-01-06 →
`6 January 2026`. Derive `CH` = `TV5 Money` if TITLE contains "Money" (case-insensitive),
else `TV5 News`.

## Output files (write all four; create parent dirs as needed)

### 1. `output/english_translation/<STEM>.en.txt`
A faithful, complete Telugu→English translation (clear readable prose; preserve ALL
numbers, tickers, company names, and meaning; do NOT summarise/omit/add). Translate the
WHOLE transcript. Prefix this exact 4-line header + blank line, then the translation:
```
# <TITLE>
# Uploaded: <DATE>
# https://youtu.be/<VIDEO_ID>
# Telugu -> English translation by Claude (Opus 4.8)

<english translation>
```

### 2. `output/summary/<STEM>.summary.md`
Header then a structured markdown summary. Use sections like `## Global backdrop`,
`## Indian markets`, `## Analysts featured` with concise bullet points (bold the key
numbers/names). Match the depth of a daily market brief.
```
# Summary — Business Breakfast, <HUMANDATE> (<CH>)
# https://youtu.be/<VIDEO_ID>

<summary body>
```

### 3. `output/kutumba_rao/<STEM>.kutumba_rao.md`
Header then everything **Kutumba Rao** said: his market view, OI/levels, stocks he
flagged, and a `## Stock calls (viewer Q&A)` section with each stock + his
Buy/Hold/Add/Accumulate/Avoid/Watch verdict and reasoning. If some calls were answered
by other analysts, note that at the end.
```
# What Kutumba Rao said — Business Breakfast, <HUMANDATE> (<CH>)
# https://youtu.be/<VIDEO_ID>

<body>
```

### 4. `output/kutumba_rao/<STEM>.buys.json`
Structured sidecar of Kutumba Rao's stock calls (this feeds the consolidated buy table
and scorecard). JSON, UTF-8, 2-space indent:
```json
{
  "date": "<DATE>",
  "video_id": "<VIDEO_ID>",
  "title": "<TITLE>",
  "recommendations": [
    {
      "stock": "Company Name",
      "action": "Buy|Add|Accumulate|Hold|Avoid|Sell|Watch",
      "price": "level or target if he gave one, else \"\"",
      "note": "one-line gist",
      "detail": "2-4 sentence faithful paraphrase of what he said"
    }
  ]
}
```
Rules for buys.json:
- ONLY Kutumba Rao's own calls (not other analysts'). If a call is clearly his, include it.
- `action` must be one of the allowed verbs. "accumulate/add on dips" → `Add` or
  `Accumulate`; "hold" → `Hold`; "don't buy / better avoid / exit" → `Avoid` or `Sell`;
  "watch / keep on radar" → `Watch`; clear buy → `Buy`.
- Use plain ASCII (no rupee sign — write "Rs"); keep numbers exactly as stated.
- If he made no stock calls, use `"recommendations": []`.

## Quality bar
Faithful to the transcript, no invention. The translation must be complete. When done,
reply with just: `OK <DATE> — <n> recs` (n = number of recommendations).
