#!/usr/bin/env python3
"""Ask Kutumba — a CLI agent that reasons like analyst Kutumba Rao (TV5 Money).

Loads the distilled doctrine (kutumba_brain.md) as the system prompt, then answers
free-form market/stock questions using live research:
  - web_search  : Anthropic server-side web search (news, results, qualitative)
  - stock_data  : Yahoo Finance price/52w/returns for an NSE stock (client tool)
  - market_context : Nifty + India VIX snapshot for the regime-first read

His past calls trained the METHOD, not a stance database — the bot may contradict
his old views when today's data says so.

Two ways to run:
  A) NO API KEY (Claude Max plan) — the recommended path:
     use the /kutumba slash command inside Claude Code, or ./kutumba.sh "question"
     (wraps `claude -p`, authenticated by your Claude subscription). In this mode
     this file is only the DATA TOOL:
       python kutumba_bot/ask_kutumba.py --tool market_context
       python kutumba_bot/ask_kutumba.py --tool stock_data "Laurus Labs"
  B) With ANTHROPIC_API_KEY (standalone agent loop):
     python kutumba_bot/ask_kutumba.py "Is Ather Energy still a buy?"
     python kutumba_bot/ask_kutumba.py                      # interactive REPL
Flags: --model claude-opus-4-8  --no-web  --debug  --tool NAME [ARG]

No third-party deps (stdlib urllib), matching the project convention.
Not investment advice — a research prototype for personal use.
"""
import argparse, json, os, sys, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UA = {"User-Agent": "Mozilla/5.0"}
API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = os.environ.get("KUTUMBA_MODEL", "claude-opus-4-8")

# ---------------------------------------------------------------- Yahoo helpers

def _get_json(url, attempts=4):
    err = None
    for i in range(attempts):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=25))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(0.6 * (i + 1))
    print(f"  [warn] fetch failed ({type(err).__name__}): {url[:90]}", file=sys.stderr)
    return None


def _load_tickers():
    try:
        return json.load(open(os.path.join(ROOT, "tickers.json")))
    except Exception:  # noqa: BLE001
        return {}


_TICKERS = _load_tickers()


def resolve_symbol(query):
    """Company name / symbol -> (yahoo_symbol, display_name, sector) or (None, query, '')."""
    q = query.strip()
    if q.upper().endswith(".NS") or q.startswith("^"):
        return q.upper() if not q.startswith("^") else q, q, ""
    ql = q.lower()
    # exact then substring match against tickers.json (608 curated names)
    for name, v in _TICKERS.items():
        if name.lower() == ql and v.get("priceable"):
            return v["symbol"], name, v.get("sector", "")
    for name, v in _TICKERS.items():
        if v.get("priceable") and (ql in name.lower() or name.lower() in ql):
            return v["symbol"], name, v.get("sector", "")
    # Yahoo symbol search, first .NS hit (same approach as build_tickers.py)
    d = _get_json("https://query1.finance.yahoo.com/v1/finance/search?"
                  + urllib.parse.urlencode({"q": q, "quotesCount": 8, "newsCount": 0}))
    for x in (d or {}).get("quotes", []):
        if str(x.get("symbol", "")).endswith(".NS"):
            return x["symbol"], x.get("shortname") or x.get("longname") or q, \
                   x.get("sector") or x.get("industry") or ""
    return None, q, ""


def _chart(symbol, rng="1y"):
    d = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/"
                  f"{urllib.parse.quote(symbol)}?range={rng}&interval=1d")
    try:
        r = d["chart"]["result"][0]
        ind = r["indicators"]
        adj = (ind.get("adjclose") or [{}])[0].get("adjclose")
        cl = adj if adj and any(c is not None for c in adj) else ind["quote"][0]["close"]
        closes = [c for c in cl if c is not None]
        return closes, r.get("meta", {})
    except Exception:  # noqa: BLE001
        return [], {}


def _ret(closes, n):
    """% return over the last n trading days (None if not enough history)."""
    if len(closes) > n and closes[-1 - n]:
        return round((closes[-1] / closes[-1 - n] - 1) * 100, 1)
    return None


