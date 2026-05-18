/* Alternative Data Platform — dashboard logic.
   Vanilla ES module, no dependencies, same-origin fetches. Every section
   fails locally (an inline message) so a single error never blanks the page. */

const KNOWN_FACTOR = "posoco_industrial_yoy";
/* Seed list so the dropdowns are useful before any /features call returns.
   fillFactors() still merges in whatever feature_names actually exist. */
const KNOWN_FACTORS = [
  "posoco_industrial_yoy",
  "gst_eway_composite",
  "railway_freight_composite",
];

/* ---------- tiny helpers ------------------------------------------ */
const $ = (sel) => document.querySelector(sel);

async function api(path, params) {
  const url = new URL(path, location.origin);
  if (params)
    for (const [k, v] of Object.entries(params))
      if (v !== undefined && v !== null && v !== "")
        url.searchParams.set(k, v);
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );

const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const pct = (x, d = 2) =>
  isNum(x) ? `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%` : "—";
const fixed = (x, d = 2) => (isNum(x) ? x.toFixed(d) : "—");
const sign = (x) => (!isNum(x) ? "" : x > 0 ? "pos" : x < 0 ? "neg" : "");
const todayISO = () => new Date().toISOString().slice(0, 10);

function setBusy(el, text) {
  el.innerHTML = `<div class="msg skeleton">${esc(text)}</div>`;
}
function setError(el, what, e) {
  el.innerHTML =
    `<div class="msg err"><strong>${esc(what)}.</strong> ${esc(
      e.message || e
    )}<br />Is the platform stack running and has data been ingested?</div>`;
}

/* ---------- status line ------------------------------------------- */
async function loadStatus() {
  const box = $("#status");
  const dot = box.querySelector(".dot");
  const txt = box.querySelector(".status-text");
  try {
    const [h, s] = await Promise.all([api("/health"), api("/sources")]);
    const ok = h.status === "ok";
    dot.dataset.state = ok ? "ok" : "degraded";
    const srcs = (s.sources || []).join(", ") || "none registered";
    txt.innerHTML =
      `Platform <code>v${esc(h.version)}</code> · database ` +
      `${h.db ? "connected" : "unreachable"} · sources: ` +
      `<code>${esc(srcs)}</code>`;
  } catch (e) {
    dot.dataset.state = "down";
    txt.innerHTML =
      `Cannot reach the API. Start it with ` +
      `<code>uvicorn adp.api.main:app --host 127.0.0.1 --port 8000</code>.`;
  }
}

/* The most recent feature_date that actually has data. Used so the date
   inputs default to real data instead of "today" (which, being past the
   end of the dataset, would always show the same last-known snapshot). */
let DATA_MAX_DATE = null;

/* ---------- factor selects ---------------------------------------- */
async function fillFactors() {
  let opts = [...KNOWN_FACTORS];
  try {
    const f = await api("/features", { as_of: todayISO(), limit: 5000 });
    const rows = f.rows || [];
    const names = [...new Set(rows.map((r) => r.feature_name))];
    if (names.length) opts = [...new Set([...names, ...KNOWN_FACTORS])];
    const dates = rows.map((r) => r.feature_date).filter(Boolean).sort();
    if (dates.length) {
      DATA_MAX_DATE = dates[dates.length - 1];
      $("#sig-asof").value = DATA_MAX_DATE;
      $("#feat-asof").value = DATA_MAX_DATE;
    }
  } catch {
    /* keep the known default */
  }
  for (const id of ["#sig-factor", "#bt-factor"]) {
    const sel = $(id);
    sel.innerHTML = opts
      .map((o) => `<option value="${esc(o)}">${esc(o)}</option>`)
      .join("");
    sel.value = KNOWN_FACTOR;
  }
}

/* ---------- universe (also used to enrich signals) ---------------- */
let UNIVERSE = [];
async function loadUniverse() {
  const u = await api("/universe");
  UNIVERSE = u.rows || [];
  return UNIVERSE;
}
const byTicker = () =>
  Object.fromEntries(UNIVERSE.map((r) => [r.ticker, r]));

