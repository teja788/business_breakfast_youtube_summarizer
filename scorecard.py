#!/usr/bin/env python3
"""Performance scorecard for the analysts' BUY calls.

For each analyst+stock, takes the EARLIEST Buy/Add/Accumulate date as the entry,
fetches the NSE close on/after that date (entry) and the latest close (current)
from Yahoo Finance, and computes the return — plus Nifty's return over the same
window (so you can see alpha vs just holding the index).

Inputs : output/kutumba_rao/*.buys.json, output/kranti/*.kranti.json, tickers.json
Outputs: output/scorecard/scorecard.md, scorecard.csv
No third-party deps (stdlib urllib). Prices are indicative, not investment advice.
"""
import csv, json, glob, time, urllib.request, urllib.parse, datetime as dt

UA = {"User-Agent": "Mozilla/5.0"}
BUY_ACTIONS = ("Buy", "Add", "Accumulate")
NIFTY = "^NSEI"
_cache = {}


def _chart(symbol, start_epoch, end_epoch):
    key = (symbol, start_epoch // 86400)
    if key in _cache:
        return _cache[key]
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?period1={start_epoch}&period2={end_epoch}&interval=1d")
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25))
        r = d["chart"]["result"][0]
        ts = r["timestamp"]
        cl = r["indicators"]["quote"][0]["close"]
        series = [(t, c) for t, c in zip(ts, cl) if c is not None]
        _cache[key] = series
        return series
    except Exception:
        _cache[key] = []
        return []


def entry_and_current(symbol, call_date):
    start = int(dt.datetime(call_date.year, call_date.month, call_date.day).timestamp())
    end = int(time.time())
    s = _chart(symbol, start, end)
    if len(s) < 2:
        return None
    return s[0][1], s[-1][1], len(s)  # entry close, current close, trading days


def load_calls():
    """Return {analyst: {stock: {'date':earliest_buy_date, 'actions':set}}}."""
    out = {"Kutumba Rao": {}, "Kranthi": {}}

    def add(analyst, stock, date, action):
        d = out[analyst].setdefault(stock, {"date": date, "actions": set()})
        d["actions"].add(action)
        if date < d["date"]:
            d["date"] = date

    for f in glob.glob("output/kutumba_rao/*.buys.json"):
        j = json.load(open(f))
        date = dt.date.fromisoformat(j["date"])
        for r in j["recommendations"]:
            if r.get("action") in BUY_ACTIONS:
                add("Kutumba Rao", r["stock"].strip(), date, r["action"])
    for f in glob.glob("output/kranti/*.kranti.json"):
        j = json.load(open(f))
        date = dt.date.fromisoformat(j["date"])
        for c in j["calls"]:
            if c.get("action") in BUY_ACTIONS:
                add("Kranthi", c["stock"].strip(), date, c["action"])
    return out


def main():
    tickers = json.load(open("tickers.json"))
    calls = load_calls()
    rows = []
    for analyst, stocks in calls.items():
        for stock, info in stocks.items():
            t = tickers.get(stock)
            if not t or not t.get("priceable"):
                rows.append({"analyst": analyst, "stock": stock, "symbol": (t or {}).get("symbol"),
                             "call_date": info["date"].isoformat(), "status": "no-price"})
                continue
            res = entry_and_current(t["symbol"], info["date"])
            if not res:
                rows.append({"analyst": analyst, "stock": stock, "symbol": t["symbol"],
                             "call_date": info["date"].isoformat(), "status": "no-data"})
                continue
            entry, cur, _ = res
            nif = entry_and_current(NIFTY, info["date"])
            nret = ((nif[1] / nif[0] - 1) * 100) if nif else None
            ret = (cur / entry - 1) * 100
            rows.append({
                "analyst": analyst, "stock": stock, "symbol": t["symbol"],
                "call_date": info["date"].isoformat(),
                "actions": "/".join(sorted(info["actions"])),
                "entry": round(entry, 2), "current": round(cur, 2),
                "return_pct": round(ret, 1),
                "nifty_pct": round(nret, 1) if nret is not None else None,
                "alpha_pct": round(ret - nret, 1) if nret is not None else None,
                "status": "ok"})
            time.sleep(0.15)

    scored = [r for r in rows if r["status"] == "ok"]
    scored.sort(key=lambda r: (r["analyst"], -r["return_pct"]))

    import os
    os.makedirs("output/scorecard", exist_ok=True)
    # CSV
    cols = ["analyst", "stock", "symbol", "call_date", "actions", "entry", "current",
            "return_pct", "nifty_pct", "alpha_pct", "status"]
    with open("output/scorecard/scorecard.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})

    today = dt.date.fromtimestamp(time.time()).isoformat()
    with open("output/scorecard/scorecard.md", "w") as fh:
        fh.write(f"# Analyst BUY-call performance scorecard\n\n")
        fh.write(f"_As of {today}. Entry = NSE close on/after the analyst's FIRST "
                 f"Buy/Add/Accumulate date for that stock; return = vs latest close. "
                 f"Nifty = same-window index return; alpha = return − Nifty. "
                 f"Prices via Yahoo Finance, indicative only — not investment advice._\n\n")
        for analyst in ("Kutumba Rao", "Kranthi"):
            a = [r for r in scored if r["analyst"] == analyst]
            if not a:
                continue
            rets = [r["return_pct"] for r in a]
            alphas = [r["alpha_pct"] for r in a if r["alpha_pct"] is not None]
            win = sum(1 for x in rets if x > 0)
            fh.write(f"## {analyst}\n\n")
            fh.write(f"- Priced buy calls: **{len(a)}**\n")
            fh.write(f"- Win rate (positive): **{win}/{len(a)} = {100*win/len(a):.0f}%**\n")
            fh.write(f"- Average return: **{sum(rets)/len(rets):+.1f}%**  |  "
                     f"median: **{sorted(rets)[len(rets)//2]:+.1f}%**\n")
            if alphas:
                fh.write(f"- Average alpha vs Nifty: **{sum(alphas)/len(alphas):+.1f}%**\n")
            fh.write(f"- Best: {a[0]['stock']} ({a[0]['return_pct']:+.1f}%)  |  "
                     f"Worst: {a[-1]['stock']} ({a[-1]['return_pct']:+.1f}%)\n\n")
            fh.write("| Stock | Symbol | First buy | Action | Entry | Now | Return | vs Nifty |\n")
            fh.write("|---|---|---|---|--:|--:|--:|--:|\n")
            for r in a:
                fh.write(f"| {r['stock']} | {r['symbol']} | {r['call_date']} | {r['actions']} | "
                         f"{r['entry']} | {r['current']} | **{r['return_pct']:+.1f}%** | "
                         f"{r['alpha_pct']:+.1f}% |\n")
            fh.write("\n")
        unpriced = [r for r in rows if r["status"] != "ok"]
        if unpriced:
            fh.write(f"## Not priced ({len(unpriced)})\n\n")
            fh.write(", ".join(sorted(set(r["stock"] for r in unpriced))) + "\n")

    print(f"Scored {len(scored)} calls; {len(rows)-len(scored)} unpriced. "
          f"Wrote output/scorecard/scorecard.md + .csv")


if __name__ == "__main__":
    main()
