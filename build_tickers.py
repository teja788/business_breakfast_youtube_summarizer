#!/usr/bin/env python3
"""Resolve every recommended stock name -> NSE Yahoo symbol (e.g. NTPC.NS).

Writes tickers.json: {original_name: {symbol, yahoo_name, priceable, note}}.
Resolution: manual overrides first, else Yahoo symbol-search (first .NS hit),
then validate each symbol actually returns price data. Non-priceable items
(mutual funds, options, indices, generic baskets) are flagged priceable=false.
"""
import json, glob, os, re, time, urllib.request, urllib.parse

from analyst_calls import alias_keys, is_buy, norm_key

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
    # Audit fixes: the search's first .NS hit was a DIFFERENT company.
    "ITC": "ITC.NS",                            # search hit ITC Hotels
    "Bank of India": "BANKINDIA.NS",            # search hit State Bank of India
    "PNB": "PNB.NS",                            # search hit PNB Gilts
    "Groww": "GROWW.NS",                        # search hit a Groww AMC ETF; = Billionbrains Garage Ventures
    # Audit fixes: variants left unresolved while a sibling spelling was priced.
    "NCC": "NCC.NS",
    "Jio Finance": "JIOFIN.NS",
    "Larsen & Toubro (L&T)": "LT.NS",
    "Naukri (Info Edge)": "NAUKRI.NS",
    "Himadri Speciality Chemicals": "HSCL.NS",   # plural variant; singular already priced
    # Search misses (validated against Yahoo 2026-07-24): the listed entity's
    # symbol differs from the brand name the show uses.
    "Nykaa": "NYKAA.NS",                         # = FSN E-Commerce Ventures
    "Nykaa (FSN E-Commerce)": "NYKAA.NS",
    "Network 18": "NETWORK18.NS",                # = Network18 Media & Investments
}

