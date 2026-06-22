#!/usr/bin/env python3
"""Performance scorecard for the analysts' BUY calls.

For each analyst+stock, the EARLIEST Buy/Add/Accumulate date is the entry. If a
later Sell/Reduce/Book-Profit on the SAME stock follows that entry, the position
is treated as CLOSED and scored entry→that exit (realized return); otherwise it
is OPEN and scored entry→latest close (paper return). Both the stock and Nifty
are aligned to the SAME trading days (first common day on/after entry, and the
exit/last day) so the alpha window matches.

Inputs : output/kutumba_rao/*.buys.json, output/kranti/*.kranti.json, tickers.json
Outputs: output/scorecard/scorecard.md, scorecard.csv
No third-party deps (stdlib urllib). Prices are indicative, not investment advice.
"""
import csv, json, glob, os, time, urllib.request, urllib.parse, datetime as dt

from analyst_calls import is_buy, is_sell, norm_key

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
    return int(dt.datetime(d.year, d.month, d.day).timestamp())


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
            ts, cl = r["timestamp"], r["indicators"]["quote"][0]["close"]
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
    """Return {analyst: {stock: {'buys':[dates], 'sells':[dates], 'buy_actions':set}}},
    keeping only stocks with at least one buy."""
    out = {"Kutumba Rao": {}, "Kranthi": {}}

    def add(analyst, stock, date, action):
        d = out[analyst].setdefault(stock, {"buys": [], "sells": [], "buy_actions": set()})
        if is_buy(action):
            d["buys"].append(date)
            d["buy_actions"].add(action)
        if is_sell(action):
            d["sells"].append(date)

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

    return {a: {s: v for s, v in stocks.items() if v["buys"]} for a, stocks in out.items()}


def build_ticker_index(tickers):
    """Normalised-name -> entry, preferring priceable entries, so spelling variants
    ('NetWeb'/'Netweb') still resolve."""
    idx = {}
    for name, v in tickers.items():
        k = norm_key(name)
        if k not in idx or (v.get("priceable") and not idx[k].get("priceable")):
            idx[k] = v
    return idx


def median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main():
    tickers = json.load(open("tickers.json"))
    idx = build_ticker_index(tickers)
    calls = load_calls()
    rows = []
    for analyst, stocks in calls.items():
        for stock, info in stocks.items():
            entry_date = min(info["buys"])
            later_sells = [d for d in info["sells"] if d > entry_date]
            exit_date = min(later_sells) if later_sells else None
            t = tickers.get(stock) or idx.get(norm_key(stock))
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

    os.makedirs("output/scorecard", exist_ok=True)
    cols = ["analyst", "stock", "symbol", "call_date", "exit_date", "position", "actions",
            "entry", "current", "return_pct", "nifty_pct", "alpha_pct", "status"]
    with open("output/scorecard/scorecard.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})

    today = dt.date.fromtimestamp(time.time()).isoformat()
    with open("output/scorecard/scorecard.md", "w") as fh:
        fh.write("# Analyst BUY-call performance scorecard\n\n")
        fh.write(f"_As of {today}. Entry = NSE close on/after the analyst's FIRST "
                 f"Buy/Add/Accumulate date for that stock. A position is **closed** at the "
                 f"first later Sell/Reduce/Book-Profit (realized return), else **open** and "
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
