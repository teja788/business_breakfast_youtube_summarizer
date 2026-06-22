#!/usr/bin/env python3
"""Resolve every recommended stock name -> NSE Yahoo symbol (e.g. NTPC.NS).

Writes tickers.json: {original_name: {symbol, yahoo_name, priceable, note}}.
Resolution: manual overrides first, else Yahoo symbol-search (first .NS hit),
then validate each symbol actually returns price data. Non-priceable items
(mutual funds, options, indices, generic baskets) are flagged priceable=false.
"""
import json, glob, os, time, urllib.request, urllib.parse

from analyst_calls import is_buy, norm_key

UA = {"User-Agent": "Mozilla/5.0"}

# Known renames / new listings the search misses or gets wrong.
OVERRIDES = {
    "Amara Raja Batteries": "ARE&M.NS",          # renamed Amara Raja Energy & Mobility
    "Siemens Energy": "ENRIN.NS",                # Siemens Energy India Ltd (listed 2025)
    "Transformers and Rectifiers (TARIL)": "TARIL.NS",
    "HDFC": "HDFCBANK.NS",                        # HDFC Ltd merged into HDFC Bank
    "SBI": "SBIN.NS",
    "State Bank of India (SBI)": "SBIN.NS",
    "Bajaj Housing Finance": "BAJAJHFL.NS",
    "Nifty BeES / Bank Nifty BeES": "NIFTYBEES.NS",
    # Search misses / wrong hits corrected (verified against Yahoo):
    "Vedanta": "VEDL.NS",                        # search gave VAML (aluminium arm) — wrong
    "Vedanta (demerger)": "VEDL.NS",
    "Tata Motors": "TATAMOTORS.NS",              # search gave TMCV (CV demerger)
    "TVS Motors": "TVSMOTOR.NS",
    "Varun Beverages (VBL)": "VBL.NS",
    "Yatharth Hospitals": "YATHARTH.NS",
    "Nava": "NAVA.NS",
    "Rainbow Hospitals": "RAINBOW.NS",
    "Rainbow Children's Medicare (Rainbow Hospitals)": "RAINBOW.NS",
    "Waaree Energy": "WAAREEENER.NS",
    "IGIL": "IGIL.NS",
    "GRM Overseas": "GRMOVER.NS",
    "Blue Star": "BLUESTARCO.NS",
    "Vishal Mega Mart (\"Walmart\") Retail": "VMM.NS",
    # Manually validated against Yahoo (search missed or returned a wrong hit):
    "Adani Ports": "ADANIPORTS.NS",
    "Bharat Electronics (BEL)": "BEL.NS",
    "BEL": "BEL.NS",
    "Coromandel International": "COROMANDEL.NS",
    "Divi's Labs": "DIVISLAB.NS",
    "Garden Reach Shipbuilders (GRSE)": "GRSE.NS",
    "Hyundai Motors": "HYUNDAI.NS",
    "Info Edge (Naukri)": "NAUKRI.NS",
    "Jio Finance (Jio Financial)": "JIOFIN.NS",
    "NCC (Nagarjuna Construction)": "NCC.NS",
    "RVNL": "RVNL.NS",
    "Subros": "SUBROS.NS",
    "Syrma SGS": "SYRMA.NS",
    "TD Power Systems": "TDPOWERSYS.NS",
    "Mahindra & Mahindra (M&M)": "M&M.NS",
    "Anoop Engineering": "ANUP.NS",            # = The Anup Engineering
}

# Not single priceable equities -> skip pricing.
NONPRICEABLE_SUBSTR = ["put", "fund", "amcs", "index", "equal weight"]


def is_nonpriceable(name: str) -> bool:
    n = name.lower()
    return any(s in n for s in NONPRICEABLE_SUBSTR)


def _get_json(url: str, attempts: int = 4):
    """GET + JSON with retry/backoff. Returns parsed JSON or None (logged)."""
    err = None
    for i in range(attempts):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(0.6 * (i + 1))
    print(f"  [warn] Yahoo fetch failed after {attempts} tries ({type(err).__name__}): {url[:90]}")
    return None


