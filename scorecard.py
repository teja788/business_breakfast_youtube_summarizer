#!/usr/bin/env python3
"""Performance scorecard for the analysts' BUY calls.

For each analyst+company, the EARLIEST Buy/Add/Accumulate date is the entry.
Spelling variants of the same company are merged into ONE position (matched by
norm_key, and additionally by resolved ticker symbol, so "SBI" / "State Bank of
India" or "Hyundai Motors" / "Hyundai Motor India" don't split). If a later
Sell/Reduce/Book-Profit — or an Avoid issued after the buy — on the SAME company
follows that entry, the position is treated as CLOSED and scored entry→that exit
(realized return); otherwise it is OPEN and scored entry→latest close (paper
return). Both the stock and Nifty are aligned to the SAME trading days (first
common day on/after entry, and the exit/last day) so the alpha window matches.

Inputs : output/kutumba_rao/*.buys.json, output/kranti/*.kranti.json, tickers.json
Outputs: output/scorecard/scorecard.md, scorecard.csv
No third-party deps (stdlib urllib). Prices are indicative, not investment advice.
"""
import csv, json, glob, os, re, time, urllib.request, urllib.parse, datetime as dt

from analyst_calls import SELL_WORDS, _tokens, alias_keys, is_buy, norm_key

# Scorecard-only exit test: an "Avoid" issued AFTER a prior buy also closes the
# position. Deliberately local — other consumers of analyst_calls (buy table,
# dashboard) keep the shared is_sell() = Sell/Reduce/Book semantics.
EXIT_WORDS = SELL_WORDS | {"avoid"}


def is_exit(action):
    """True for calls that close a scorecard position (Sell/Reduce/Book/Avoid)."""
    return bool(_tokens(action) & EXIT_WORDS)

UA = {"User-Agent": "Mozilla/5.0"}
NIFTY = "^NSEI"
_cache = {}


def _get_json(url, attempts=4):
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


def _epoch(d):
    # Pinned to UTC so results don't depend on the runner's local timezone.
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


