/* Deep-Time — front-end controller. Talks to the stdlib JSON API and drives
   the SVG charts in charts.js. */
(function () {
  "use strict";
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const C = window.DTCharts;

  const state = { config: null, params: {}, lastRun: null, lastMC: null, tab: "history" };

  // event kind -> colour + label (categorical annotations, always labelled)
  const EVENT_META = {
    breakthrough:       { color: "#3987e5", label: "Breakthrough" },
    field_breakthrough: { color: "#9085e9", label: "Field paradigm" },
    colonization:       { color: "#008300", label: "Colonization" },
    merger:             { color: "#199e70", label: "Merger" },
    fragmentation:      { color: "#fab219", label: "Fragmentation" },
    war_start:          { color: "#d03b3b", label: "War begins" },
    war_end:            { color: "#c98500", label: "War ends" },
    collapse:           { color: "#d95926", label: "Collapse" },
    extinction:         { color: "#e66767", label: "Extinction" },
    aeonic_transition:  { color: "#d55181", label: "Aeonic transition" },
  };

  // history metric charts (single-series each)
  const HIST_METRICS = [
    { key: "K_max", title: "Kardashev index K", color: "#3987e5", note: "max over civilizations (§13)" },
    { key: "Phi_max", title: "Field mastery Φ", color: "#9085e9", note: "max over civilizations (§16)" },
    { key: "P_total", title: "Population", color: "#008300", note: "total active minds (§7)", ylog: true },
    { key: "A_mean", title: "Scientific knowledge A", color: "#c98500", note: "mean over civilizations (§10)" },
    { key: "n_civ", title: "Living civilizations", color: "#d55181", note: "count (§41)" },
    { key: "n_colonized", title: "Colonized sites", color: "#199e70", note: "occupied nodes (§20)" },
  ];
  const MC_METRICS = [
    { key: "K_max", title: "Kardashev index K", color: "#3987e5" },
    { key: "Phi_max", title: "Field mastery Φ", color: "#9085e9" },
    { key: "P_total", title: "Population", color: "#008300", ylog: true },
    { key: "n_civ", title: "Living civilizations", color: "#d55181" },
    { key: "n_colonized", title: "Colonized sites", color: "#199e70" },
    { key: "A_mean", title: "Knowledge A", color: "#c98500" },
  ];

  // ---------- init ----------
  async function init() {
    try {
      state.config = await (await fetch("api/config")).json();
    } catch (e) {
      $("#status").textContent = "Cannot reach server."; return;
    }
    state.params = Object.assign({}, state.config.defaults);
    buildParamControls();
    buildGlossary();
    buildTiers();
    buildEraRef();
    buildCosmoRef();
    buildQtr();
    loadModelDoc();
    wireButtons();
    window.addEventListener("resize", debounce(() => {
      if (state.tab === "history" && state.lastRun) renderHistory();
      if (state.tab === "montecarlo" && state.lastMC) renderMC();
    }, 180));
  }

  function wireButtons() {
    $("#btn-run").addEventListener("click", runHistory);
    $("#btn-mc").addEventListener("click", runMonteCarlo);
    $("#btn-reset").addEventListener("click", () => {
      state.params = Object.assign({}, state.config.defaults);
      buildParamControls();
    });
    $$(".tab").forEach(t => t.addEventListener("click", () => switchTab(t.dataset.tab)));
  }

  function switchTab(name) {
    state.tab = name;
    $$(".tab").forEach(t => t.classList.toggle("tab-active", t.dataset.tab === name));
    $$(".tab-panel").forEach(p => p.classList.add("hidden"));
    $("#panel-" + name).classList.remove("hidden");
    if (name === "history" && state.lastRun) renderHistory();
    if (name === "montecarlo" && state.lastMC) renderMC();
  }

  // ---------- parameter controls ----------
  function buildParamControls() {
    const meta = state.config.meta;
    const groups = {};
    for (const key in meta) {
      const g = meta[key].group;
      (groups[g] = groups[g] || []).push(key);
    }
    const host = $("#param-groups"); host.innerHTML = "";
    let first = true;
    for (const g in groups) {
      const det = document.createElement("details");
      det.className = "pgroup"; if (first) { det.open = true; first = false; }
      const sum = document.createElement("summary"); sum.textContent = g; det.appendChild(sum);
      const body = document.createElement("div"); body.className = "pgroup-body";
      groups[g].forEach(key => body.appendChild(paramControl(key)));
      det.appendChild(body); host.appendChild(det);
    }
  }

  function paramControl(key) {
    const m = state.config.meta[key];
    const wrap = document.createElement("div"); wrap.className = "param";
    const top = document.createElement("div"); top.className = "param-top";
    const label = document.createElement("span"); label.className = "param-label";
    const tag = document.createElement("span"); tag.className = "tag tag-" + m.tag;
    tag.textContent = m.tag; tag.title = state.config.tags[m.tag];
    label.appendChild(tag); label.appendChild(document.createTextNode(m.label));
    const val = document.createElement("span"); val.className = "param-val";
    top.appendChild(label); top.appendChild(val);

    const range = document.createElement("input");
    range.type = "range"; range.min = m.min; range.max = m.max;
    range.step = m.step != null ? m.step : (m.int ? 1 : (m.max - m.min) / 100);
    range.value = state.params[key];
    const show = () => { val.textContent = m.int ? String(parseInt(range.value)) : (+range.value).toString(); };
    show();
    range.addEventListener("input", () => {
      state.params[key] = m.int ? parseInt(range.value) : parseFloat(range.value);
      show();
    });
    wrap.appendChild(top); wrap.appendChild(range);
    return wrap;
  }

  // ---------- single history ----------
  async function runHistory() {
    setBusy(true, "Integrating trajectory…");
    $("#btn-run").disabled = true;
    try {
      const body = Object.assign({}, state.params, { record_every: 4 });
      const res = await fetch("api/simulate", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      state.lastRun = data;
      $("#history-empty").classList.add("hidden");
      $("#history-body").classList.remove("hidden");
      switchTab("history");
      renderHistory();
      setBusy(false, "Done.");
    } catch (e) {
      setBusy(false, "Error: " + e.message);
    } finally {
      $("#btn-run").disabled = false;
    }
  }

  function renderHistory() {
    const d = state.lastRun; if (!d) return;
    const s = d.series;
    const rp = d.params || state.params;   // the run's own parameters, not live sliders
    // stat tiles
    const lastCivs = d.civ_table || [];
    const bestPhi = lastCivs.reduce((a, c) => c.Phi > a ? c.Phi : a, 0);
    const bestTier = lastCivs.reduce((a, c) => c.Phi >= (a.Phi || -1) ? c : a, {});
    const lead = lastCivs.slice().sort((a, b) => (b.era_level || 0) - (a.era_level || 0))[0] || {};
    const kmax = s.K_max.length ? Math.max(...s.K_max) : 0;
    const tiles = [
      { k: "Civilizational era", v: lead.era_level ? (lead.era_level + ". " + lead.era) : "—", sub: lead.era_it || "leading civilization" },
      { k: "Peak Kardashev", v: C.fmt(kmax), sub: "energy tier" },
      { k: "Field mastery", v: C.fmt(bestPhi), sub: bestTier.tier || "—" },
      { k: "Civilizations (end)", v: String(lastCivs.length), sub: "of " + Math.round(rp.n_civ) + " seeded" },
      { k: "Sites colonized", v: String(s.n_colonized.length ? s.n_colonized[s.n_colonized.length - 1] : 0), sub: Math.round(rp.n_nodes) + " total" },
      { k: "Historical events", v: String(d.n_events || (d.events ? d.events.length : 0)), sub: "recorded" },
    ];
    $("#stat-row").innerHTML = tiles.map(t =>
      `<div class="stat"><div class="k">${t.k}</div><div class="v">${t.v}</div><div class="sub">${t.sub}</div></div>`).join("");

    // deep-time ladder (Image 1) + cosmological context
    const lad = d.ladder || {};
    C.ladderChart($("#ladder"), {
      frontier: lad.frontier || [], per_civ: lad.per_civ || {},
      year0: lad.year0, year_end: lad.year_end, narrativeYear: lad.narrative_year,
      eras: (state.config && state.config.civ_eras) || [],
      milestones: [
        { year: rp.self_ref_year || 1e13, label: "universal self-reference" },
        { year: rp.trans_aware_year || 1e14, label: "trans-universal awareness" },
      ],
    });
    C.cosmoStrip($("#cosmo-strip"), {
      eras: (state.config && state.config.cosmo_eras) || [],
      universeAgeNow: state.config && state.config.universe_age_now,
      narrativeYear: rp.narrative_year,
    });
    const cos = d.cosmos || {};
    $("#cosmo-note").innerHTML =
      `Horizon: <b>${C.fmtYears(cos.cosmic_year || 0)} yr ahead</b> &middot; ` +
      `cosmological era: <b>${cos.cosmo_era || "—"}</b> &middot; ` +
      `this universe's fate: <b>${cos.fate_name || "—"}</b> &middot; ` +
      `conformal crossovers: <b>${cos.max_aeon || 0}</b>`;

    // charts — append every card FIRST so the grid has settled each card's
    // final width, then render (avoids the first card being measured while it
    // is momentarily the sole, full-width grid child).
    const grid = $("#history-charts"); grid.innerHTML = "";
    const cards = HIST_METRICS.map(mc => { const c = chartCard(mc.title, mc.note); grid.appendChild(c.card); return c; });
    HIST_METRICS.forEach((mc, i) => {
      const pts = s.t.map((t, k) => [t, s[mc.key][k]]);
      C.lineChart(cards[i].body, { series: [{ name: mc.title, color: mc.color, points: pts }], ylog: mc.ylog, xlabel: "time" });
    });

    // network
    const net = d.graph;
    C.networkGraph($("#network"), { nodes: net.nodes, edges: net.edges, civName: i => "Civ " + i });
    $("#network-legend").innerHTML = legendHTML(
      (net.nodes ? uniqueCivs(net.nodes) : []).map(i => ({ swatch: C.civColor(i), label: "Civ " + i }))
        .concat([{ swatch: "#3a3a37", label: "uninhabited" }]));

    // civ table
    renderCivTable(lastCivs);

    // timeline
    const usedKinds = {};
    (d.events || []).forEach(e => { if (EVENT_META[e.kind]) usedKinds[e.kind] = EVENT_META[e.kind]; });
    // keep a stable order
    const orderedKinds = {};
    Object.keys(EVENT_META).forEach(k => { if (usedKinds[k]) orderedKinds[k] = usedKinds[k]; });
    C.timeline($("#timeline"), { events: d.events || [], tmax: rp.t_max, kinds: orderedKinds });
    $("#timeline-legend").innerHTML = legendHTML(Object.keys(orderedKinds).map(k =>
      ({ swatch: orderedKinds[k].color, label: orderedKinds[k].label })));
  }

  function renderCivTable(civs) {
    if (!civs.length) { $("#civ-table").innerHTML = "<p class='muted'>No civilizations survived to the horizon.</p>"; return; }
    const rows = civs.slice().sort((a, b) => (b.era_level || 0) - (a.era_level || 0) || b.nodes - a.nodes).map(c =>
      `<tr>
        <td><span class="civ-dot" style="background:${C.civColor(c.civ)}"></span>Civ ${c.civ}</td>
        <td style="text-align:left">${c.era_level ? c.era_level + ". " + c.era : "—"}</td>
        <td style="text-align:left">${c.vessel || "—"} <span class="muted">${c.oct || ""}</span></td>
        <td>${c.nodes}</td><td>${C.fmt(c.K)}</td><td>${C.fmt(c.Phi)}</td><td>${c.aeon || 0}</td>
      </tr>`).join("");
    $("#civ-table").innerHTML =
      `<table><thead><tr><th>Civilization</th><th style="text-align:left">Era</th>
        <th style="text-align:left">Vessel · OCT</th><th>Sites</th><th>K</th><th>Φ</th><th>Aeon</th></tr></thead>
       <tbody>${rows}</tbody></table>`;
  }

  // ---------- monte carlo ----------
  async function runMonteCarlo() {
    switchTab("montecarlo");
    $("#mc-empty").classList.add("hidden");
    $("#mc-body").classList.add("hidden");
    $("#mc-progress-wrap").classList.remove("hidden");
    setProgress(0, state.params && $("#mc-runs") ? parseInt($("#mc-runs").value) : 40);
    $("#btn-mc").disabled = true;
    setBusy(true, "Sampling ensemble…");
    try {
      const nRuns = Math.max(2, Math.min(200, parseInt($("#mc-runs").value) || 40));
      const body = Object.assign({}, state.params, { n_runs: nRuns, record_every: 6 });
      const start = await (await fetch("api/montecarlo", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
      })).json();
      if (start.error) throw new Error(start.error);
      const jobId = start.job_id;
      const result = await pollJob(jobId);
      state.lastMC = result;
      $("#mc-progress-wrap").classList.add("hidden");
      $("#mc-body").classList.remove("hidden");
      renderMC();
      setBusy(false, "Ensemble complete.");
    } catch (e) {
      $("#mc-progress-wrap").classList.add("hidden");
      setBusy(false, "Error: " + e.message);
    } finally {
      $("#btn-mc").disabled = false;
    }
  }

  function pollJob(jobId) {
    return new Promise((resolve, reject) => {
      const tick = async () => {
        try {
          const j = await (await fetch("api/montecarlo/" + jobId)).json();
          if (j.status === "error") return reject(new Error(j.error || "job failed"));
          setProgress(j.done, j.total);
          if (j.status === "done") return resolve(j.result);
          setTimeout(tick, 400);
        } catch (e) { reject(e); }
      };
      tick();
    });
  }

  function setProgress(done, total) {
    const pct = total ? Math.round(100 * done / total) : 0;
    $("#mc-progress-bar").style.width = pct + "%";
    $("#mc-progress-text").textContent = `${done} / ${total} histories`;
  }

  function renderMC() {
    const d = state.lastMC; if (!d) return;
    $("#mc-n").textContent = d.n_runs;
    // probability bars
    const probHost = $("#mc-prob"); probHost.innerHTML = "";
    Object.keys(d.probabilities).forEach(q => {
      const p = d.probabilities[q], err = d.stderr[q] || 0;
      const row = document.createElement("div"); row.className = "prob-row";
      const errLeft = Math.max(0, (p - err)) * 100, errW = Math.min(100, (2 * err)) * 100 / 100 * 100;
      row.innerHTML =
        `<div class="prob-label">${q}</div>
         <div class="prob-track">
           <div class="prob-fill" style="width:${(p * 100).toFixed(1)}%"></div>
           <div class="prob-err" style="left:${errLeft.toFixed(1)}%;width:${(2 * err * 100).toFixed(1)}%"></div>
         </div>
         <div class="prob-val">${(p * 100).toFixed(0)}%</div>`;
      probHost.appendChild(row);
    });
    // fan charts — append all cards first, then render (see renderHistory).
    const grid = $("#mc-charts"); grid.innerHTML = "";
    const cards = MC_METRICS.map(mc => { const c = chartCard(mc.title, "mean & 10–90% band"); grid.appendChild(c.card); return c; });
    MC_METRICS.forEach((mc, i) => {
      const mean = d.time_grid.map((t, k) => [t, d.mean_series[mc.key][k]]);
      const band = d.time_grid.map((t, k) => [t, d.p10_series[mc.key][k], d.p90_series[mc.key][k]]);
      C.lineChart(cards[i].body, {
        series: [{ name: mc.title, color: mc.color, points: mean }],
        band: { points: band, color: mc.color }, ylog: mc.ylog, xlabel: "time"
      });
    });
  }

  // ---------- model tab ----------
  function buildGlossary() {
    const vl = state.config.var_labels;
    $("#glossary").innerHTML = Object.keys(vl).map(sym =>
      `<div class="gl-item"><span class="gl-sym">${prettySym(sym)}</span><span class="gl-desc">${vl[sym]}</span></div>`).join("");
  }
  function buildTiers() {
    const tiers = state.config.field_tiers;
    $("#tiers").innerHTML = tiers.map((t, i) => {
      const rng = i < tiers.length - 1 ? `${t.threshold} – ${tiers[i + 1].threshold}` : `≥ ${t.threshold}`;
      return `<div class="tier"><span class="rng">Φ ${rng}</span><span>${t.label}</span></div>`;
    }).join("");
  }
  function buildEraRef() {
    const eras = state.config.civ_eras || [];
    $("#era-ref").innerHTML = eras.map(e =>
      `<div class="tier era-ref-row">
         <span class="rng">${e.level}. ${e.name}</span>
         <span><b>${e.name_it}</b> &nbsp;<span class="muted">K&ge;${e.K_min} &middot; &Phi;&ge;${e.Phi_min}</span><br>
           <span class="gl-desc">${e.desc}</span></span>
       </div>`).join("");
  }
  function buildCosmoRef() {
    const eras = state.config.cosmo_eras || [];
    const fmtE = v => v == null ? "∞" : (v === 0 ? "0" : "10^" + Math.round(Math.log10(v)));
    $("#cosmo-ref").innerHTML = eras.map(e =>
      `<div class="tier"><span class="rng">${fmtE(e.start)}–${fmtE(e.end)} yr</span>
        <span>${e.name}<br><span class="gl-desc">${e.note}</span></span></div>`).join("");
  }
  function buildQtr() {
    const cfg = state.config;
    $("#qtr-layers").innerHTML = (cfg.qtr_layers || []).map(l =>
      `<div class="tier"><span class="rng">${l.key}</span>
        <span>${l.name}<br><span class="gl-desc">${l.answers}</span></span></div>`).join("");
    $("#qtr-postulates").innerHTML = (cfg.qtr_postulates || []).map(p =>
      `<div class="tier"><span class="rng">${p.key} ${p.name}</span>
        <span class="gl-desc">${p.text}</span></div>`).join("");
    $("#qtr-lambda").innerHTML = (cfg.lambda_l || []).map(v =>
      `<span class="chip"><b>${v.sym}</b> ${v.meaning}</span>`).join("");
    $("#oct-ref").innerHTML = (cfg.oct_ladder || []).map(o =>
      `<div class="tier"><span class="rng">${o.oct} · ${o.class}</span>
        <span><b>${o.name}</b> <span class="muted">Φ≥${o.Phi_min}</span><br>
          <span class="gl-desc">${o.reach}</span></span></div>`).join("");
    $("#nav-ref").innerHTML = (cfg.nav_doors || []).map(d =>
      `<div class="tier"><span class="rng">${d.axis}${d.phi !== "—" ? " · " + d.phi : ""}</span>
        <span><b>${d.door}</b><br><span class="gl-desc">${d.text}</span></span></div>`).join("");
    const fmtPct = w => Math.round(w * 100) + "%";
    $("#fates-ref").innerHTML = (cfg.cosmic_fates || []).map(f =>
      `<div class="tier"><span class="rng">${fmtPct(f.weight)}</span>
        <span><b>${f.name}</b><br><span class="gl-desc">${f.note}</span></span></div>`).join("");
  }
  async function loadModelDoc() {
    try {
      const d = await (await fetch("api/model")).json();
      $("#model-doc").innerHTML = miniMarkdown(d.markdown || "");
    } catch (e) { $("#model-doc").textContent = "Specification unavailable."; }
  }

  // ---------- helpers ----------
  function chartCard(title, note) {
    const card = document.createElement("div"); card.className = "chart-card";
    const h = document.createElement("h4"); h.textContent = title; card.appendChild(h);
    if (note) { const n = document.createElement("p"); n.className = "chart-note"; n.textContent = note; card.appendChild(n); }
    const body = document.createElement("div"); card.appendChild(body);
    return { card, body };
  }
  function legendHTML(items) {
    return items.map(it =>
      `<span class="legend-item"><span class="legend-swatch" style="background:${it.swatch}"></span>${it.label}</span>`).join("");
  }
  function uniqueCivs(nodes) {
    const s = new Set(); nodes.forEach(n => { if (n.civ >= 0) s.add(n.civ); });
    return Array.from(s).sort((a, b) => a - b);
  }
  function prettySym(sym) {
    return sym.replace("Phi", "Φ").replace("Lambda", "Λ");
  }
  function setBusy(busy, msg) { $("#status").textContent = msg || ""; }
  function debounce(fn, ms) { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; }

  // Very small markdown subset for the spec (headings, code, lists, tables, para).
  function miniMarkdown(md) {
    const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const lines = md.split("\n");
    let html = "", inCode = false, inTable = false;
    for (let raw of lines) {
      if (raw.startsWith("```")) {
        if (!inCode) { html += "<pre><code>"; inCode = true; }
        else { html += "</code></pre>"; inCode = false; }
        continue;
      }
      if (inCode) { html += esc(raw) + "\n"; continue; }
      const isTable = /^\s*\|.*\|\s*$/.test(raw);
      if (isTable) {
        if (/^\s*\|[\s:|-]+\|\s*$/.test(raw)) continue; // separator row
        const cells = raw.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => esc(c.trim()));
        if (!inTable) { html += "<table>"; inTable = true; }
        html += "<tr>" + cells.map(c => `<td>${c}</td>`).join("") + "</tr>";
        continue;
      } else if (inTable) { html += "</table>"; inTable = false; }

      if (/^#\s/.test(raw)) html += "<h1>" + esc(raw.slice(2)) + "</h1>";
      else if (/^##\s/.test(raw)) html += "<h2>" + esc(raw.slice(3)) + "</h2>";
      else if (/^###\s/.test(raw)) html += "<h3>" + esc(raw.slice(4)) + "</h3>";
      else if (/^\s*[-*]\s/.test(raw)) html += "<div>• " + esc(raw.replace(/^\s*[-*]\s/, "")) + "</div>";
      else if (raw.trim() === "" || raw.trim() === "---") html += "";
      else if (/^\\\[|\\\]$|^\\\(/.test(raw.trim())) html += `<div class="muted">${esc(raw)}</div>`;
      else html += "<p>" + esc(raw) + "</p>";
    }
    if (inTable) html += "</table>";
    return html;
  }

  init();
})();
