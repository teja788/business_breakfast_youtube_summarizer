/* Business Breakfast dashboard — reads split docs/data/*.json, renders 3 tabs +
   per-stock drill-down, global search, hash routing, CSV export, PWA. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// Mirrors analyst_calls.norm_key() so a stock name maps to the same drill-down key.
const normKey = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
const stockLink = (name) =>
  `<a class="stocklink" href="#/stock/${encodeURIComponent(normKey(name))}">${esc(name)}</a>`;

function badge(action) {
  const a = String(action || "").toLowerCase();
  let cls = "b-other";
  if (/(buy|accumulate|add)/.test(a)) cls = "b-buy";
  else if (/(hold|watch)/.test(a)) cls = "b-hold";
  else if (/(avoid|sell|book|exit|reduce)/.test(a)) cls = "b-avoid";
  return action ? `<span class="badge ${cls}">${esc(action)}</span>` : "";
}

const pct = (v) =>
  v == null ? '<span class="muted">—</span>' : `<span class="${v >= 0 ? "pos" : "neg"}">${v >= 0 ? "+" : ""}${v}%</span>`;

/* ---------- Data loading (split per tab, version-busted, memoized) ---------- */
const STATE = { ver: "", meta: null, recsRendered: false, epRendered: false, mini: null, lastTab: "scorecard" };

async function loadData(name) {
  if (STATE[name]) return STATE[name];
  const url = `data/${name}.json` + (STATE.ver ? `?v=${encodeURIComponent(STATE.ver)}` : "");
  // With a version query param the file is immutable per build → let the browser cache it.
  const res = await fetch(url, STATE.ver ? {} : { cache: "no-cache" });
  if (!res.ok) throw new Error(`${name}.json ${res.status}`);
  STATE[name] = await res.json();
  return STATE[name];
}