def _series(symbol, start_epoch, end_epoch):
    """Daily (epoch_day, close) list for a symbol over the window, cached per start-day."""
    key = (symbol, start_epoch // 86400)
    if key in _cache:
        return _cache[key]
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?period1={start_epoch}&period2={end_epoch}&interval=1d")
    d = _get_json(url)
    series = []
    if d:
        try:
            r = d["chart"]["result"][0]
            ts, ind = r["timestamp"], r["indicators"]
            # Prefer ADJUSTED closes so corporate actions (splits, demergers,
            # dividends) don't show up as phantom moves; fall back to raw closes.
            adj = (ind.get("adjclose") or [{}])[0].get("adjclose")
            cl = adj if adj and any(c is not None for c in adj) else ind["quote"][0]["close"]
            series = [(t // 86400, c) for t, c in zip(ts, cl) if c is not None]
        except Exception:  # noqa: BLE001
            series = []
    _cache[key] = series
    return series


def position_return(symbol, entry_date, exit_date):
    """Entry/current closes for a position, with the stock and Nifty aligned to the
    SAME trading days. Closes at `exit_date` if given (realized), else latest (paper).
    Returns dict {entry, current, n_entry, n_current, tdays} or None if no data."""
    start = _epoch(entry_date)
    end = int(time.time())
    ss = _series(symbol, start, end)
    if len(ss) < 2:
        return None
    ns = _series(NIFTY, start, end)
    sd = dict(ss)
    nd = dict(ns)
    # Days where BOTH the stock and Nifty traded (so alpha is over one window).
    common = sorted(d for d in sd if d in nd) if nd else sorted(sd)
    if len(common) < 2:
        common, nd = sorted(sd), {}
    start_day = start // 86400
    days = [d for d in common if d >= start_day]
    if len(days) < 2:
        return None
    d_entry = days[0]
    if exit_date:
        exit_day = _epoch(exit_date) // 86400
        after = [d for d in common if d >= exit_day and d > d_entry]
        d_exit = after[0] if after else common[-1]
    else:
        d_exit = common[-1]
    if d_exit <= d_entry:
        return None
    tdays = sum(1 for d in common if d_entry <= d <= d_exit)
    return {"entry": sd[d_entry], "current": sd[d_exit],
            "n_entry": nd.get(d_entry), "n_current": nd.get(d_exit), "tdays": tdays}


def load_calls():
    """Return {analyst: {norm_key: group}} where a group merges every spelling
    variant of a company: 'names' = {buy variant -> its earliest buy date} (the
    overall-earliest one becomes the display name), 'raw' = all variant spellings
    seen (for ticker lookup), 'buys'/'sells' = all buy/exit dates, 'buy_actions'
    = buy labels. Groups with neither a buy nor an exit are dropped; exit-only
    groups are KEPT so a sell filed under a variant name can still close the
    matching position after the symbol merge in main()."""
    out = {"Kutumba Rao": {}, "Kranthi": {}}

    def add(analyst, stock, date, action):
        g = out[analyst].setdefault(norm_key(stock), {
            "names": {}, "raw": set(), "buys": [], "sells": [], "buy_actions": set()})
        g["raw"].add(stock)
        if is_buy(action):
            g["buys"].append(date)
            g["buy_actions"].add(action)
            g["names"][stock] = min(date, g["names"].get(stock, date))
        if is_exit(action):
            g["sells"].append(date)

    for f in glob.glob("output/kutumba_rao/*.buys.json"):
        j = json.load(open(f))
        date = dt.date.fromisoformat(j["date"])
        for r in j["recommendations"]:
            add("Kutumba Rao", r["stock"].strip(), date, r.get("action"))
    for f in glob.glob("output/kranti/*.kranti.json"):
        j = json.load(open(f))
        date = dt.date.fromisoformat(j["date"])
        for c in j["calls"]:
            add("Kranthi", c["stock"].strip(), date, c.get("action"))

    return {a: {k: g for k, g in groups.items() if g["buys"] or g["sells"]}
            for a, groups in out.items()}


# Corporate boilerplate ignored by the loose key below.
_GENERIC_TOKENS = {"india", "ltd", "limited", "the", "of", "and"}


def _loose_key(name):
    """Last-resort matching key: parentheticals and generic tokens dropped, a
    plural 's' trimmed — so 'Hyundai Motor India' == 'Hyundai Motors'."""
    base = re.sub(r"\([^)]*\)", " ", name or "")
    toks = [t for t in re.findall(r"[a-z0-9]+", base.lower()) if t not in _GENERIC_TOKENS]
    return "".join(t[:-1] if len(t) > 3 and t.endswith("s") else t for t in toks)


def build_ticker_index(tickers):
    """Two lookup maps, preferring priceable entries on collisions: `idx` keys
    every entry by its norm/alias keys ('NetWeb'/'Netweb', parenthetical forms
    like 'Vedanta (post-demerger)' -> 'Vedanta'); `loose` keys it by _loose_key
    so exit-call spellings ('Hyundai Motor India') still resolve."""
    idx, loose = {}, {}

    def put(m, k, v):
        if k and (k not in m or (v.get("priceable") and not m[k].get("priceable"))):
            m[k] = v

    for name, v in tickers.items():
        for k in alias_keys(name):
            put(idx, k, v)
        put(loose, _loose_key(name), v)
    return idx, loose


def lookup_ticker(raw_names, tickers, idx, loose):
    """Resolve a call-group (all its spelling variants) to a tickers.json entry:
    exact raw names first, then norm/alias keys, then the loose key. Returns the
    first priceable hit in that order, else the first hit, else None."""
    ordered = sorted(raw_names)
    tiers = (
        [tickers[n] for n in ordered if n in tickers],
        [idx[k] for n in ordered for k in alias_keys(n) if k in idx],
        [loose[k] for n in ordered if (k := _loose_key(n)) in loose],
    )
    first = None
    for hits in tiers:
        for h in hits:
            if h.get("priceable"):
                return h
            first = first or h
    return first


def median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main():
    tickers = json.load(open("tickers.json"))
    idx, loose = build_ticker_index(tickers)
    calls = load_calls()
    rows = []
    for analyst, groups in calls.items():
        # Second merge pass: different norm-keys that resolve to the SAME ticker
        # symbol ("Suzlon"/"Suzlon Energy", "Hyundai Motors"/"Hyundai Motor
        # India") are one position, and an exit filed under any variant closes it.
        merged = {}
        for key, g in sorted(groups.items()):
            t = lookup_ticker(g["raw"], tickers, idx, loose)
            mkey = (t or {}).get("symbol") or "#" + key
            m = merged.get(mkey)
            if m:
                m["raw"] |= g["raw"]
                m["buys"] += g["buys"]
                m["sells"] += g["sells"]
                m["buy_actions"] |= g["buy_actions"]
                for n, d in g["names"].items():
                    m["names"][n] = min(d, m["names"].get(n, d))
            else:
                merged[mkey] = {**g, "ticker": t}
        for info in merged.values():
            if not info["buys"]:
                continue  # exit/avoid-only variants that never matched a buy
            entry_date = min(info["buys"])
            # Display name = the spelling used on that earliest buy call.
            stock = min(info["names"], key=lambda n: (info["names"][n], n))
            later_sells = [d for d in info["sells"] if d > entry_date]
            exit_date = min(later_sells) if later_sells else None
            t = info["ticker"]
            base = {"analyst": analyst, "stock": stock, "symbol": (t or {}).get("symbol"),
                    "call_date": entry_date.isoformat(),
                    "exit_date": exit_date.isoformat() if exit_date else "",
                    "position": "closed" if exit_date else "open",
                    "actions": "/".join(sorted(info["buy_actions"]))}
            if not t or not t.get("priceable"):
                rows.append({**base, "status": "no-price"})
                continue
            res = position_return(t["symbol"], entry_date, exit_date)
            if not res:
                rows.append({**base, "status": "no-data"})
                continue
            entry, cur = res["entry"], res["current"]
            ret = (cur / entry - 1) * 100
            nret = ((res["n_current"] / res["n_entry"] - 1) * 100
                    if res["n_entry"] and res["n_current"] else None)
            rows.append({**base,
                         "entry": round(entry, 2), "current": round(cur, 2),
                         "return_pct": round(ret, 1),
                         "nifty_pct": round(nret, 1) if nret is not None else None,
                         "alpha_pct": round(ret - nret, 1) if nret is not None else None,
                         "status": "ok"})
            time.sleep(0.15)

    scored = [r for r in rows if r["status"] == "ok"]
    scored.sort(key=lambda r: (r["analyst"], -r["return_pct"]))

    # No-data guard: if a previous scorecard exists and this run priced fewer
    # than half as many rows, assume a Yahoo outage and refuse to overwrite it.
    csv_path = "output/scorecard/scorecard.csv"
    if os.path.exists(csv_path):
        with open(csv_path, newline="") as fh:
            prev_ok = sum(1 for r in csv.DictReader(fh) if r.get("status") == "ok")
        if len(scored) < 0.5 * prev_ok:
            print(f"ERROR: only {len(scored)} rows priced ok vs {prev_ok} in the existing "
                  f"scorecard (<50%) — refusing to overwrite. Yahoo may be down; not writing.")
            raise SystemExit(1)

    os.makedirs("output/scorecard", exist_ok=True)
    cols = ["analyst", "stock", "symbol", "call_date", "exit_date", "position", "actions",
            "entry", "current", "return_pct", "nifty_pct", "alpha_pct", "status"]
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})

    today = dt.date.fromtimestamp(time.time()).isoformat()
    with open("output/scorecard/scorecard.md", "w") as fh:
        fh.write("# Analyst BUY-call performance scorecard\n\n")
        fh.write(f"_As of {today}. Entry = NSE close on/after the analyst's FIRST "
                 f"Buy/Add/Accumulate date for that stock (name variants merged). A position "
                 f"is **closed** at the first later Sell/Reduce/Book-Profit/Avoid (realized "
                 f"return), else **open** and "
                 f"marked to the latest close (paper return). Nifty = same-window index return "
                 f"on the SAME trading days; alpha = return − Nifty. Prices via Yahoo Finance, "
                 f"indicative only — not investment advice._\n\n")
        for analyst in ("Kutumba Rao", "Kranthi"):
            a = [r for r in scored if r["analyst"] == analyst]
            if not a:
                continue
            rets = [r["return_pct"] for r in a]
            alphas = [r["alpha_pct"] for r in a if r["alpha_pct"] is not None]
            closed = [r for r in a if r["position"] == "closed"]
            open_ = [r for r in a if r["position"] == "open"]
            win = sum(1 for x in rets if x > 0)
            fh.write(f"## {analyst}\n\n")
            fh.write(f"- Priced buy calls: **{len(a)}**  (open: {len(open_)} · closed: {len(closed)})\n")
            fh.write(f"- Win rate (positive): **{win}/{len(a)} = {100*win/len(a):.0f}%**\n")
            fh.write(f"- Average return: **{sum(rets)/len(rets):+.1f}%**  |  "
                     f"median: **{median(rets):+.1f}%**\n")
            if open_:
                o = [r["return_pct"] for r in open_]
                fh.write(f"- Open/paper: avg **{sum(o)/len(o):+.1f}%** over {len(o)} calls\n")
            if closed:
                c = [r["return_pct"] for r in closed]
                fh.write(f"- Closed/realized: avg **{sum(c)/len(c):+.1f}%** over {len(c)} calls\n")
            if alphas:
                fh.write(f"- Average alpha vs Nifty: **{sum(alphas)/len(alphas):+.1f}%**\n")
            fh.write(f"- Best: {a[0]['stock']} ({a[0]['return_pct']:+.1f}%)  |  "
                     f"Worst: {a[-1]['stock']} ({a[-1]['return_pct']:+.1f}%)\n\n")
            fh.write("| Stock | Symbol | First buy | Action | Status | Entry | Exit/Now | Return | vs Nifty |\n")
            fh.write("|---|---|---|---|---|--:|--:|--:|--:|\n")
            for r in a:
                status = f"closed {r['exit_date']}" if r["position"] == "closed" else "open"
                alpha = f"{r['alpha_pct']:+.1f}%" if r["alpha_pct"] is not None else "—"
                fh.write(f"| {r['stock']} | {r['symbol']} | {r['call_date']} | {r['actions']} | "
                         f"{status} | {r['entry']} | {r['current']} | **{r['return_pct']:+.1f}%** | "
                         f"{alpha} |\n")
            fh.write("\n")
        unpriced = [r for r in rows if r["status"] != "ok"]
        if unpriced:
            fh.write(f"## Not priced ({len(unpriced)})\n\n")
            fh.write(", ".join(sorted(set(r["stock"] for r in unpriced))) + "\n")

    closed_n = sum(1 for r in scored if r["position"] == "closed")
    print(f"Scored {len(scored)} calls ({closed_n} closed/realized, {len(scored)-closed_n} open); "
          f"{len(rows)-len(scored)} unpriced. Wrote output/scorecard/scorecard.md + .csv")


if __name__ == "__main__":
    main()
