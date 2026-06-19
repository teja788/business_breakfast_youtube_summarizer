#!/usr/bin/env python3
"""Resolve every recommended stock name -> NSE Yahoo symbol (e.g. NTPC.NS).

Writes tickers.json: {original_name: {symbol, yahoo_name, priceable, note}}.
Resolution: manual overrides first, else Yahoo symbol-search (first .NS hit),
then validate each symbol actually returns price data. Non-priceable items
(mutual funds, options, indices, generic baskets) are flagged priceable=false.
"""
import json, glob, time, urllib.request, urllib.parse

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
}

# Not single priceable equities -> skip pricing.
NONPRICEABLE_SUBSTR = ["put", "fund", "amcs", "index", "equal weight"]


def is_nonpriceable(name: str) -> bool:
    n = name.lower()
    return any(s in n for s in NONPRICEABLE_SUBSTR)


def yahoo_search(name: str):
    q = urllib.parse.urlencode({"q": name, "quotesCount": 8, "newsCount": 0})
    url = f"https://query1.finance.yahoo.com/v1/finance/search?{q}"
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20))
        for x in d.get("quotes", []):
            if str(x.get("symbol", "")).endswith(".NS"):
                return x["symbol"], (x.get("shortname") or x.get("longname") or "")
    except Exception:
        pass
    return None, None


def validate(symbol: str):
    """Return (last_close, currency) if the symbol returns price data, else (None, None)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d"
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20))
        r = d["chart"]["result"][0]
        closes = [c for c in r["indicators"]["quote"][0]["close"] if c]
        return (closes[-1] if closes else None), r["meta"].get("currency")
    except Exception:
        return None, None


def main():
    names = set()
    for f in glob.glob("output/kutumba_rao/*.buys.json"):
        for r in json.load(open(f))["recommendations"]:
            if r.get("action") in ("Buy", "Add", "Accumulate", "Hold"):
                names.add(r["stock"].strip())
    for f in glob.glob("output/kranti/*.kranti.json"):
        for c in json.load(open(f))["calls"]:
            if c.get("action") in ("Buy", "Add", "Accumulate", "Hold"):
                names.add(c["stock"].strip())

    out = {}
    for name in sorted(names):
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
            print(f"OK   {name:42} -> {sym:16} {yname or ''}")
        else:
            out[name] = {"symbol": sym, "yahoo_name": yname, "priceable": False,
                         "note": "unresolved / no price data"}
            print(f"MISS {name:42} -> {sym}")
        time.sleep(0.2)

    json.dump(out, open("tickers.json", "w"), ensure_ascii=False, indent=2)
    pr = sum(1 for v in out.values() if v["priceable"])
    print(f"\nWrote tickers.json: {pr}/{len(out)} priceable.")


if __name__ == "__main__":
    main()