# Curated sector by Yahoo symbol. Yahoo's sector API (quoteSummary/v7) 401s from
# some cloud IPs, so these well-known NSE names are mapped by hand (accurate, free,
# offline). The live Yahoo lookup still fills any symbol not listed here.
SECTOR_OVERRIDES = {
    "ADANIENT.NS": "Diversified", "ADANIPORTS.NS": "Infrastructure", "ADANIPOWER.NS": "Power",
    "BIRLAMONEY.NS": "Financial Services", "ARE&M.NS": "Auto Ancillaries", "AMBUJACEM.NS": "Cement",
    "ANANTRAJ.NS": "Realty", "ANUP.NS": "Capital Goods", "ASHOKLEY.NS": "Automobile",
    "ATHERENERG.NS": "Automobile", "AVANTEL.NS": "Defence", "AVANTIFEED.NS": "FMCG",
    "BEL.NS": "Defence", "BSE.NS": "Financial Services", "BAJAJHFL.NS": "Financial Services",
    "BHARTIARTL.NS": "Telecom", "BIOCON.NS": "Pharmaceuticals", "BLUESTARCO.NS": "Consumer Durables",
    "CCL.NS": "FMCG", "CDSL.NS": "Financial Services", "CGPOWER.NS": "Capital Goods",
    "CANBK.NS": "Banking", "CRAMC.NS": "Financial Services", "COALINDIA.NS": "Mining",
    "COFORGE.NS": "IT", "CUMMINSIND.NS": "Capital Goods", "DCBBANK.NS": "Banking",
    "DIXON.NS": "Consumer Durables", "DRREDDY.NS": "Pharmaceuticals", "ERIS.NS": "Pharmaceuticals",
    "GMRAIRPORT.NS": "Infrastructure", "GRMOVER.NS": "FMCG", "GRSE.NS": "Defence",
    "HBLENGINE.NS": "Capital Goods", "HDFCBANK.NS": "Banking", "HCG.NS": "Healthcare",
    "HERITGFOOD.NS": "FMCG", "HINDALCO.NS": "Metals", "POWERINDIA.NS": "Capital Goods",
    "HYUNDAI.NS": "Automobile", "IDBI.NS": "Banking", "IGIL.NS": "Consumer Services",
    "IRFC.NS": "Financial Services", "ITCHOTELS.NS": "Hotels", "INDOFARM.NS": "Automobile",
    "NAUKRI.NS": "IT", "INFY.NS": "IT", "JSWENERGY.NS": "Power", "JSWINFRA.NS": "Infrastructure",
    "JINDALSAW.NS": "Metals", "JIOFIN.NS": "Financial Services", "JWL.NS": "Capital Goods",
    "KPIGREEN.NS": "Renewable Energy", "KALYANKJIL.NS": "Consumer Durables", "KIRLOSENG.NS": "Capital Goods",
    "KOTAKBANK.NS": "Banking", "LTF.NS": "Financial Services", "LGEINDIA.NS": "Consumer Durables",
    "LICI.NS": "Insurance", "LT.NS": "Capital Goods", "LAURUSLABS.NS": "Pharmaceuticals",
    "MCX.NS": "Financial Services", "MTARTECH.NS": "Capital Goods", "M&M.NS": "Automobile",
    "MANORAMA.NS": "FMCG", "MARUTI.NS": "Automobile", "MAZDOCK.NS": "Defence",
    "MOTILALOFS.NS": "Financial Services", "MPHASIS.NS": "IT", "NLCINDIA.NS": "Power",
    "NTPC.NS": "Power", "NH.NS": "Healthcare", "NATCOPHARM.NS": "Pharmaceuticals", "NAVA.NS": "Power",
    "NETWEB.NS": "IT", "OLAELEC.NS": "Automobile", "OLECTRA.NS": "Automobile",
    "PGEL.NS": "Consumer Durables", "PNBGILTS.NS": "Financial Services", "PATANJALI.NS": "FMCG",
    "PERSISTENT.NS": "IT", "PIDILITIND.NS": "Chemicals", "POLYCAB.NS": "Capital Goods",
    "POWERMECH.NS": "Capital Goods", "PRAJIND.NS": "Capital Goods", "PRECWIRE.NS": "Capital Goods",
    "RVNL.NS": "Railways", "RADICO.NS": "FMCG", "RAINBOW.NS": "Healthcare", "RATEGAIN.NS": "IT",
    "RELIANCE.NS": "Diversified", "ROLEXRINGS.NS": "Auto Ancillaries", "SBFC.NS": "Financial Services",
    "SBIN.NS": "Banking", "SMSPHARMA.NS": "Pharmaceuticals", "SAIPARENT.NS": "Pharmaceuticals",
    "MOTHERSON.NS": "Auto Ancillaries", "SANSERA.NS": "Auto Ancillaries", "SATIN.NS": "Financial Services",
    "SHILCTECH.NS": "Capital Goods", "ENRIN.NS": "Capital Goods", "SUZLON.NS": "Renewable Energy",
    "SYRMA.NS": "Capital Goods", "TCS.NS": "IT", "TDPOWERSYS.NS": "Capital Goods",
    "TVSMOTOR.NS": "Automobile", "TVSSCS.NS": "Logistics", "TATACAP.NS": "Financial Services",
    "TATAPOWER.NS": "Power", "TEJASNET.NS": "Telecom", "TARIL.NS": "Capital Goods",
    "UJJIVANSFB.NS": "Banking", "WABAG.NS": "Capital Goods", "VBL.NS": "FMCG", "VEDL.NS": "Metals",
    "VIMTALABS.NS": "Healthcare", "VMM.NS": "Retail", "WAAREEENER.NS": "Renewable Energy",
    "WINDLAS.NS": "Pharmaceuticals", "YATHARTH.NS": "Healthcare",
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


def _quote_sector(x: dict) -> str:
    """Pull a sector/industry label off a search-quote dict if present (free)."""
    for f in ("sector", "sectorDisp", "industry", "industryDisp"):
        v = x.get(f)
        if v:
            return str(v).strip()
    return ""


# Corporate boilerplate that shouldn't count as a "significant" query word.
_STOP_TOKENS = {"ltd", "limited", "the", "of", "and", "co", "company"}


def _name_matches(query: str, candidate: str) -> bool:
    """Similarity guard so the first .NS hit can't be a different company
    ('Bank of India' -> SBI, 'PNB' -> PNB Gilts). True when the query's first
    significant word appears in the candidate name, or >=50% of the query's
    tokens do."""
    qt = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in _STOP_TOKENS]
    if not qt:
        return True
    ct = set(re.findall(r"[a-z0-9]+", candidate.lower()))
    if qt[0] in ct:
        return True
    return sum(1 for t in qt if t in ct) >= len(qt) / 2


