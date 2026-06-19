#!/usr/bin/env python3
"""
Business Breakfast (TV5 Money) – Telugu YouTube transcript -> English translator.

Pipeline
--------
1. DISCOVER : list a channel's recent uploads, keep only videos whose title
              contains a keyword (default "business breakfast") and that were
              uploaded within the last N days (default 7).
2. TRANSCRIBE: get the Telugu transcript for a video. Tries, in order:
                 a) youtube-transcript-api (fastest, uses caption tracks)
                 b) yt-dlp subtitle download (auto/manual .vtt)
                 c) Whisper on the downloaded audio   (--whisper)
3. TRANSLATE : Telugu -> English with deep-translator (Google), chunked.
4. SAVE      : write <date>__<title>.te.txt (original) and .en.txt (English).

NOTE ON ACCESS
--------------
YouTube blocks unauthenticated requests from data-center / cloud IPs
("Sign in to confirm you're not a bot" / RequestBlocked). On a normal home
machine this script works as-is. From a server/codespace you MUST supply
either browser cookies or a residential proxy:

    --cookies cookies.txt           (Netscape cookie file exported from your browser)
    --cookies-from-browser chrome   (read cookies directly from a local browser)
    --proxy http://user:pass@host:port

Examples
--------
    # Just see which videos match (no transcript work):
    python bb_summarizer.py --list-only --cookies cookies.txt

    # Do ONE video end-to-end and print it (what we demo first):
    python bb_summarizer.py --limit 1 --cookies cookies.txt

    # All matching videos from the last 7 days, with Whisper fallback:
    python bb_summarizer.py --whisper --cookies cookies.txt
"""
from __future__ import annotations

import argparse
import datetime as dt
import http.cookiejar
import re
import sys
import textwrap
from pathlib import Path

# ---- third-party ----------------------------------------------------------
# Only yt-dlp is third-party. Translation is done by Claude itself (Anthropic
# API) over a plain stdlib HTTPS call — no translation package, no SDK.
import yt_dlp

DEFAULT_CHANNEL = "https://www.youtube.com/@Tv5money/videos"
# @tv5news reuploads the same Business Breakfast episodes and, unlike @Tv5money,
# its /videos tab is still listable from blocked data-centre IPs.
DEFAULT_NEWS_CHANNEL = "https://www.youtube.com/@tv5news/videos"
DEFAULT_KEYWORD = "business breakfast"
DEFAULT_MODEL = "claude-opus-4-8"  # Anthropic's most capable Opus-tier model


# ===========================================================================
# helpers
# ===========================================================================
def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\s.-]", "", name).strip()
    name = re.sub(r"\s+", "_", name)
    return name[:120]


def parse_upload_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


def date_from_title(title: str) -> dt.date | None:
    """Parse the broadcast date out of a TV5 title.

    Handles both 'June 10, 2026' and '11th June 2026' / '18th June 2026'.
    """
    t = title.replace(",", " ")
    # "<month> <day> <year>"  e.g. June 10 2026
    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})", t)
    if m and m.group(1).lower() in _MONTHS:
        return dt.date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
    # "<day> <month> <year>"  e.g. 11th June 2026
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", t)
    if m and m.group(2).lower() in _MONTHS:
        return dt.date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
    return None


def title_via_oembed(video_id: str) -> str | None:
    """Fetch a video's title via YouTube's oEmbed endpoint (works from blocked IPs)."""
    import json as _json
    import urllib.request
    url = ("https://www.youtube.com/oembed?format=json&url="
           f"https://www.youtube.com/watch?v={video_id}")
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return _json.loads(resp.read().decode("utf-8")).get("title")
    except Exception as exc:  # noqa: BLE001
        log(f"[oembed] {video_id}: {type(exc).__name__}: {str(exc)[:100]}")
        return None


def videos_from_ids(ids: list[str]) -> list[dict]:
    """Build video dicts from explicit IDs, bypassing the (often blocked) discovery.

    Title comes from oEmbed; broadcast date is parsed from the title.
    """
    videos: list[dict] = []
    for vid in ids:
        title = title_via_oembed(vid) or vid
        date = date_from_title(title)
        if not date:
            log(f"[ids] could not parse date from title {title!r}; using today")
            date = dt.date.today()
        videos.append({"id": vid, "title": title, "upload_date": date,
                       "candidates": [_candidate(vid, title)]})
    return videos


