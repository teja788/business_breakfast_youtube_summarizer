/* Business Breakfast dashboard — reads docs/data.json, renders 3 tabs. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

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

/* ---------- Year/month multi-select date filter (shared by all tabs) ---------- */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Returns { html(), match(dateStr), wire(root, onChange) }. With nothing selected
// everything matches; selecting years and/or months narrows (OR within each axis,
// AND across axes). Dates are "YYYY-MM-DD" strings.
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
// Recompute an analyst's scorecard stats from a (possibly date-filtered) row set.
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
  el.innerHTML = `<div class="toolbar">${df.html()}</div><div id="scBody"></div>`;
  const analysts = Object.keys(sc.stats);

  const draw = () => {
  $("#scBody").innerHTML = analysts.map((name) => {
    const inRange = sc.rows.filter((r) => r.analyst === name && df.match(r.call_date));
    // Unfiltered view keeps the exact server-computed stats; recompute only when narrowed.
    const s = df.active() ? computeStats(inRange) : sc.stats[name];
    if (!s) return "";
    const rows = inRange
      .filter((r) => r.return_pct != null)
      .sort((a, b) => b.return_pct - a.return_pct);
    if (!rows.length) return "";
    const maxAbs = Math.max(...rows.map((r) => Math.abs(r.return_pct)), 1);
    const cards = `
      <div class="cards">
        <div class="card"><div class="k">Priced calls</div><div class="v">${s.priced}</div></div>
        <div class="card"><div class="k">Win rate</div><div class="v">${s.win_rate}%</div></div>
        <div class="card"><div class="k">Avg return</div><div class="v">${pct(s.avg_return)}</div></div>
        <div class="card"><div class="k">Median</div><div class="v">${pct(s.median_return)}</div></div>
        <div class="card"><div class="k">Avg alpha</div><div class="v">${pct(s.avg_alpha)}</div></div>
        <div class="card"><div class="k">Best</div><div class="v">${pct(s.best.return_pct)}<div class="muted" style="font-size:12px;font-weight:400">${esc(s.best.stock)}</div></div></div>
      </div>`;
    const body = rows.map((r) => {
      const w = Math.round((Math.abs(r.return_pct) / maxAbs) * 90);
      const color = r.return_pct >= 0 ? "var(--green)" : "var(--red)";
      return `<tr>
        <td>${esc(r.stock)} ${badge(r.action)}</td>
        <td class="muted">${esc(r.symbol || "")}</td>
        <td class="muted">${esc(r.call_date)}</td>
        <td class="num">${pct(r.return_pct)}<span class="bar" style="width:${w}px;background:${color}"></span></td>
        <td class="num">${pct(r.alpha_pct)}</td>
      </tr>`;
    }).join("");
    return `<div class="analyst-block">
      <h2>${esc(name)}</h2>
      <p class="muted" style="margin:0 0 4px">Worst: ${pct(s.worst.return_pct)} ${esc(s.worst.stock)}</p>
      ${cards}
      <table><thead><tr><th>Stock</th><th>Symbol</th><th>First buy</th>
        <th class="num">Return</th><th class="num">vs Nifty</th></tr></thead>
        <tbody>${body}</tbody></table>
    </div>`;
  }).join("") || '<p class="muted">No calls in the selected period.</p>';
  };
  df.wire(el, draw);
  draw();
}

/* ---------- Recommendations ---------- */
// Sort the ~26 granular action strings into a few sentiment categories so the
// filter dropdown can present them under tidy optgroup headings.
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
  // Hybrid calls (e.g. "Hold/Accumulate", "Hold/Add") match >1 sentiment —
  // group them all together under Mixed / Other rather than picking one.
  return hits.length === 1 ? hits[0] : "other";
}