def yahoo_search(name: str):
    """Return (symbol, yahoo_name, sector). sector is best-effort ('' if absent).
    Skips .NS hits whose name doesn't resemble the query — an unresolved name is
    better than a wrong company."""
    q = urllib.parse.urlencode({"q": name, "quotesCount": 8, "newsCount": 0})
    d = _get_json(f"https://query1.finance.yahoo.com/v1/finance/search?{q}")
    for x in (d or {}).get("quotes", []):
        if not str(x.get("symbol", "")).endswith(".NS"):
            continue
        yname = x.get("shortname") or x.get("longname") or ""
        if not _name_matches(name, yname):
            continue
        return x["symbol"], yname, _quote_sector(x)
    return None, None, ""


def yahoo_sector_by_symbol(symbol: str) -> str:
    """Free sector lookup: search by the exact symbol and read the quote's sector
    field (the v1 search endpoint carries sector/industry for NSE equities and is
    not crumb-gated). '' if unavailable."""
    if not symbol:
        return ""
    q = urllib.parse.urlencode({"q": symbol, "quotesCount": 8, "newsCount": 0})
    d = _get_json(f"https://query1.finance.yahoo.com/v1/finance/search?{q}", attempts=2)
    for x in (d or {}).get("quotes", []):
        if x.get("symbol") == symbol:
            return _quote_sector(x)
    # Fall back to the first .NS hit if exact symbol not surfaced.
    for x in (d or {}).get("quotes", []):
        if str(x.get("symbol", "")).endswith(".NS"):
            return _quote_sector(x)
    return ""


_CRUMB = {"crumb": None, "tried": False}


def _yahoo_crumb():
    """Fetch (and cache) a Yahoo crumb for query2 quoteSummary. None on failure."""
    if _CRUMB["tried"]:
        return _CRUMB["crumb"]
    _CRUMB["tried"] = True
    try:
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(__import__("http.cookiejar", fromlist=["CookieJar"]).CookieJar())
        )
        # Prime cookies, then request a crumb.
        opener.open(urllib.request.Request("https://fc.yahoo.com", headers=UA), timeout=15)
        req = urllib.request.Request(
            "https://query2.finance.yahoo.com/v1/test/getcrumb", headers=UA
        )
        crumb = opener.open(req, timeout=15).read().decode("utf-8").strip()
        if crumb and "<" not in crumb:
            _CRUMB["crumb"] = crumb
            _CRUMB["opener"] = opener
    except Exception:  # noqa: BLE001
        _CRUMB["crumb"] = None
    return _CRUMB["crumb"]