# ===========================================================================
# yt-dlp configuration (cookies / proxy shared everywhere)
# ===========================================================================
def base_ydl_opts(args) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "js_runtimes": {"deno": {}},  # yt-dlp now needs a JS runtime for YouTube
    }
    if args.cookies:
        opts["cookiefile"] = args.cookies
    if args.cookies_from_browser:
        opts["cookiesfrombrowser"] = (args.cookies_from_browser,)
    if args.proxy:
        opts["proxy"] = args.proxy
    return opts


# ===========================================================================
# 1. DISCOVER
# ===========================================================================
def _flat_entries(source: str, args, scan: int | None = None) -> list[dict]:
    """Run a cheap extract_flat listing on a channel URL or an ``ytsearchN:`` query."""
    flat_opts = base_ydl_opts(args) | {
        "extract_flat": "in_playlist",
        "playlistend": scan or args.scan,
    }
    try:
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(source, download=False)
        return [e for e in ((info or {}).get("entries") or []) if e]
    except Exception as exc:  # noqa: BLE001
        log(f"[discover] flat listing failed for {source!r}: {type(exc).__name__}")
        return []


# --- Candidate ranking -------------------------------------------------------
# TV5 uploads the SAME episode to @Tv5money AND @tv5news, often as a LIVE + a
# non-LIVE cut — each a distinct video ID. kome.ai usually has the @Tv5money
# copy cached but not the News one, so for every date we keep ALL candidate IDs
# and try transcripts in priority order: non-LIVE Money -> LIVE Money ->
# non-LIVE News -> LIVE News.
_CHANNEL_RANK = {"money": 0, "news": 1, "other": 2}


def _channel_of(title: str) -> str:
    t = (title or "").lower()
    if "money" in t:
        return "money"
    if "news" in t:
        return "news"
    return "other"


def _candidate(vid: str, title: str) -> dict:
    return {"id": vid, "title": title or vid,
            "is_live": "live" in (title or "").lower(),
            "channel": _channel_of(title)}


def _candidate_rank(c: dict) -> tuple:
    return (_CHANNEL_RANK.get(c["channel"], 2), 1 if c["is_live"] else 0)


def _search_queries(args) -> list[str]:
    if args.search_query:
        return [args.search_query]
    # Two queries surface both channels' copies (each has its own video ID).
    return [f"TV5 Money {args.keyword}", f"TV5 News {args.keyword}"]


def discover_videos(args) -> list[dict]:
    """Return one dict per broadcast date, each with a ranked ``candidates`` list.

    Each match is ``{upload_date, id, title, candidates:[{id,title,is_live,channel}]}``
    where ``id``/``title`` are the top-ranked candidate. Unlike the old version
    (which stopped at the first source and kept one ID per date), this gathers IDs
    from BOTH channels so a date's @Tv5money copy can be tried before the @tv5news
    one. Dating uses :func:`date_from_title` (the watch page is IP-blocked).
    """
    keyword = args.keyword.lower()
    cutoff = dt.date.today() - dt.timedelta(days=args.days)

    # Gather from every source (don't stop early) so both channels' copies appear.
    raw: list[dict] = []
    log(f"[discover] listing {args.channel} ...")
    raw += _flat_entries(args.channel, args)  # primary channel (often blocked)
    if args.news_channel:
        news_scan = max(args.scan, args.days * 150)
        log(f"[discover] deep-scanning {args.news_channel} (up to {news_scan}) ...")
        raw += _flat_entries(args.news_channel, args, scan=news_scan)
    for q in _search_queries(args):
        log(f"[discover] ytsearch {q!r} ...")
        raw += _flat_entries(f"ytsearch{args.scan}:{q}", args)

    # Keyword filter + dedup by video id (a single episode may surface many times).
    by_id: dict[str, str] = {}
    for e in raw:
        vid, title = e.get("id"), e.get("title") or ""
        if vid and keyword in title.lower():
            by_id.setdefault(vid, title)
    log(f"[discover] {len(by_id)} unique video id(s) contain '{args.keyword}'.")

    # Group candidates by title-parsed date within the window; rank within a date.
    by_date: dict[dt.date, list[dict]] = {}
    for vid, title in by_id.items():
        date = date_from_title(title)
        if not (date and date >= cutoff):
            continue
        by_date.setdefault(date, []).append(_candidate(vid, title))

    matches = []
    for date in sorted(by_date, reverse=True):
        cands = sorted(by_date[date], key=_candidate_rank)
        top = cands[0]
        matches.append({"upload_date": date, "id": top["id"],
                        "title": top["title"], "candidates": cands})
    n_alt = sum(len(m["candidates"]) - 1 for m in matches)
    log(f"[discover] {len(matches)} date(s) in last {args.days} days "
        f"({n_alt} alternate copies available across channels).")
    return matches