/* ---------- CSV export ---------- */
function toCSV(rows, cols) {
  const cell = (v) => {
    v = v == null ? "" : String(v);
    // Neutralize CSV/formula injection on text cells, but keep real numbers
    // (e.g. negative returns like "-10.6") numeric, not text.
    if (/^[=+\-@\t\r]/.test(v) && !Number.isFinite(Number(v))) v = "'" + v;
    return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
  };
  return [cols.join(",")].concat(rows.map((r) => cols.map((c) => cell(r[c])).join(","))).join("\n");
}
function download(name, text) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/* ---------- Sparkline (inline SVG, no lib) ---------- */
function sparkSVG(counts) {
  if (!counts || !counts.length || !counts.some((c) => c > 0)) return "";
  const w = 110, h = 22, max = Math.max(...counts, 1), n = counts.length;
  const step = n > 1 ? w / (n - 1) : 0;
  const pts = counts.map((c, i) => `${(i * step).toFixed(1)},${(h - 2 - (c / max) * (h - 5)).toFixed(1)}`).join(" ");
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="mentions over time"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>`;
}

/* ---------- Click-to-sort helpers (shared by the table tabs) ---------- */
function cmp(a, b) {
  const an = a == null || a === "";
  const bn = b == null || b === "";
  if (an || bn) return an && bn ? 0 : an ? 1 : -1;
  const na = Number(a);
  const nb = Number(b);
  if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}
const sortBy = (rows, key, dir) => (key ? [...rows].sort((x, y) => dir * cmp(x[key], y[key])) : rows);

function sortTh(label, key, state, cls = "", analyst = null) {
  const on = state.key === key;
  const arrow = on ? (state.dir > 0 ? " ▲" : " ▼") : "";
  const ariaSort = on ? (state.dir > 0 ? "ascending" : "descending") : "none";
  const analystAttr = analyst != null ? ` data-analyst="${esc(analyst)}"` : "";
  return `<th data-sort="${key}"${analystAttr}${cls ? ` class="${cls}"` : ""} role="button" tabindex="0" aria-sort="${ariaSort}">${label}${arrow}</th>`;
}
function applySort(state, key) {
  if (state.key === key) state.dir *= -1;
  else {
    state.key = key;
    state.dir = key === "call_date" || key === "last" || key === "date" ? -1 : 1;
  }
}
function wireSort(root, state, draw) {
  const handle = (th) => {
    applySort(state, th.dataset.sort);
    draw();
  };
  root.addEventListener("click", (e) => {
    const th = e.target.closest("th[data-sort]");
    if (th && root.contains(th)) handle(th);
  });
  root.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " " && e.key !== "Spacebar") return;
    const th = e.target.closest("th[data-sort]");
    if (!th || !root.contains(th)) return;
    if (e.key !== "Enter") e.preventDefault();
    handle(th);
  });
}

/* ---------- Year/month multi-select date filter (shared by all tabs) ---------- */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function makeDateFilter(dates) {
  const clean = dates.filter(Boolean);
  const years = [...new Set(clean.map((d) => d.slice(0, 4)))].sort();
  const months = [...new Set(clean.map((d) => d.slice(5, 7)))].sort();
  const selY = new Set();
  const selM = new Set();

  const chip = (attr, val, label) => `<button class="chip" data-${attr}="${val}">${label}</button>`;
  const html = () => {
    const yearPart =
      years.length > 1 ? `<span class="flabel">Year</span>${years.map((y) => chip("y", y, y)).join("")}` : "";
    const monthPart = `<span class="flabel">Month</span>${months
      .map((m) => chip("m", m, MONTHS[+m - 1] || m))
      .join("")}`;
    return `<div class="datefilter">${yearPart}${monthPart}<button class="chip clear" data-clear="1">Clear</button></div>`;
  };
  const active = () => selY.size > 0 || selM.size > 0;
  const match = (d) => {
    if (!d) return !active();
    return (selY.size === 0 || selY.has(d.slice(0, 4))) && (selM.size === 0 || selM.has(d.slice(5, 7)));
  };
  const wire = (root, onChange) => {
    const toggle = (set, val, btn) => {
      set.has(val) ? set.delete(val) : set.add(val);
      btn.classList.toggle("on");
      onChange();
    };
    root.querySelectorAll(".datefilter .chip[data-y]").forEach((b) => (b.onclick = () => toggle(selY, b.dataset.y, b)));
    root.querySelectorAll(".datefilter .chip[data-m]").forEach((b) => (b.onclick = () => toggle(selM, b.dataset.m, b)));
    root.querySelectorAll(".datefilter .chip.clear").forEach(
      (b) =>
        (b.onclick = () => {
          selY.clear();
          selM.clear();
          root.querySelectorAll(".datefilter .chip.on").forEach((c) => c.classList.remove("on"));
          onChange();
        })
    );
  };
  return { html, match, wire, active };
}

const r1 = (v) => (v == null ? null : Math.round(v * 10) / 10);
function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  const n = s.length;
  if (!n) return null;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}
function computeStats(rows) {
  const priced = rows.filter((r) => r.return_pct != null);
  if (!priced.length) return null;
  const rets = priced.map((r) => r.return_pct);
  const alphas = priced.map((r) => r.alpha_pct).filter((v) => v != null);
  const mean = (xs) => (xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : null);
  const best = priced.reduce((a, b) => (b.return_pct > a.return_pct ? b : a));
  const worst = priced.reduce((a, b) => (b.return_pct < a.return_pct ? b : a));
  return {
    priced: priced.length,
    wins: rets.filter((v) => v > 0).length,
    win_rate: r1((rets.filter((v) => v > 0).length / priced.length) * 100),
    avg_return: r1(mean(rets)),
    median_return: r1(median(rets)),
    avg_alpha: r1(mean(alphas)),
    best: { stock: best.stock, return_pct: best.return_pct },
    worst: { stock: worst.stock, return_pct: worst.return_pct },
  };
}

/* ---------- Scorecard ---------- */
function renderScorecard(sc) {
  const el = $("#scorecard");
  const df = makeDateFilter(sc.rows.map((r) => r.call_date));
  el.innerHTML = `<div class="toolbar">${df.html()}<button class="chip" id="scCsv">⭳ CSV</button></div><div id="scBody"></div>`;
  const analysts = Object.keys(sc.stats);
  const scSort = {};
  analysts.forEach((name) => (scSort[name] = { key: "return_pct", dir: -1 }));

  const draw = () => {
    $("#scBody").innerHTML =
      analysts
        .map((name) => {
          const st = scSort[name];
          const inRange = sc.rows.filter((r) => r.analyst === name && df.match(r.call_date));
          const s = df.active() ? computeStats(inRange) : sc.stats[name];
          if (!s) return "";
          const rows = sortBy(inRange.filter((r) => r.return_pct != null), st.key, st.dir);
          if (!rows.length) return "";
          const maxAbs = Math.max(...rows.map((r) => Math.abs(r.return_pct)), 1);
          const avg = (xs) => (xs.length ? r1(xs.reduce((a, b) => a + b, 0) / xs.length) : null);
          const openRets = rows.filter((r) => r.position !== "closed").map((r) => r.return_pct);
          const closedRets = rows.filter((r) => r.position === "closed").map((r) => r.return_pct);
          const splitLine =
            `<p class="muted" style="margin:0 0 10px;font-size:12.5px">` +
            `Open: ${openRets.length} (paper avg ${pct(avg(openRets))})` +
            (closedRets.length ? ` · Closed: ${closedRets.length} (realized avg ${pct(avg(closedRets))})` : "") +
            `</p>`;
          const cards = `
      <div class="cards">
        <div class="card"><div class="k">Priced calls</div><div class="v">${s.priced}</div></div>
        <div class="card"><div class="k">Win rate</div><div class="v">${s.win_rate}%</div></div>
        <div class="card"><div class="k">Avg return</div><div class="v">${pct(s.avg_return)}</div></div>
        <div class="card"><div class="k">Median</div><div class="v">${pct(s.median_return)}</div></div>
        <div class="card"><div class="k">Avg alpha</div><div class="v">${pct(s.avg_alpha)}</div></div>
        <div class="card"><div class="k">Best</div><div class="v">${pct(s.best.return_pct)}<div class="muted" style="font-size:12px;font-weight:400">${esc(s.best.stock)}</div></div></div>
      </div>`;
          const body = rows
            .map((r) => {
              const w = Math.round((Math.abs(r.return_pct) / maxAbs) * 90);
              const color = r.return_pct >= 0 ? "var(--green)" : "var(--red)";
              const closed = r.position === "closed";
              const statusCell = closed
                ? `<span class="pos-tag closed">Closed</span><span class="muted" style="font-size:11.5px"> ${esc(r.exit_date)}</span>`
                : `<span class="pos-tag open">Open</span>`;
              return `<tr>
        <td>${stockLink(r.stock)} ${badge(r.action)}</td>
        <td class="muted">${esc(r.symbol || "")}</td>
        <td class="muted">${esc(r.call_date)}</td>
        <td>${statusCell}</td>
        <td class="num">${pct(r.return_pct)}<span class="bar" style="width:${w}px;background:${color}"></span></td>
        <td class="num">${pct(r.alpha_pct)}</td>
      </tr>`;
            })
            .join("");
          return `<div class="analyst-block">
      <h2>${esc(name)}</h2>
      <p class="muted" style="margin:0 0 4px">Worst: ${pct(s.worst.return_pct)} ${esc(s.worst.stock)}</p>
      ${splitLine}
      ${cards}
      <div class="table-wrap"><table><thead><tr>${sortTh("Stock", "stock", st, "", name)}${sortTh("Symbol", "symbol", st, "", name)}${sortTh("First buy", "call_date", st, "", name)}${sortTh("Status", "position", st, "", name)}${sortTh("Return", "return_pct", st, "num", name)}${sortTh("vs Nifty", "alpha_pct", st, "num", name)}</tr></thead>
        <tbody>${body}</tbody></table></div>
    </div>`;
        })
        .join("") || '<p class="muted">No calls in the selected period.</p>';
  };
  df.wire(el, draw);
  const handleSc = (th) => {
    const name = th.dataset.analyst;
    if (name == null || !scSort[name]) return;
    applySort(scSort[name], th.dataset.sort);
    draw();
  };
  el.addEventListener("click", (e) => {
    const th = e.target.closest("th[data-sort]");
    if (th && el.contains(th)) handleSc(th);
  });
  el.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " " && e.key !== "Spacebar") return;
    const th = e.target.closest("th[data-sort]");
    if (!th || !el.contains(th)) return;
    if (e.key !== "Enter") e.preventDefault();
    handleSc(th);
  });
  $("#scCsv").onclick = () =>
    download(
      "scorecard.csv",
      toCSV(sc.rows, ["analyst", "stock", "symbol", "sector", "call_date", "exit_date", "position",
        "action", "entry", "current", "return_pct", "nifty_pct", "alpha_pct", "status"])
    );
  draw();
}

/* ---------- Recommendations ---------- */
const REC_CATEGORIES = [
  { key: "buy", label: "Buy / Accumulate" },
  { key: "hold", label: "Hold / Watch" },
  { key: "avoid", label: "Avoid / Sell" },
  { key: "other", label: "Mixed / Other" },
];

function recCategory(action) {
  const a = String(action || "").toLowerCase();
  const hits = [];
  if (/(avoid|sell|book|exit|reduce|switch out)/.test(a)) hits.push("avoid");
  if (/(buy|accumulate|add|apply|average)/.test(a)) hits.push("buy");
  if (/(hold|watch|wait)/.test(a)) hits.push("hold");
  return hits.length === 1 ? hits[0] : "other";
}

function canonicalAction(action) {
  let a = String(action || "").trim();
  if (!a) return a;
  a = a.replace(/\s*\/\s*switch\s+(?:out|into)\b/i, "");
  a = a.replace(/\s+on\s+dips?\b/i, "");
  a = a.replace(/\s*\(([^)]*)\)\s*$/, (m, inner) =>
    /\b(buy|sell|accumulate|add|avoid|exit|reduce|book|hold|watch|wait|switch)\b/i.test(inner) ? m : ""
  );
  return a.trim();
}

function recActionFilter(recs) {
  const actions = [...new Set(recs.map((r) => canonicalAction(r.action)).filter(Boolean))];
  const groups = REC_CATEGORIES.map((c) => {
    const opts = actions.filter((a) => recCategory(a) === c.key).sort();
    if (!opts.length) return "";
    const all = `<option value="cat:${c.key}">All ${esc(c.label)}</option>`;
    return `<optgroup label="${esc(c.label)}">${all}${opts.map((a) => `<option>${esc(a)}</option>`).join("")}</optgroup>`;
  }).join("");
  return `<option value="">All actions</option>${groups}`;
}

function renderRecs(recs) {
  const el = $("#recs");
  const df = makeDateFilter(recs.map((r) => r.last));
  el.innerHTML = `
    <div class="toolbar">
      <input id="recSearch" placeholder="Filter by stock or note…" />
      <select id="recAction">${recActionFilter(recs)}</select>
      <button class="chip" id="recCsv">⭳ CSV</button>
      <span class="muted" id="recCount"></span>
    </div>
    <div class="toolbar">${df.html()}</div>
    <div class="table-wrap"><table><thead id="recHead"></thead><tbody id="recBody"></tbody></table></div>`;
  const recSort = { key: null, dir: 1 };

  const draw = () => {
    const q = $("#recSearch").value.toLowerCase();
    const act = $("#recAction").value;
    const matchAct = act.startsWith("cat:")
      ? (r) => recCategory(canonicalAction(r.action)) === act.slice(4)
      : (r) => canonicalAction(r.action) === act;
    const filtered = sortBy(
      recs.filter(
        (r) =>
          (!act || matchAct(r)) &&
          df.match(r.last) &&
          (!q || ((r.stock || "") + " " + (r.summary || "")).toLowerCase().includes(q))
      ),
      recSort.key,
      recSort.dir
    );
    $("#recCount").textContent = `${filtered.length} of ${recs.length}`;
    $("#recHead").innerHTML = `<tr>${sortTh("Stock", "stock", recSort)}${sortTh("Action", "action", recSort)}${sortTh("Price/level", "price", recSort)}${sortTh("Summary", "summary", recSort)}<th>Trend</th>${sortTh("Last", "last", recSort)}${sortTh("Times", "times", recSort, "num")}</tr>`;
    $("#recBody").innerHTML = filtered
      .map(
        (r) => `<tr>
      <td><strong>${stockLink(r.stock)}</strong>${r.sector ? `<div class="muted" style="font-size:11px">${esc(r.sector)}</div>` : ""}</td>
      <td>${badge(r.action)}</td>
      <td class="muted">${esc(r.price)}</td>
      <td>${esc(r.summary)}</td>
      <td class="spark-cell">${sparkSVG(r.spark)}</td>
      <td class="muted">${esc(r.last)}</td>
      <td class="num">${esc(r.times)}</td>
    </tr>`
      )
      .join("");
  };
  $("#recSearch").addEventListener("input", draw);
  $("#recAction").addEventListener("change", draw);
  $("#recCsv").onclick = () =>
    download("recommendations.csv", toCSV(recs, ["stock", "symbol", "sector", "action", "price", "summary", "first", "last", "times"]));
  df.wire(el, draw);
  wireSort(el, recSort, draw);
  draw();
}

/* ---------- Episodes ---------- */
function recItems(list, fields) {
  if (!list || !list.length) return '<p class="muted">None recorded.</p>';
  return `<div class="reclist">${list
    .map(
      (r) => `
    <div class="recitem">
      <div class="top">
        <span class="stock">${stockLink(r.stock)}</span>
        ${badge(r.action)}
        ${r.price ? `<span class="price">${esc(r.price)}</span>` : ""}
      </div>
      <div class="note">${esc(r[fields] || "")}</div>
    </div>`
    )
    .join("")}</div>`;
}

function renderEpisodes(eps) {
  const el = $("#episodes");
  const df = makeDateFilter(eps.map((e) => e.date));
  el.innerHTML = `<div class="toolbar">${df.html()}<button class="chip" id="epSort"></button><span class="muted" id="epCount"></span></div><div id="epList"></div>`;
  let epDir = -1;

  const summaryCache = new Map();
  const summaryFor = (e) => {
    const cacheKey = e.stem != null ? e.stem : e;
    if (summaryCache.has(cacheKey)) return summaryCache.get(cacheKey);
    const html = e.summary_md ? DOMPurify.sanitize(marked.parse(e.summary_md)) : '<p class="muted">No summary.</p>';
    summaryCache.set(cacheKey, html);
    return html;
  };

  const draw = () => {
    $("#epSort").textContent = epDir < 0 ? "Date ▼ newest" : "Date ▲ oldest";
    const list = sortBy(eps.filter((e) => df.match(e.date)), "date", epDir);
    $("#epCount").textContent = `${list.length} of ${eps.length}`;
    $("#epList").innerHTML =
      list
        .map((e) => {
          const takeaways = (e.takeaways || []).length
            ? `<ul class="takeaways">${e.takeaways.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`
            : "";
          return `<details class="ep" data-stem="${esc(e.stem)}">
      <summary>
        <span><span class="date">${esc(e.date)}</span>${esc(e.title)}</span>
        <span class="pills">${(e.kutumba || []).length} KR · ${(e.kranti || []).length} Kranthi</span>
      </summary>
      <div class="ep-body">
        ${e.youtube_url ? `<p><a class="yt" href="${esc(e.youtube_url)}" target="_blank" rel="noopener">▶ Watch on YouTube</a></p>` : ""}
        ${takeaways ? `<h3>Key takeaways</h3>${takeaways}` : ""}
        <h3>Kutumba Rao — calls</h3>${recItems(e.kutumba, "note")}
        <h3>Kranthi — calls</h3>${recItems(e.kranti, "note")}
        <h3>Summary</h3><div class="ep-summary">${summaryFor(e)}</div>
      </div>
    </details>`;
        })
        .join("") || '<p class="muted">No episodes in the selected period.</p>';
  };
  df.wire(el, draw);
  $("#epSort").addEventListener("click", () => {
    epDir *= -1;
    draw();
  });
  draw();
}

/* ---------- Digest banner (latest + weekly) ---------- */
function renderDigest(meta) {
  const d = meta.weekly_digest || {};
  const lines = (d.lines || []).map((l) => `<li>${esc(l)}</li>`).join("");
  const latest = meta.latest
    ? `Latest episode: <a href="#/episode/${encodeURIComponent(meta.latest.stem)}">${esc(meta.latest.date)} — ${esc(meta.latest.title)}</a>`
    : "";
  $("#digest").innerHTML = `<div class="digest-inner">
    <div class="digest-h">This week${d.since ? ` <span class="muted">(since ${esc(d.since)})</span>` : ""}</div>
    ${lines ? `<ul>${lines}</ul>` : ""}
    ${latest ? `<div class="digest-latest">${latest}</div>` : ""}
  </div>`;
}

/* ---------- Per-stock drill-down ---------- */
async function openStock(key) {
  const overlay = $("#stockOverlay");
  const body = $("#sdBody");
  body.innerHTML = '<div class="loading">Loading…</div>';
  overlay.classList.add("on");
  document.body.classList.add("noscroll");
  $("#sdClose").focus(); // move keyboard focus into the dialog
  let s;
  try {
    s = (await loadData("stocks")).stocks[key];
  } catch (e) {
    body.innerHTML = `<p class="muted">Failed to load stock data.</p>`;
    return;
  }
  if (!s) {
    body.innerHTML = `<p class="muted">No calls found for this stock.</p>`;
    return;
  }
  const head = `<h2>${esc(s.name)} ${s.symbol ? `<span class="muted" style="font-size:13px">${esc(s.symbol)}</span>` : ""}</h2>
    <p class="muted">${s.sector ? esc(s.sector) + " · " : ""}${(s.mentions || []).length} mention(s) <span class="spark-inline">${sparkSVG(s.spark)}</span></p>`;
  const scTable =
    s.scorecard && s.scorecard.length
      ? `<h3>Performance vs Nifty</h3>
    <div class="table-wrap"><table><thead><tr><th>Analyst</th><th>First buy</th><th>Status</th><th class="num">Return</th><th class="num">vs Nifty</th></tr></thead>
    <tbody>${s.scorecard
      .map(
        (r) => `<tr><td>${esc(r.analyst)}</td><td class="muted">${esc(r.call_date)}</td>
        <td>${r.position === "closed" ? `<span class="pos-tag closed">Closed</span> <span class="muted" style="font-size:11.5px">${esc(r.exit_date)}</span>` : `<span class="pos-tag open">Open</span>`}</td>
        <td class="num">${pct(r.return_pct)}</td><td class="num">${pct(r.alpha_pct)}</td></tr>`
      )
      .join("")}</tbody></table></div>`
      : "";
  const mentions = `<h3>Calls timeline (${(s.mentions || []).length})</h3><div class="reclist">${(s.mentions || [])
    .map(
      (m) => `<div class="recitem">
      <div class="top"><span class="muted">${esc(m.date)}</span> <span class="stock">${esc(m.analyst)}</span> ${badge(m.action)} ${m.price ? `<span class="price">${esc(m.price)}</span>` : ""} ${m.stem ? `<a class="yt" href="#/episode/${encodeURIComponent(m.stem)}">episode →</a>` : ""}</div>
      <div class="note">${esc(m.detail || m.note || "")}</div>
    </div>`
    )
    .join("")}</div>`;
  body.innerHTML = head + scTable + mentions;
  body.scrollTop = 0;
}
function closeStock() {
  $("#stockOverlay").classList.remove("on");
  document.body.classList.remove("noscroll");
}

/* ---------- Episode deep-link ---------- */
async function openEpisode(stem) {
  await activateTab("episodes");
  const t = document.querySelector(`#epList details[data-stem="${(window.CSS && CSS.escape) ? CSS.escape(stem) : stem}"]`);
  if (t) {
    t.open = true;
    t.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

/* ---------- Global search (MiniSearch) ---------- */
async function ensureSearch() {
  if (STATE.mini) return;
  const d = await loadData("search");
  STATE.mini = new MiniSearch({
    fields: ["title", "text"],
    storeFields: ["title", "type", "ref"],
    searchOptions: { boost: { title: 2 }, prefix: true, fuzzy: 0.2 },
  });
  STATE.mini.addAll(d.docs);
}
function wireSearch() {
  const inp = $("#gsearch");
  const out = $("#gresults");
  if (!inp || !out) return;
  const run = async () => {
    const q = inp.value.trim();
    if (!q) {
      out.innerHTML = "";
      out.classList.remove("on");
      return;
    }
    try {
      await ensureSearch();
    } catch (e) {
      return;
    }
    const res = STATE.mini.search(q).slice(0, 12);
    out.innerHTML = res.length
      ? res
          .map((r) => {
            const href = r.type === "stock" ? `#/stock/${encodeURIComponent(r.ref)}` : `#/episode/${encodeURIComponent(r.ref)}`;
            const tag = r.type === "stock" ? "Stock" : "Episode";
            return `<a class="gr" href="${href}"><span class="gr-tag gr-${r.type}">${tag}</span> ${esc(r.title)}</a>`;
          })
          .join("")
      : `<div class="gr muted">No matches</div>`;
    out.classList.add("on");
  };
  inp.addEventListener("input", run);
  inp.addEventListener("focus", () => inp.value.trim() && run());
  out.addEventListener("click", (e) => {
    // Hide the dropdown when a result is picked (covers clicking a result whose
    // href equals the current hash, which fires no hashchange).
    if (e.target.closest(".gr")) out.classList.remove("on");
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-wrap")) out.classList.remove("on");
  });
}

/* ---------- Tabs + routing ---------- */
async function activateTab(name) {
  if (!name) name = "scorecard";
  STATE.lastTab = name;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === name));
  try {
    if (name === "recs" && !STATE.recsRendered) {
      STATE.recsRendered = true;
      renderRecs((await loadData("recs")).rows);
    }
    if (name === "episodes" && !STATE.epRendered) {
      STATE.epRendered = true;
      renderEpisodes((await loadData("episodes")).episodes);
    }
  } catch (e) {
    if (name === "recs") STATE.recsRendered = false;
    if (name === "episodes") STATE.epRendered = false;
    $("#" + name).innerHTML = `<div class="loading">Failed to load — ${esc(e.message)}</div>`;
  }
}
function initTabs() {
  document.querySelectorAll("#tabs button").forEach((btn) => {
    btn.addEventListener("click", () => (location.hash = `#/tab/${btn.dataset.tab}`));
  });
}
function handleRoute() {
  $("#gresults") && $("#gresults").classList.remove("on");
  const h = location.hash.replace(/^#/, "");
  const m = h.match(/^\/(tab|stock|episode)\/(.+)$/);
  if (!m) {
    closeStock();
    return;
  }
  const kind = m[1];
  const val = decodeURIComponent(m[2]);
  if (kind === "stock") {
    openStock(val);
  } else {
    closeStock();
    if (kind === "tab") activateTab(val);
    else if (kind === "episode") openEpisode(val);
  }
}

/* ---------- PWA ---------- */
function registerSW() {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
  }
}

/* ---------- Boot ---------- */
async function boot() {
  document.querySelectorAll(".tab").forEach((t) => (t.innerHTML = '<div class="loading">Loading…</div>'));
  try {
    const meta = await (await fetch("data/meta.json", { cache: "no-cache" })).json();
    STATE.ver = meta.generated_at || "";
    STATE.meta = meta;
    $("#generated").textContent = "Updated " + (meta.generated_at || "");
    renderDigest(meta);
    renderScorecard(await loadData("scorecard"));
    initTabs();
    wireSearch();
    $("#sdClose").onclick = () => (location.hash = `#/tab/${STATE.lastTab || "scorecard"}`);
    $("#stockOverlay").addEventListener("click", (e) => {
      if (e.target.id === "stockOverlay") location.hash = `#/tab/${STATE.lastTab || "scorecard"}`;
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && $("#stockOverlay").classList.contains("on"))
        location.hash = `#/tab/${STATE.lastTab || "scorecard"}`;
    });
    window.addEventListener("hashchange", handleRoute);
    handleRoute(); // apply any deep link on load
    registerSW();
  } catch (err) {
    $("#scorecard").innerHTML = `<div class="loading">Failed to load data — ${esc(err.message)}</div>`;
  }
}
boot();