def yahoo_sector(symbol: str) -> str:
    """OPTIONAL assetProfile lookup (query2 + crumb). '' if it 401s/fails."""
    crumb = _yahoo_crumb()
    if not crumb:
        return ""
    url = (
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
        f"{urllib.parse.quote(symbol)}?modules=assetProfile&crumb={urllib.parse.quote(crumb)}"
    )
    try:
        opener = _CRUMB.get("opener") or urllib.request
        d = json.load(opener.open(urllib.request.Request(url, headers=UA), timeout=20))
        prof = d["quoteSummary"]["result"][0]["assetProfile"]
        return str(prof.get("sector") or prof.get("industry") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


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
    # is already priceable, e.g. "Netweb"/"NetWeb"). Indexed by every alias key
    # (full / parens stripped / parenthetical content) so "NCC" also matches
    # "NCC (Nagarjuna Construction)".
    alias_map = {}

    def register_priceable(name, entry):
        for k in alias_keys(name):
            alias_map.setdefault(k, entry)

    for n, v in out.items():
        if v.get("priceable"):
            register_priceable(n, v)
    # Cache sector by norm_key so each company is fetched at most once per run.
    sector_by_key = {norm_key(n): v["sector"]
                     for n, v in out.items() if v.get("sector")}

    def resolve_sector(name, sym, from_search):
        """Best-effort sector: search-quote field first (free), else optional
        assetProfile. Cached per company. Never raises."""
        k = norm_key(name)
        if sector_by_key.get(k):
            return sector_by_key[k]
        sec = from_search or (yahoo_sector(sym) if sym else "")
        if sec:
            sector_by_key[k] = sec
        return sec

    resolved = 0
    for name in sorted(names):
        prev = out.get(name, {})
        if name in OVERRIDES:
            # Overrides ALWAYS win: re-resolve unless the entry already carries
            # the override symbol, so a wrong mapping can't be frozen forever.
            if prev.get("priceable") and prev.get("symbol") == OVERRIDES[name]:
                continue
            sector_by_key.pop(norm_key(name), None)  # drop sector cached off the wrong company
        elif prev.get("priceable"):
            continue  # already good — preserve (sector backfilled separately below)
        else:
            # A different spelling of this company may already be priced; copy it
            # over so a raw-name lookup still hits (carries sector too).
            twin = next((alias_map[k] for k in alias_keys(name) if k in alias_map), None)
            if twin:
                out[name] = dict(twin)
                print(f"DUP  {name:42} -> {twin['symbol']} (alias)")
                continue
        if is_nonpriceable(name):
            out[name] = {"symbol": None, "yahoo_name": None, "priceable": False,
                         "note": "fund/option/index — not a single equity"}
            continue
        sym = OVERRIDES.get(name)
        yname = None
        search_sector = ""
        if not sym:
            sym, yname, search_sector = yahoo_search(name)
            time.sleep(0.3)
        last, cur = (validate(sym) if sym else (None, None))
        if sym and last:
            sector = resolve_sector(name, sym, search_sector)
            out[name] = {"symbol": sym, "yahoo_name": yname, "priceable": True,
                         "last_close": round(last, 2), "currency": cur,
                         "sector": sector}
            register_priceable(name, out[name])
            resolved += 1
            print(f"OK   {name:42} -> {sym:16} {yname or ''} [{sector or '-'}]")
        else:
            out[name] = {"symbol": sym, "yahoo_name": yname, "priceable": False,
                         "note": "unresolved / no price data"}
            print(f"MISS {name:42} -> {sym}")
        time.sleep(0.2)

    # Backfill sector for already-priceable entries missing one (idempotent,
    # one lookup per company, never clobbers an existing value). Prefer the free
    # v1-search sector field (works without a crumb); only if that's empty try the
    # crumb-gated assetProfile (which 401s from some IPs — that's fine, we skip).
    backfilled = 0
    for name, v in out.items():
        if not v.get("priceable") or v.get("sector"):
            continue
        k = norm_key(name)
        sym = v.get("symbol")
        sec = sector_by_key.get(k)
        if not sec and sym:
            # Free v1-search sector first (works without a crumb), then the
            # crumb-gated assetProfile, then the curated offline fallback.
            sec = yahoo_sector_by_symbol(sym) or yahoo_sector(sym) or SECTOR_OVERRIDES.get(sym, "")
            time.sleep(0.25)
            if sec:
                sector_by_key[k] = sec
        if sec:
            v["sector"] = sec
            backfilled += 1

    json.dump(out, open("tickers.json", "w"), ensure_ascii=False, indent=2)
    pr = sum(1 for v in out.values() if v.get("priceable"))
    sec_n = sum(1 for v in out.values() if v.get("sector"))
    print(f"\nWrote tickers.json: {pr}/{len(out)} priceable "
          f"({resolved} newly resolved this run; {sec_n} have sector, +{backfilled} backfilled).")


if __name__ == "__main__":
    main()