/* ---------- signals ----------------------------------------------- */
async function loadSignals() {
  const out = $("#signals-out");
  const factor = $("#sig-factor").value || KNOWN_FACTOR;
  const asof = $("#sig-asof").value;
  setBusy(out, "Reading the signal point-in-time…");
  try {
    if (!UNIVERSE.length) await loadUniverse().catch(() => {});
    const d = await api("/signals", { factor, as_of: asof });
    const rows = d.signals || [];
    if (!rows.length) {
      out.innerHTML =
        `<div class="msg">No signal for <strong>${esc(
          factor
        )}</strong> as of <strong>${esc(
          d.as_of
        )}</strong>. Nothing had been published yet, or features have not been built for this range.</div>`;
      return;
    }
    const u = byTicker();
    const latestData = rows
      .map((r) => r.feature_date)
      .filter(Boolean)
      .sort()
      .pop();
    const stale = latestData && d.as_of > latestData;
    const peak = Math.max(...rows.map((r) => Math.abs(r.value) || 0)) || 1;
    const body = rows
      .map((r, i) => {
        const m = u[r.ticker] || {};
        const w = Math.min(50, (Math.abs(r.value) / peak) * 50);
        const s = sign(r.value);
        const bar =
          r.value >= 0
            ? `<i class="pos" style="left:50%;width:${w}%"></i>`
            : `<i class="neg" style="left:${50 - w}%;width:${w}%"></i>`;
        return `<tr>
          <td class="dim num">${i + 1}</td>
          <td class="tick">${esc(r.ticker)}</td>
          <td>${esc(m.name || "—")}</td>
          <td class="dim">${esc(m.sector || "—")}</td>
          <td class="dim">${esc(m.state || "—")}</td>
          <td class="num ${s}">${pct(r.value)}</td>
          <td class="bar-cell"><div class="bar"><span class="mid"></span>${bar}</div></td>
        </tr>`;
      })
      .join("");
    out.innerHTML = `
      <div class="tbl-scroll"><table>
        <caption>${rows.length} stocks ranked by <strong>${esc(
      factor
    )}</strong>, point-in-time as of <strong>${esc(
      d.as_of
    )}</strong>. Top of the list = strongest physical activity (strategy goes long); bottom = weakest (strategy goes short).
        <br />Newest data available is <strong>${esc(
          latestData || "—"
        )}</strong>.${
      stale
        ? ` Your “as of” date is past that, so this is the last known snapshot — pick a date on or before ${esc(
            latestData
          )} to move through history.`
        : ""
    } These alternative-data factors are <em>basket-level</em> (state or industry), so every company in the same basket shares the value — the honest granularity ceiling, by design.</caption>
        <thead><tr>
          <th>#</th><th>Ticker</th><th>Company</th><th>Sector</th>
          <th>State</th><th class="num">Signal</th><th class="bar-cell">vs&nbsp;peers</th>
        </tr></thead>
        <tbody>${body}</tbody>
      </table></div>`;
  } catch (e) {
    setError(out, "Could not load signals", e);
  }
}

/* ---------- backtest ---------------------------------------------- */
async function runBacktest() {
  const out = $("#backtest-out");
  const btn = $("#bt-run");
  const factor = $("#bt-factor").value || KNOWN_FACTOR;
  const start = $("#bt-start").value;
  const end = $("#bt-end").value;
  btn.disabled = true;
  setBusy(out, "Replaying history month by month and fetching prices…");
  try {
    const d = await api("/backtest", { factor, start, end });
    if (d.error) {
      out.innerHTML = `<div class="msg err"><strong>Backtest could not run.</strong> ${esc(
        d.error
      )}<br />This needs a populated <code>features</code> table and price connectivity (it fetches market data live).</div>`;
      return;
    }
    const m = d.metrics;
    const cards = [
      ["Net CAGR", pct(m.net_cagr), sign(m.net_cagr), "after trading costs, annualised"],
      ["Sharpe", fixed(m.sharpe), sign(m.sharpe), "return per unit of risk"],
      ["Mean IC", fixed(m.mean_ic, 4), sign(m.mean_ic), `t-stat ${fixed(m.ic_tstat)} · ${m.ic_periods} periods`],
      ["Cumulative net", pct(m.cum_net), sign(m.cum_net), `${m.n_rebalances} monthly rebalances`],
    ]
      .map(
        ([l, v, s, sub]) => `<div class="metric">
          <div class="label">${esc(l)}</div>
          <div class="value ${s}">${esc(v)}</div>
          <div class="sub">${esc(sub)}</div>
        </div>`
      )
      .join("");

    out.innerHTML = `
      <div class="metrics">${cards}</div>
      <div class="chart">
        <h3>Equity curve</h3>
        <p class="cap">Cumulative return of the long/short strategy across the
        backtest. Net is after costs; gross is before.</p>
        ${equitySvg(d.equity_curve)}
        <div class="legend">
          <span class="net"><i></i>Net (after costs)</span>
          <span class="gross"><i></i>Gross</span>
        </div>
      </div>
      <div class="chart">
        <h3>Information Coefficient by period</h3>
        <p class="cap">How well the signal's ranking predicted what happened
        next, each rebalance. Consistently positive is the goal.</p>
        ${icSvg(d.ic_series)}
      </div>`;
  } catch (e) {
    setError(out, "Backtest request failed", e);
  } finally {
    btn.disabled = false;
  }
}