# ===========================================================================
# 2. TRANSCRIBE  (three strategies, tried in order)
# ===========================================================================
def _cookie_session(args):
    """A requests.Session preloaded with cookies, for youtube-transcript-api."""
    import requests
    sess = requests.Session()
    if args.cookies:
        jar = http.cookiejar.MozillaCookieJar(args.cookies)
        jar.load(ignore_discard=True, ignore_expires=True)
        sess.cookies = jar
    return sess


def transcript_via_api(video_id: str, args) -> str | None:
    """Strategy a) youtube-transcript-api – prefers Telugu, else any track.

    A Webshare residential proxy (``--webshare-user/--webshare-pass``) is the most
    reliable way past YouTube's data-centre IP block *and* its throttle; a generic
    ``--proxy`` URL works too. Without a proxy this is still attempted (works on a
    home IP) but will likely be RequestBlocked from a server."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig
    except ImportError:
        return None

    proxy_cfg = None
    if args.webshare_user and args.webshare_pass:
        proxy_cfg = WebshareProxyConfig(
            proxy_username=args.webshare_user, proxy_password=args.webshare_pass)
    elif args.proxy:
        proxy_cfg = GenericProxyConfig(http_url=args.proxy, https_url=args.proxy)

    try:
        api = YouTubeTranscriptApi(
            proxy_config=proxy_cfg,
            http_client=_cookie_session(args) if (args.cookies) else None,
        )
        # Prefer Telugu; fall back to whatever exists.
        fetched = api.fetch(video_id, languages=["te", "en", "hi"])
        text = " ".join(snip.text for snip in fetched)
        if text.strip():
            log("[transcript] got captions via youtube-transcript-api")
            return text
    except Exception as exc:  # noqa: BLE001
        log(f"[transcript] api strategy failed: {type(exc).__name__}: {str(exc)[:120]}")
    return None


def transcript_via_ytdlp_subs(video_id: str, args) -> str | None:
    """Strategy b) download .vtt subtitles with yt-dlp and strip the markup."""
    out_dir = Path(args.out) / "_subs"
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = base_ydl_opts(args) | {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["te", "en", "hi"],
        "subtitlesformat": "vtt",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as exc:  # noqa: BLE001
        log(f"[transcript] yt-dlp subs failed: {type(exc).__name__}")
        return None

    for vtt in sorted(out_dir.glob(f"{video_id}*.vtt")):
        text = _vtt_to_text(vtt.read_text(encoding="utf-8", errors="ignore"))
        if text.strip():
            log(f"[transcript] got captions via yt-dlp ({vtt.name})")
            return text
    return None


def _vtt_to_text(vtt: str) -> str:
    lines, seen = [], set()
    for line in vtt.splitlines():
        line = line.strip()
        if (not line or line.startswith(("WEBVTT", "Kind:", "Language:"))
                or "-->" in line or line.isdigit()):
            continue
        line = re.sub(r"<[^>]+>", "", line)  # inline timing tags
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return " ".join(lines)


def transcript_via_whisper(video_id: str, args) -> str | None:
    """Strategy c) download audio with yt-dlp, transcribe with Whisper."""
    try:
        import whisper
    except ImportError:
        log("[transcript] whisper not installed (pip install openai-whisper); skipping")
        return None

    audio_dir = Path(args.out) / "_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{video_id}.mp3"
    opts = base_ydl_opts(args) | {
        "format": "bestaudio/best",
        "outtmpl": str(audio_dir / "%(id)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as exc:  # noqa: BLE001
        log(f"[transcript] audio download failed: {type(exc).__name__}")
        return None

    if not audio_path.exists():
        return None
    log(f"[transcript] transcribing with Whisper '{args.whisper_model}' (this is slow) ...")
    model = whisper.load_model(args.whisper_model)
    result = model.transcribe(str(audio_path), language="te")
    return (result.get("text") or "").strip() or None


def transcript_via_kome(video_id: str, args) -> str | None:
    """Strategy (no-auth, works from cloud IPs): kome.ai fetches server-side.
    It throttles / fetches on-demand, so retry a few times with backoff."""
    import json as _json
    import time
    import urllib.request
    url = "https://kome.ai/api/transcript"
    for attempt in range(1, args.kome_retries + 1):
        try:
            req = urllib.request.Request(
                url,
                data=_json.dumps({"video_id": video_id, "format": True}).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            text = _json.load(urllib.request.urlopen(req, timeout=45)).get("transcript", "")
            if text and "aren't available" not in text:
                log(f"[transcript] got transcript via kome.ai (attempt {attempt})")
                return text
        except Exception as exc:  # noqa: BLE001
            log(f"[transcript] kome.ai attempt {attempt} error: {type(exc).__name__}")
        time.sleep(5)
    return None


def transcript_via_supadata(video_id: str, args) -> str | None:
    """Strategy (server-side, no proxy needed): supadata.ai transcript API.
    Free tier; needs --supadata-key (or SUPADATA_API_KEY). Supadata is async:
    the submit returns a jobId, then we poll until the job completes. A browser
    User-Agent is required on every call (else Cloudflare error 1010)."""
    import json as _json
    import os
    import time
    import urllib.parse
    import urllib.request
    key = args.supadata_key or os.environ.get("SUPADATA_API_KEY")
    if not key:
        return None
    hdr = {"x-api-key": key, "User-Agent": "Mozilla/5.0"}

    def _get(url):
        return _json.load(urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=60))

    def _content(d):
        c = d.get("content")
        if isinstance(c, list):
            c = " ".join(x.get("text", "") for x in c)
        return c if (isinstance(c, str) and c.strip()) else None

    try:
        qs = urllib.parse.urlencode({"url": f"https://youtu.be/{video_id}", "lang": "te", "text": "true"})
        data = _get(f"https://api.supadata.ai/v1/transcript?{qs}")
        # Synchronous result?
        c = _content(data)
        if c:
            log("[transcript] got transcript via supadata.ai (sync)")
            return c
        # Async job: poll until completed.
        job = data.get("jobId")
        if not job:
            return None
        for _ in range(40):
            time.sleep(4)
            d = _get(f"https://api.supadata.ai/v1/transcript/{job}")
            status = d.get("status")
            if status in ("completed", "complete", "done"):
                c = _content(d)
                if c:
                    log("[transcript] got transcript via supadata.ai (job)")
                return c
            if status in ("failed", "error"):
                log(f"[transcript] supadata job failed: {str(d)[:120]}")
                return None
    except Exception as exc:  # noqa: BLE001
        log(f"[transcript] supadata failed: {type(exc).__name__}: {str(exc)[:120]}")
    return None


def transcript_via_rapidapi(video_id: str, args) -> str | None:
    """Strategy (server-side, no proxy needed): a RapidAPI transcript endpoint.
    Needs --rapidapi-key (or RAPIDAPI_KEY); host defaults to youtube-transcript3."""
    import json as _json
    import os
    import urllib.parse
    import urllib.request
    key = args.rapidapi_key or os.environ.get("RAPIDAPI_KEY")
    if not key:
        return None
    host = args.rapidapi_host
    qs = urllib.parse.urlencode({"url": f"https://youtu.be/{video_id}", "videoId": video_id, "lang": "te"})
    try:
        req = urllib.request.Request(
            f"https://{host}/api/transcript?{qs}",
            headers={"x-rapidapi-key": key, "x-rapidapi-host": host, "User-Agent": "Mozilla/5.0"},
        )
        data = _json.load(urllib.request.urlopen(req, timeout=60))
        # shapes vary by provider: {"transcript": [{text}...]} or {"text": "..."}
        if isinstance(data, dict):
            if isinstance(data.get("transcript"), list):
                text = " ".join(c.get("text", "") for c in data["transcript"])
            else:
                text = data.get("text") or data.get("transcript") or ""
        else:
            text = ""
        if text and text.strip():
            log(f"[transcript] got transcript via RapidAPI ({host})")
            return text
    except Exception as exc:  # noqa: BLE001
        log(f"[transcript] RapidAPI failed: {type(exc).__name__}: {str(exc)[:120]}")
    return None


def get_transcript(video_id: str, args) -> str | None:
    # Order: proxied official API (most reliable past block+throttle) → yt-dlp subs
    # → paid-but-reliable server-side APIs → free anonymous kome.ai → Whisper.
    return (
        transcript_via_api(video_id, args)
        or transcript_via_ytdlp_subs(video_id, args)
        or transcript_via_supadata(video_id, args)
        or transcript_via_rapidapi(video_id, args)
        or transcript_via_kome(video_id, args)
        or (transcript_via_whisper(video_id, args) if args.whisper else None)
    )


# ===========================================================================
# 3. TRANSLATE
# ===========================================================================
TRANSLATE_SYSTEM = (
    "You are an expert Telugu-to-English translator specialising in Indian stock-"
    "market / business news. Translate the given Telugu transcript (auto-generated "
    "captions from a TV show, so expect spelling noise and run-ons) into clear, "
    "faithful, readable English prose. Preserve all numbers, tickers, company names "
    "and the meaning exactly; do not summarise, omit, or add commentary. Output only "
    "the English translation — no preamble, no notes."
)


def _claude_call(system: str, user: str, args, max_tokens: int = 16000) -> str:
    """One request to the Anthropic Messages API via stdlib urllib (no SDK)."""
    import json as _json
    import os
    import time
    import urllib.request

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No Anthropic API key. Set ANTHROPIC_API_KEY or pass --api-key. "
            "Translation/summary are done by Claude, which needs API access."
        )
    body = _json.dumps({
        "model": args.model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()

    last = None
    for attempt in range(1, 6):
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=body,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = _json.load(resp)
            # content is a list of blocks; collect the text blocks
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        except Exception as exc:  # noqa: BLE001 – transient HTTP / rate-limit errors
            last = exc
            time.sleep(2 * attempt)
    raise last


def translate_to_english(text: str, args, source: str = "te") -> str:
    """Translate the whole transcript with Claude, chunked so each request stays
    well within output limits. Claude handles large chunks fine, so chunks are big."""
    chunks, out = _split_chunks(text, 6000), []
    for i, chunk in enumerate(chunks, 1):
        log(f"[translate] Claude chunk {i}/{len(chunks)} ({len(chunk)} chars) ...")
        out.append(_claude_call(TRANSLATE_SYSTEM, chunk, args))
    return "\n".join(out)


SUMMARY_SYSTEM = (
    "You are a financial-news editor. Summarise the given English transcript of an "
    "Indian stock-market TV show into clear markdown. Use sections (Global backdrop, "
    "Indian markets, Analysts/segments) and bullet points. Preserve key numbers, "
    "levels, tickers and company names. Be faithful and concise; no preamble."
)

KUTUMBA_SYSTEM = (
    "You are a financial analyst's assistant. From the given English transcript of an "
    "Indian stock-market TV show, extract ONLY what the analyst named 'Kutumba Rao' "
    "says — his market view and his individual stock calls (with levels/targets/"
    "stop-losses). Organise as markdown with a 'Market view' section and a 'Stock "
    "calls' section. Do NOT include the technical analyst Ramakrishna's calls. If a "
    "call's speaker is ambiguous, note it. No preamble."
)


def summarize(english: str, args) -> str:
    log("[analyze] summarising with Claude ...")
    return _claude_call(SUMMARY_SYSTEM, english, args)


def extract_kutumba_rao(english: str, args) -> str:
    log("[analyze] extracting Kutumba Rao with Claude ...")
    return _claude_call(KUTUMBA_SYSTEM, english, args)


RECS_SYSTEM = (
    "From the given English transcript of an Indian stock-market TV show, extract "
    "EVERY stock recommendation made by the analyst named 'Kutumba Rao' — including "
    "Buy, Add, Accumulate, Hold, Reduce/Trim, Sell/Exit, Avoid, Book Profit, and "
    "Watch calls (exclude anything said by the technical analyst Ramakrishna). "
    "Respond with a JSON array only (no prose, no code fence). Each item: "
    '{"stock": "<name>", '
    '"action": "<one of: Buy, Add, Accumulate, Hold, Reduce, Sell, Avoid, Book Profit, Watch>", '
    '"price": "<price or level if stated, else empty>", '
    '"note": "<one-line reason in <=160 chars>", '
    '"detail": "<his full comment on this stock, 1-4 sentences, no truncation>"}. '
    "If none, respond with []."
)
# Back-compat alias (older imports may reference BUYS_SYSTEM).
BUYS_SYSTEM = RECS_SYSTEM


def extract_recommendations(english: str, args) -> list[dict]:
    """Claude returns a JSON array of ALL of Kutumba Rao's recommendations.

    Each item has stock/action/price/note. Items missing an action are kept and
    default to 'Buy' downstream (legacy behaviour)."""
    import json as _json
    raw = _claude_call(RECS_SYSTEM, english, args, max_tokens=4000).strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    m = re.search(r"\[.*\]", raw, flags=re.DOTALL)  # tolerate stray text
    if not m:
        return []
    try:
        data = _json.loads(m.group(0))
        return [d for d in data if isinstance(d, dict) and d.get("stock")]
    except Exception:  # noqa: BLE001
        return []


# Back-compat alias.
extract_buy_calls = extract_recommendations


def _split_chunks(text: str, size: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?।])\s+", text)
    chunks, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) + 1 > size:
            if cur:
                chunks.append(cur)
            cur = s
            while len(cur) > size:  # a single huge "sentence"
                chunks.append(cur[:size])
                cur = cur[size:]
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks or [text]


# ===========================================================================
# 4. SAVE  +  orchestration
# ===========================================================================
def process_video(video: dict, args) -> dict | None:
    date = video["upload_date"]
    # Try every channel/LIVE copy for this date in priority order; first one that
    # yields a transcript wins (and names the output files).
    candidates = video.get("candidates") or [_candidate(video["id"], video.get("title", ""))]
    telugu, vid, title = None, candidates[0]["id"], candidates[0]["title"]
    for c in candidates:
        tag = c["channel"] + ("/live" if c["is_live"] else "")
        log(f"\n=== {date} | {c['title']} ({c['id']}) [{tag}] ===")
        telugu = get_transcript(c["id"], args)
        if telugu:
            vid, title = c["id"], c["title"]
            break
        if len(candidates) > 1:
            log("[try-next] no transcript on this copy; trying another channel/cut.")
    if not telugu:
        log("[skip] no transcript on any channel copy for this date.")
        return None

    english = translate_to_english(telugu, args, source=args.source_lang)

    stem = f"{date.isoformat()}__{sanitize_filename(title)}"
    out_dir = Path(args.out)
    header = f"# {title}\n# Uploaded: {date.isoformat()}\n# https://youtu.be/{vid}\n\n"

    def _save(subdir: str, filename: str, body: str) -> Path:
        d = out_dir / subdir
        d.mkdir(parents=True, exist_ok=True)
        p = d / filename
        p.write_text(body, encoding="utf-8")
        log(f"[saved] {p}")
        return p

    result = {"video": video, "english": english}
    result["te"] = _save("telugu_transcript", f"{stem}.te.txt", telugu)
    result["en"] = _save("english_translation", f"{stem}.en.txt", header + english)

    if not args.no_analyze:
        result["summary"] = _save(
            "summary", f"{stem}.summary.md", header + summarize(english, args))
        result["kutumba_rao"] = _save(
            "kutumba_rao", f"{stem}.kutumba_rao.md", header + extract_kutumba_rao(english, args))
        # Structured recommendations sidecar that feeds the consolidated table.
        # Key kept as "buys" (and items still named buys) for backward compatibility
        # with sidecars written before Hold/Sell/etc. were captured; the table
        # builder reads both "recommendations" and "buys".
        import json as _json
        recs = extract_recommendations(english, args)
        result["buys"] = _save("kutumba_rao", f"{stem}.buys.json", _json.dumps(
            {"date": date.isoformat(), "video_id": vid, "title": title,
             "recommendations": recs},
            ensure_ascii=False, indent=2))

    return result


def build_args(argv=None):
    p = argparse.ArgumentParser(
        description="Translate TV5 Money 'Business Breakfast' Telugu videos to English.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--channel", default=DEFAULT_CHANNEL)
    p.add_argument("--news-channel", default=DEFAULT_NEWS_CHANNEL,
                   help="fallback channel whose /videos tab still lists from blocked IPs "
                   "(deep-scanned); set empty to disable")
    p.add_argument("--keyword", default=DEFAULT_KEYWORD)
    p.add_argument("--days", type=int, default=7, help="look back this many days")
    p.add_argument("--scan", type=int, default=80, help="how many recent uploads/search "
                   "hits to scan (search is relevance-ranked, so raise this for longer windows)")
    p.add_argument("--search-query", help="override the ytsearch fallback query "
                   "(used when the channel listing is blocked); default 'TV5 Money <keyword>'")
    p.add_argument("--limit", type=int, default=None, help="process at most N videos")
    p.add_argument("--video-ids", help="comma-separated YouTube IDs to process directly, "
                   "bypassing discovery (title via oEmbed, date parsed from title)")
    p.add_argument("--out", default="output")
    p.add_argument("--source-lang", default="te", help="source language for translation")
    p.add_argument("--list-only", action="store_true", help="only discover, don't transcribe")
    p.add_argument("--whisper", action="store_true", help="enable Whisper audio fallback")
    p.add_argument("--whisper-model", default="small")
    p.add_argument("--kome-retries", type=int, default=8,
                   help="retries for the kome.ai transcript fallback (it throttles)")
    # translation + analysis (done by Claude)
    p.add_argument("--model", default=DEFAULT_MODEL, help="Anthropic model for translation/analysis")
    p.add_argument("--api-key", help="Anthropic API key (else uses ANTHROPIC_API_KEY env)")
    p.add_argument("--no-analyze", action="store_true",
                   help="skip the summary + Kutumba Rao extraction steps")
    p.add_argument("--skip-existing", action="store_true",
                   help="skip dates that already have an english_translation output "
                        "(idempotent daily runs; honours the reuse-existing rule)")
    # auth / network
    p.add_argument("--cookies", help="Netscape cookie file (cookies.txt)")
    p.add_argument("--cookies-from-browser", help="e.g. chrome, firefox, edge")
    p.add_argument("--proxy", help="generic http(s) proxy URL (for yt-dlp + transcript API)")
    # transcript-source credentials (beat YouTube's data-centre IP block + throttle)
    p.add_argument("--webshare-user", help="Webshare residential proxy username "
                   "(best fix: youtube-transcript-api routes through it)")
    p.add_argument("--webshare-pass", help="Webshare residential proxy password")
    p.add_argument("--supadata-key", help="supadata.ai API key (server-side, no proxy; else SUPADATA_API_KEY)")
    p.add_argument("--rapidapi-key", help="RapidAPI key for a transcript endpoint (else RAPIDAPI_KEY)")
    p.add_argument("--rapidapi-host", default="youtube-transcript3.p.rapidapi.com",
                   help="RapidAPI transcript host")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = build_args(argv)
    if args.video_ids:
        ids = [v.strip() for v in args.video_ids.split(",") if v.strip()]
        videos = videos_from_ids(ids)
    else:
        videos = discover_videos(args)

    if not videos:
        log("No matching videos found.")
        return 1

    if args.skip_existing:
        out_en = Path(args.out) / "english_translation"
        kept = [v for v in videos
                if not list(out_en.glob(f"{v['upload_date'].isoformat()}__*.en.txt"))]
        skipped = len(videos) - len(kept)
        if skipped:
            log(f"[skip-existing] skipping {skipped} date(s) already processed.")
        videos = kept
        if not videos:
            log("All discovered dates already processed; nothing to do.")
            return 0

    print("\nMatching videos:")
    for v in videos:
        print(f"  {v['upload_date']}  {v['id']}  {v['title']}")

    if args.list_only:
        return 0

    if args.limit:
        videos = videos[: args.limit]

    results = [r for v in videos if (r := process_video(v, args))]

    # Refresh the consolidated Kutumba Rao buy table from all sidecars.
    if results and not args.no_analyze:
        try:
            from update_buy_table import rebuild_buy_table
            n = rebuild_buy_table(Path(args.out) / "kutumba_rao")
            log(f"[buys] rebuilt buy_recommendations table ({n} stocks)")
        except Exception as exc:  # noqa: BLE001
            log(f"[buys] table rebuild skipped: {type(exc).__name__}")

    # Refresh the web-dashboard manifest (docs/data.json) so it never goes stale.
    if results:
        try:
            import build_dashboard_data
            build_dashboard_data.main()
        except Exception as exc:  # noqa: BLE001
            log(f"[dashboard] data rebuild skipped: {type(exc).__name__}")

    if results:
        first = results[0]
        print("\n" + "=" * 70)
        print(f"PREVIEW – {first['video']['title']}")
        print("=" * 70)
        print(textwrap.shorten(first["english"], width=1500, placeholder=" ..."))
    return 0 if results else 2


if __name__ == "__main__":
    raise SystemExit(main())