// Collapse near-duplicate variants to a canonical action for the filter, so
// "Buy on dips" / "Buy (long term)" / "Buy / switch into" all read as "Buy".
// Table rows still show the original wording; only the filter is normalized.
function canonicalAction(action) {
  let a = String(action || "").trim();
  if (!a) return a;
  a = a.replace(/\s*\/\s*switch\s+(?:out|into)\b/i, ""); // "Sell / switch out" → "Sell"
  a = a.replace(/\s+on\s+dips?\b/i, ""); // "Buy on dips" → "Buy"
  // Drop a trailing parenthetical qualifier, but keep ones that carry their own
  // sentiment (e.g. "Hold (exit on rally)") so the category doesn't shift.
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
    // First entry selects the whole super-group; the rest are individual actions.
    const all = `<option value="cat:${c.key}">All ${esc(c.label)}</option>`;
    return `<optgroup label="${esc(c.label)}">${all}${opts
      .map((a) => `<option>${esc(a)}</option>`)
      .join("")}</optgroup>`;
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
      <span class="muted" id="recCount"></span>
    </div>
    <div class="toolbar">${df.html()}</div>
    <table><thead><tr>
      <th>Stock</th><th>Action</th><th>Price/level</th><th>Summary</th>
      <th>Last</th><th class="num">Times</th>
    </tr></thead><tbody id="recBody"></tbody></table>`;

  const draw = () => {
    const q = $("#recSearch").value.toLowerCase();
    const act = $("#recAction").value;
    const matchAct = act.startsWith("cat:")
      ? (r) => recCategory(canonicalAction(r.action)) === act.slice(4)
      : (r) => canonicalAction(r.action) === act;
    const filtered = recs.filter(
      (r) =>
        (!act || matchAct(r)) &&
        df.match(r.last) &&
        (!q || (r.stock + " " + r.summary).toLowerCase().includes(q))
    );
    $("#recCount").textContent = `${filtered.length} of ${recs.length}`;
    $("#recBody").innerHTML = filtered.map((r) => `<tr>
      <td><strong>${esc(r.stock)}</strong></td>
      <td>${badge(r.action)}</td>
      <td class="muted">${esc(r.price)}</td>
      <td>${esc(r.summary)}</td>
      <td class="muted">${esc(r.last)}</td>
      <td class="num">${esc(r.times)}</td>
    </tr>`).join("");
  };
  $("#recSearch").addEventListener("input", draw);
  $("#recAction").addEventListener("change", draw);
  df.wire(el, draw);
  draw();
}

/* ---------- Episodes ---------- */
function recItems(list, fields) {
  if (!list || !list.length) return '<p class="muted">None recorded.</p>';
  return `<div class="reclist">${list.map((r) => `
    <div class="recitem">
      <div class="top">
        <span class="stock">${esc(r.stock)}</span>
        ${badge(r.action)}
        ${r.price ? `<span class="price">${esc(r.price)}</span>` : ""}
      </div>
      <div class="note">${esc(r[fields] || "")}</div>
    </div>`).join("")}</div>`;
}

function renderEpisodes(eps) {
  const el = $("#episodes");
  const df = makeDateFilter(eps.map((e) => e.date));
  el.innerHTML = `<div class="toolbar">${df.html()}<span class="muted" id="epCount"></span></div><div id="epList"></div>`;

  const draw = () => {
    const list = eps.filter((e) => df.match(e.date));
    $("#epCount").textContent = `${list.length} of ${eps.length}`;
    $("#epList").innerHTML = list.map((e) => {
      const summaryHtml = e.summary_md ? marked.parse(e.summary_md) : '<p class="muted">No summary.</p>';
      return `<details class="ep">
      <summary>
        <span><span class="date">${esc(e.date)}</span>${esc(e.title)}</span>
        <span class="pills">${e.kutumba.length} KR · ${e.kranti.length} Kranthi</span>
      </summary>
      <div class="ep-body">
        ${e.youtube_url ? `<p><a class="yt" href="${esc(e.youtube_url)}" target="_blank" rel="noopener">▶ Watch on YouTube</a></p>` : ""}
        <h3>Kutumba Rao — calls</h3>${recItems(e.kutumba, "note")}
        <h3>Kranthi — calls</h3>${recItems(e.kranti, "note")}
        <h3>Summary</h3><div class="ep-summary">${summaryHtml}</div>
      </div>
    </details>`;
    }).join("") || '<p class="muted">No episodes in the selected period.</p>';
  };
  df.wire(el, draw);
  draw();
}

/* ---------- Tabs + boot ---------- */
function initTabs() {
  document.querySelectorAll("#tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#tabs button").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      btn.classList.add("active");
      $("#" + btn.dataset.tab).classList.add("active");
    });
  });
}

async function boot() {
  document.querySelectorAll(".tab").forEach((t) => (t.innerHTML = '<div class="loading">Loading…</div>'));
  try {
    const data = await (await fetch("data.json", { cache: "no-cache" })).json();
    $("#generated").textContent = "Updated " + data.generated_at;
    renderScorecard(data.scorecard);
    renderRecs(data.recommendations);
    renderEpisodes(data.episodes);
    initTabs();
  } catch (err) {
    $("#scorecard").innerHTML = `<div class="loading">Failed to load data.json — ${esc(err.message)}</div>`;
  }
}
boot();