/* ---------- hand-rolled SVG charts (no library) ------------------- */
function equitySvg(curve) {
  if (!curve || curve.length < 2)
    return `<div class="msg">Not enough rebalance periods to draw a curve.</div>`;
  const W = 920, H = 280, P = 38;
  const xs = curve.map((_, i) => i);
  const ys = curve.flatMap((p) => [p.net_cum, p.gross_cum]);
  const yMin = Math.min(0, ...ys), yMax = Math.max(0, ...ys);
  const X = (i) => P + (i / (xs.length - 1)) * (W - 2 * P);
  const Y = (v) => H - P - ((v - yMin) / (yMax - yMin || 1)) * (H - 2 * P);
  const path = (key) =>
    curve.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(p[key]).toFixed(1)}`).join(" ");
  const y0 = Y(0);
  const last = curve[curve.length - 1];
  const ticks = [0, Math.floor(curve.length / 2), curve.length - 1];
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Equity curve">
    <line class="axis" x1="${P}" y1="${H - P}" x2="${W - P}" y2="${H - P}"/>
    <line class="zero" x1="${P}" y1="${y0.toFixed(1)}" x2="${W - P}" y2="${y0.toFixed(1)}"/>
    <text class="tick-lbl" x="${P}" y="${(y0 - 6).toFixed(1)}">0%</text>
    <path class="gross" d="${path("gross_cum")}"/>
    <path class="net" d="${path("net_cum")}"/>
    ${ticks
      .map(
        (i) =>
          `<text class="tick-lbl" x="${X(i).toFixed(1)}" y="${H - P + 16}" text-anchor="middle">${esc(
            curve[i].date
          )}</text>`
      )
      .join("")}
    <text class="tick-lbl" x="${W - P}" y="${(Y(last.net_cum) - 8).toFixed(1)}" text-anchor="end">${esc(
    pct(last.net_cum)
  )}</text>
  </svg>`;
}

function icSvg(series) {
  if (!series || !series.length)
    return `<div class="msg">No per-period IC was produced for this run.</div>`;
  const W = 920, H = 200, P = 34;
  const n = series.length;
  const mag = Math.max(...series.map((d) => Math.abs(d.ic)), 0.01);
  const bw = ((W - 2 * P) / n) * 0.66;
  const X = (i) => P + (i + 0.5) * ((W - 2 * P) / n);
  const Y = (v) => H / 2 - (v / mag) * (H / 2 - P);
  const bars = series
    .map((d) => {
      const y = Y(d.ic), y0 = H / 2;
      const top = Math.min(y, y0), h = Math.abs(y - y0);
      return `<rect class="${d.ic >= 0 ? "barpos" : "barneg"}" x="${(
        X(series.indexOf(d)) - bw / 2
      ).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(
        h,
        0.5
      ).toFixed(1)}"/>`;
    })
    .join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="IC by period">
    <line class="zero" x1="${P}" y1="${H / 2}" x2="${W - P}" y2="${H / 2}"/>
    ${bars}
    <text class="tick-lbl" x="${P}" y="${H / 2 - 6}">+IC</text>
    <text class="tick-lbl" x="${P}" y="${H / 2 + 14}">−IC</text>
  </svg>`;
}

/* ---------- universe table ---------------------------------------- */
function renderUniverse() {
  const out = $("#universe-out");
  const q = ($("#uni-q").value || "").trim().toLowerCase();
  const rows = UNIVERSE.filter((r) =>
    !q
      ? true
      : [r.ticker, r.name, r.sector, r.state]
          .map((x) => String(x || "").toLowerCase())
          .some((x) => x.includes(q))
  );
  if (!rows.length) {
    out.innerHTML = `<div class="msg">No companies match “${esc(q)}”.</div>`;
    return;
  }
  const body = rows
    .map(
      (r) => `<tr>
        <td class="tick">${esc(r.ticker)}</td>
        <td>${esc(r.name || "—")}</td>
        <td class="dim">${esc(r.sector || "—")}</td>
        <td class="dim">${esc(r.state || "—")}</td>
      </tr>`
    )
    .join("");
  out.innerHTML = `<div class="tbl-scroll"><table>
      <caption>${rows.length} of ${UNIVERSE.length} companies.</caption>
      <thead><tr><th>Ticker</th><th>Company</th><th>Sector</th><th>State</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
}