def tool_stock_data(query):
    sym, name, sector = resolve_symbol(query)
    if not sym:
        return {"error": f"Could not resolve '{query}' to an NSE symbol."}
    closes, meta = _chart(sym)
    if not closes:
        return {"error": f"No price data for {sym}."}
    last = round(closes[-1], 2)
    hi, lo = round(max(closes), 2), round(min(closes), 2)
    return {
        "query": query, "name": name, "symbol": sym, "sector": sector or None,
        "price": last, "currency": meta.get("currency", "INR"),
        "52w_high": hi, "52w_low": lo,
        "pct_from_52w_high": round((last / hi - 1) * 100, 1),
        "pct_from_52w_low": round((last / lo - 1) * 100, 1),
        "return_1w_pct": _ret(closes, 5), "return_1m_pct": _ret(closes, 21),
        "return_3m_pct": _ret(closes, 63),
        "return_1y_pct": round((closes[-1] / closes[0] - 1) * 100, 1),
    }


def tool_market_context():
    out = {}
    closes, _meta = _chart("^NSEI", "6mo")
    if closes:
        out["nifty"] = {"level": round(closes[-1], 1),
                        "return_1d_pct": _ret(closes, 1), "return_1w_pct": _ret(closes, 5),
                        "return_1m_pct": _ret(closes, 21),
                        "6m_high": round(max(closes), 1), "6m_low": round(min(closes), 1)}
    vix, _ = _chart("^INDIAVIX", "1mo")
    if vix:
        out["india_vix"] = {"level": round(vix[-1], 2), "1w_ago": round(vix[-6], 2) if len(vix) > 5 else None}
    bank, _ = _chart("^NSEBANK", "1mo")
    if bank:
        out["bank_nifty"] = {"level": round(bank[-1], 1), "return_1w_pct": _ret(bank, 5)}
    usdinr, _ = _chart("USDINR=X", "3mo")
    if usdinr:
        out["usd_inr"] = {"level": round(usdinr[-1], 2), "return_1m_pct": _ret(usdinr, 21)}
    crude, _ = _chart("BZ=F", "3mo")
    if crude:
        out["brent_crude_usd"] = {"level": round(crude[-1], 2), "return_1m_pct": _ret(crude, 21)}
    return out or {"error": "No market data available."}


# ---------------------------------------------------------------- Claude agent

CLIENT_TOOLS = [
    {"name": "stock_data",
     "description": ("Live NSE stock snapshot from Yahoo Finance: current price, 52-week "
                     "high/low and distance from them, and 1w/1m/3m/1y returns. Use for "
                     "EVERY specific stock discussed, before giving a verdict."),
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Company name or NSE symbol (e.g. 'Laurus Labs' or 'LAURUSLABS.NS')"}},
         "required": ["query"]}},
    {"name": "market_context",
     "description": ("Current Indian market regime snapshot: Nifty level + 1d/1w/1m returns "
                     "+ 6-month range, India VIX, Bank Nifty, USD/INR, Brent crude. Call this "
                     "first for any market-view or stock question — the regime read comes first."),
     "input_schema": {"type": "object", "properties": {}}},
]
WEB_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 8}


def load_brain():
    for fname in ("kutumba_brain.md", "distill_2025-12_2026-02.md"):
        p = os.path.join(HERE, fname)
        if os.path.exists(p):
            return open(p).read(), fname
    sys.exit("No brain file found in kutumba_bot/ — expected kutumba_brain.md")


ANSWER_CONTRACT = """
---
# Who you are and how you answer

You are an AI analyst that reasons EXACTLY like Kutumba Rao — the veteran
fundamental/markets analyst of TV5 Money's "Business Breakfast" — using the doctrine
above, which was distilled from ~116 of his episodes. You have his SKILL and his
LENSES, not his memory: you may contradict his past calls when today's data warrants.
Today's date matters — always reason from CURRENT data you fetch, never from stale
levels in the doctrine (those illustrate his method, not today's market).

## Process (every answer)
1. Call market_context first — his regime-first habit. For stocks, also call
   stock_data. Use web_search for recent results, news, order books, promoter or
   sector developments before any verdict. Research first, verdict after.
2. Answer in HIS structure:
   - **Market read first** (one short paragraph): buy-on-dips vs sell-on-rallies vs
     consolidation, with the Nifty level/trigger that would flip it.
   - **Verdict** (for stock questions) from his verb set only:
     Buy / Add / Accumulate / Hold / Avoid / Sell / Watch — bolded, first line.
   - **His reasoning lenses** (use the ones that apply): value vs fancy, consolidation
     band and breakout level, 52w positioning, PE stance, promoter quality, result +
     stock reaction, hidden value/SOTP, order book vs execution, dividend/FD-alternative,
     sector tailwind, already-priced-in test.
   - **Risk & horizon**: entry zone / add-on-dips zone, stop or trailing stop, and an
     explicit horizon (trading / 1yr+ long term / 2-3yr turnaround / 3-5yr PSU).
   - **What would change my mind** — one or two concrete triggers.
3. Voice: direct, conversational, confident but honest about uncertainty — like a
   veteran Telugu market analyst speaking English on morning TV. Use his verbal tells
   naturally where they fit ("value but no fancy", "exit on rallies", "already
   discounted", "hero or zero", "make it free of cost", "not the time to pyramid").
   Numbers concrete, Rs not the rupee sign. No hedging walls of caveats — he commits.
4. If the question is macro/general (no single stock), skip the verdict verb and give
   his market view + how he'd position (sectors, buckets, allocation).
5. End with one italic line: *Research prototype, not investment advice.*
"""