def yahoo_search(name: str):
    q = urllib.parse.urlencode({"q": name, "quotesCount": 8, "newsCount": 0})
    d = _get_json(f"https://query1.finance.yahoo.com/v1/finance/search?{q}")
    for x in (d or {}).get("quotes", []):
        if str(x.get("symbol", "")).endswith(".NS"):
            return x["symbol"], (x.get("shortname") or x.get("longname") or "")
    return None, None


def validate(symbol: str):
    """Return (last_close, currency) if the symbol returns price data, else (None, None)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1mo&interval=1d"
    d = _get_json(url)
    if not d:
        return None, None
    try:
        r = d["chart"]["result"][0]
        closes = [c for c in r["indicators"]["quote"][0]["close"] if c]
        return (closes[-1] if closes else None), r["meta"].get("currency")
    except Exception:  # noqa: BLE001
        return None, None


def _is_holdish(action: str) -> bool:
    return "hold" in (action or "").lower() or "watch" in (action or "").lower()


def main():
    # Collect every name that is a buy or a hold (so the scorecard's buys always
    # get a ticker, and holds are covered too). Uses the shared is_buy() so the
    # set matches exactly what the scorecard will try to price.
    names = set()
    for f in glob.glob("output/kutumba_rao/*.buys.json"):
        for r in json.load(open(f))["recommendations"]:
            if is_buy(r.get("action")) or _is_holdish(r.get("action")):
                names.add(r["stock"].strip())
    for f in glob.glob("output/kranti/*.kranti.json"):
        for c in json.load(open(f))["calls"]:
            if is_buy(c.get("action")) or _is_holdish(c.get("action")):
                names.add(c["stock"].strip())

    # Merge with the existing file so a daily rebuild never clobbers a validated
    # symbol on a transient Yahoo hiccup: keep priceable entries, only (re)resolve
    # names that are new or not-yet-priceable.
    out = {}
    if os.path.exists("tickers.json"):
        out = json.load(open("tickers.json"))
    # Dedup names that normalise to the same company (skip if a sibling spelling
    # is already priceable, e.g. "Netweb"/"NetWeb").
    priceable_keys = {norm_key(n) for n, v in out.items() if v.get("priceable")}

    resolved = 0
    for name in sorted(names):
        if out.get(name, {}).get("priceable"):
            continue  # already good — preserve
        if norm_key(name) in priceable_keys:
            # A different spelling of this company is already priced; copy it over
            # so a raw-name lookup still hits.
            twin = next(v for n, v in out.items() if v.get("priceable") and norm_key(n) == norm_key(name))
            out[name] = dict(twin)
            print(f"DUP  {name:42} -> {twin['symbol']} (alias)")
            continue
        if is_nonpriceable(name):
            out[name] = {"symbol": None, "yahoo_name": None, "priceable": False,
                         "note": "fund/option/index — not a single equity"}
            continue
        sym = OVERRIDES.get(name)
        yname = None
        if not sym:
            sym, yname = yahoo_search(name)
            time.sleep(0.3)
        last, cur = (validate(sym) if sym else (None, None))
        if sym and last:
            out[name] = {"symbol": sym, "yahoo_name": yname, "priceable": True,
                         "last_close": round(last, 2), "currency": cur}
            priceable_keys.add(norm_key(name))
            resolved += 1
            print(f"OK   {name:42} -> {sym:16} {yname or ''}")
        else:
            out[name] = {"symbol": sym, "yahoo_name": yname, "priceable": False,
                         "note": "unresolved / no price data"}
            print(f"MISS {name:42} -> {sym}")
        time.sleep(0.2)

    json.dump(out, open("tickers.json", "w"), ensure_ascii=False, indent=2)
    pr = sum(1 for v in out.values() if v.get("priceable"))
    print(f"\nWrote tickers.json: {pr}/{len(out)} priceable ({resolved} newly resolved this run).")


if __name__ == "__main__":
    main()