async function loadUniverseSection() {
  const out = $("#universe-out");
  setBusy(out, "Loading the universe…");
  try {
    await loadUniverse();
    if (!UNIVERSE.length) {
      out.innerHTML = `<div class="msg">The universe is empty — has the database been seeded (<code>python tasks.py init</code>)?</div>`;
      return;
    }
    renderUniverse();
  } catch (e) {
    setError(out, "Could not load the universe", e);
  }
}

/* ---------- feature explorer -------------------------------------- */
async function loadFeatures() {
  const out = $("#features-out");
  setBusy(out, "Fetching feature rows point-in-time…");
  try {
    const d = await api("/features", {
      as_of: $("#feat-asof").value,
      feature_name: $("#feat-name").value.trim(),
      ticker: $("#feat-ticker").value.trim(),
      limit: $("#feat-limit").value,
    });
    const rows = d.rows || [];
    if (!rows.length) {
      out.innerHTML = `<div class="msg">No rows known as of <strong>${esc(
        d.as_of
      )}</strong> for those filters.</div>`;
      return;
    }
    const cols = ["ticker", "feature_name", "feature_date", "value", "published_date", "as_of_date", "source"];
    const head = cols
      .map((c) => `<th${c === "value" ? ' class="num"' : ""}>${esc(c.replace(/_/g, " "))}</th>`)
      .join("");
    const body = rows
      .map(
        (r) => `<tr>
        <td class="tick">${esc(r.ticker)}</td>
        <td class="dim">${esc(r.feature_name)}</td>
        <td>${esc(r.feature_date)}</td>
        <td class="num ${sign(r.value)}">${
          isNum(r.value) ? r.value.toFixed(4) : esc(r.value)
        }</td>
        <td>${esc(r.published_date)}</td>
        <td class="dim">${esc(r.as_of_date)}</td>
        <td class="dim">${esc(r.source)}</td>
      </tr>`
      )
      .join("");
    out.innerHTML = `<div class="tbl-scroll"><table>
        <caption>${d.count} row(s), point-in-time as of <strong>${esc(
      d.as_of
    )}</strong>.</caption>
        <thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  } catch (e) {
    setError(out, "Could not load features", e);
  }
}

/* ---------- section-nav scroll spy -------------------------------- */
function scrollSpy() {
  const links = [...document.querySelectorAll(".sectionnav a")];
  const map = new Map(
    links.map((a) => [a.getAttribute("href").slice(1), a])
  );
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries)
        if (e.isIntersecting) {
          links.forEach((l) => l.classList.remove("active"));
          map.get(e.target.id)?.classList.add("active");
        }
    },
    { rootMargin: "-45% 0px -50% 0px" }
  );
  document.querySelectorAll("main section").forEach((s) => io.observe(s));
}

/* ---------- wire up ----------------------------------------------- */
function defaults() {
  const t = todayISO();
  $("#sig-asof").value = t;
  $("#feat-asof").value = t;
  $("#feat-name").value = KNOWN_FACTOR;
  $("#bt-start").value = "2024-08-01";
  $("#bt-end").value = "2025-05-01";
}

function init() {
  defaults();
  scrollSpy();

  $("#signals-controls").addEventListener("submit", (e) => {
    e.preventDefault();
    loadSignals();
  });
  $("#bt-controls").addEventListener("submit", (e) => {
    e.preventDefault();
    runBacktest();
  });
  $("#feat-controls").addEventListener("submit", (e) => {
    e.preventDefault();
    loadFeatures();
  });
  $("#uni-q").addEventListener("input", () => {
    if (UNIVERSE.length) renderUniverse();
  });

  loadStatus();
  fillFactors().then(loadSignals);
  loadUniverseSection();
  loadFeatures();
}

document.addEventListener("DOMContentLoaded", init);