def api_call(payload, key, debug=False):
    req = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=300))
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if debug:
            print(f"[api {e.code}] {body[:500]}", file=sys.stderr)
        raise RuntimeError(f"API error {e.code}: {body[:300]}") from e


def run_tool(name, args):
    if name == "stock_data":
        return tool_stock_data(args.get("query", ""))
    if name == "market_context":
        return tool_market_context()
    return {"error": f"unknown tool {name}"}


def answer(question, history, system, model, use_web, debug):
    """One agentic turn: loop tool_use rounds until end_turn. Mutates history."""
    key = os.environ.get("ANTHROPIC_API_KEY") or sys.exit("Set ANTHROPIC_API_KEY")
    tools = CLIENT_TOOLS + ([WEB_TOOL] if use_web else [])
    history.append({"role": "user", "content": question})
    while True:
        payload = {"model": model, "max_tokens": 4096, "system": system,
                   "messages": history, "tools": tools}
        try:
            resp = api_call(payload, key, debug)
        except RuntimeError as e:
            # Graceful fallback if the org lacks the server web-search tool.
            if use_web and "web_search" in str(e):
                print("[warn] web_search tool unavailable — continuing without it.",
                      file=sys.stderr)
                use_web = False
                tools = CLIENT_TOOLS
                continue
            raise
        history.append({"role": "assistant", "content": resp["content"]})
        if resp.get("stop_reason") != "tool_use":
            return "\n".join(b.get("text", "") for b in resp["content"]
                             if b.get("type") == "text").strip()
        results = []
        for b in resp["content"]:
            if b.get("type") != "tool_use":
                continue
            if debug:
                print(f"[tool] {b['name']}({json.dumps(b['input'])[:120]})", file=sys.stderr)
            out = run_tool(b["name"], b.get("input") or {})
            if debug:
                print(f"       -> {json.dumps(out)[:200]}", file=sys.stderr)
            results.append({"type": "tool_result", "tool_use_id": b["id"],
                            "content": json.dumps(out)})
        history.append({"role": "user", "content": results})


def main():
    ap = argparse.ArgumentParser(description="Ask Kutumba — analyst-brain CLI")
    ap.add_argument("question", nargs="*", help="your question (omit for REPL)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-web", action="store_true", help="disable web search tool")
    ap.add_argument("--debug", action="store_true", help="print tool traffic")
    ap.add_argument("--tool", choices=["stock_data", "market_context"],
                    help="run one data tool standalone (no API key) and print JSON")
    a = ap.parse_args()

    if a.tool:  # standalone tool mode — used by the /kutumba Claude Code command
        arg = " ".join(a.question)
        out = tool_stock_data(arg) if a.tool == "stock_data" else tool_market_context()
        print(json.dumps(out, indent=1))
        return

    brain, brain_file = load_brain()
    system = brain + ANSWER_CONTRACT
    print(f"[brain: {brain_file} · model: {a.model} · web: {not a.no_web}]\n",
          file=sys.stderr)

    history = []
    if a.question:
        print(answer(" ".join(a.question), history, system, a.model,
                     not a.no_web, a.debug))
        return
    print("Ask Kutumba (Ctrl-D or 'exit' to quit). Follow-ups keep context.\n")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q or q.lower() in ("exit", "quit"):
            break
        try:
            print("\n" + answer(q, history, system, a.model, not a.no_web, a.debug) + "\n")
        except RuntimeError as e:
            print(f"[error] {e}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
