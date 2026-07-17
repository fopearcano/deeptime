/* Deep-Time — self-contained SVG charts (no external libraries).
   Implements the marks/interaction specs from the dataviz method:
   thin 2px lines, recessive hairline grid/axes, a shared crosshair+tooltip
   on line charts, per-mark hover on network/timeline, selective direct labels. */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";

  const PALETTE = ["#3987e5", "#008300", "#d55181", "#c98500",
                   "#199e70", "#d95926", "#9085e9", "#e66767"];
  const INK = "#ffffff", INK2 = "#c3c2b7", MUTED = "#898781";
  const GRID = "#2c2c2a", BASE = "#383835", SURF = "#1a1a19";

  function civColor(i) {
    if (i < 0) return MUTED;
    return PALETTE[i % PALETTE.length];
  }

  function el(tag, attrs, kids) {
    const n = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (kids) for (const c of [].concat(kids)) if (c != null)
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    return n;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  // shared tooltip -----------------------------------------------------------
  let TT;
  function tooltip() {
    if (!TT) { TT = document.createElement("div"); TT.className = "viz-tooltip"; document.body.appendChild(TT); }
    return TT;
  }
  function showTip(html, x, y) {
    const t = tooltip(); t.innerHTML = html; t.style.opacity = "1";
    const pad = 14, w = t.offsetWidth, h = t.offsetHeight;
    let lx = x + pad, ly = y + pad;
    if (lx + w > window.innerWidth - 8) lx = x - w - pad;
    if (ly + h > window.innerHeight - 8) ly = y - h - pad;
    t.style.left = lx + "px"; t.style.top = ly + "px";
  }
  function hideTip() { if (TT) TT.style.opacity = "0"; }

  function niceNum(range, round) {
    const exp = Math.floor(Math.log10(range || 1));
    const f = (range || 1) / Math.pow(10, exp);
    let nf;
    if (round) nf = f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10;
    else nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
    return nf * Math.pow(10, exp);
  }
  function ticks(min, max, count) {
    const range = niceNum(max - min, false);
    const step = niceNum(range / Math.max(1, count - 1), true);
    const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
    const out = [];
    for (let v = lo; v <= hi + step * 0.5; v += step) out.push(Math.abs(v) < step * 1e-6 ? 0 : v);
    return out;
  }
  function fmt(v) {
    if (!isFinite(v)) return "–";
    const a = Math.abs(v);
    if (a >= 1e4 || (a > 0 && a < 1e-2)) return v.toExponential(1);
    if (a >= 100) return v.toFixed(0);
    if (a >= 10) return v.toFixed(1);
    return v.toFixed(2);
  }

  // LINE CHART ---------------------------------------------------------------
  // opts: {series:[{name,color,points:[[x,y]...],dashed}], band:{points:[[x,lo,hi]],color},
  //        ylog, xlabel, ylabel, unit}
  function lineChart(container, opts) {
    clear(container);
    const W = Math.max(300, container.clientWidth || 340), H = opts.height || 210;
    const m = { t: 12, r: 14, b: 26, l: 42 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const svg = el("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, width: "100%", height: H });

    const series = (opts.series || []).filter(s => s.points && s.points.length);
    let xs = [], ysAll = [];
    series.forEach(s => s.points.forEach(p => { xs.push(p[0]); ysAll.push(p[1]); }));
    if (opts.band && opts.band.points) opts.band.points.forEach(p => { xs.push(p[0]); ysAll.push(p[1]); ysAll.push(p[2]); });
    if (!xs.length) { container.appendChild(svg); return; }

    let xmin = Math.min(...xs), xmax = Math.max(...xs);
    if (xmin === xmax) xmax = xmin + 1;
    const ylog = !!opts.ylog;
    let ymin = opts.ymin != null ? opts.ymin : Math.min(...ysAll);
    let ymax = opts.ymax != null ? opts.ymax : Math.max(...ysAll);
    if (ylog) { ymin = Math.max(ymin, 1e-3); ymax = Math.max(ymax, ymin * 10); }
    else {
      if (ymin > 0) ymin = 0;
      const pad = (ymax - ymin) * 0.08 || 1; ymax += pad;
    }
    if (ymin === ymax) ymax = ymin + 1;

    const X = x => m.l + (x - xmin) / (xmax - xmin) * iw;
    const Yv = ylog ? (Math.log10(ymax) - Math.log10(Math.max(ymin,1e-3))) : (ymax - ymin);
    const Y = y => {
      if (ylog) { const yy = Math.log10(Math.max(y, 1e-3)); return m.t + (Math.log10(ymax) - yy) / Yv * ih; }
      return m.t + (ymax - y) / Yv * ih;
    };

    // gridlines + y ticks
    const yt = ylog ? logTicks(ymin, ymax) : ticks(ymin, ymax, 5);
    yt.forEach(v => {
      if (v < ymin - 1e-9 || v > ymax + 1e-9) return;
      const y = Y(v);
      svg.appendChild(el("line", { x1: m.l, x2: m.l + iw, y1: y, y2: y, stroke: GRID, "stroke-width": 1 }));
      svg.appendChild(el("text", { x: m.l - 6, y: y + 3, "text-anchor": "end", fill: MUTED, "font-size": 10 }, fmt(v)));
    });
    // x ticks
    ticks(xmin, xmax, 6).forEach(v => {
      if (v < xmin - 1e-9 || v > xmax + 1e-9) return;
      const x = X(v);
      svg.appendChild(el("text", { x, y: H - 8, "text-anchor": "middle", fill: MUTED, "font-size": 10 }, fmt(v)));
    });
    // axes baseline
    svg.appendChild(el("line", { x1: m.l, x2: m.l + iw, y1: m.t + ih, y2: m.t + ih, stroke: BASE, "stroke-width": 1 }));
    if (opts.xlabel) svg.appendChild(el("text", { x: m.l + iw / 2, y: H - 0, "text-anchor": "middle", fill: MUTED, "font-size": 10 }, opts.xlabel));

    // uncertainty band
    if (opts.band && opts.band.points && opts.band.points.length) {
      const pts = opts.band.points;
      let d = "M" + pts.map(p => `${X(p[0])},${Y(p[1])}`).join(" L");
      for (let i = pts.length - 1; i >= 0; i--) d += ` L${X(pts[i][0])},${Y(pts[i][2])}`;
      d += " Z";
      svg.appendChild(el("path", { d, fill: opts.band.color || "#3987e5", "fill-opacity": 0.16, stroke: "none" }));
    }

    // series lines
    series.forEach(s => {
      const d = "M" + s.points.map(p => `${X(p[0])},${Y(p[1])}`).join(" L");
      svg.appendChild(el("path", {
        d, fill: "none", stroke: s.color, "stroke-width": 2,
        "stroke-linejoin": "round", "stroke-linecap": "round",
        "stroke-dasharray": s.dashed ? "5 4" : ""
      }));
    });
    // selective direct labels when few series
    if (series.length > 1 && series.length <= 4) {
      series.forEach(s => {
        const last = s.points[s.points.length - 1];
        svg.appendChild(el("text", { x: X(last[0]) + 3, y: Y(last[1]) + 3, fill: s.color, "font-size": 10, "font-weight": 600 }, s.name));
      });
    }

    // hover overlay
    const cross = el("line", { x1: 0, x2: 0, y1: m.t, y2: m.t + ih, stroke: BASE, "stroke-width": 1, opacity: 0 });
    svg.appendChild(cross);
    const dots = series.map(s => { const c = el("circle", { r: 3.5, fill: s.color, stroke: SURF, "stroke-width": 1.5, opacity: 0 }); svg.appendChild(c); return c; });
    const hit = el("rect", { x: m.l, y: m.t, width: iw, height: ih, fill: "transparent" });
    svg.appendChild(hit);
    hit.addEventListener("mousemove", (e) => {
      const r = svg.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width * W;
      const xv = xmin + (px - m.l) / iw * (xmax - xmin);
      let rows = "";
      cross.setAttribute("x1", X(xv)); cross.setAttribute("x2", X(xv)); cross.setAttribute("opacity", 1);
      series.forEach((s, i) => {
        const p = nearest(s.points, xv);
        if (!p) { dots[i].setAttribute("opacity", 0); return; }
        dots[i].setAttribute("cx", X(p[0])); dots[i].setAttribute("cy", Y(p[1])); dots[i].setAttribute("opacity", 1);
        rows += `<div class="tt-row"><span style="color:${s.color}">&#9632;</span>&nbsp;${s.name}<b>${fmt(p[1])}</b></div>`;
      });
      showTip(`<div class="tt-title">t = ${fmt(xv)}</div>${rows}`, e.clientX, e.clientY);
    });
    hit.addEventListener("mouseleave", () => { cross.setAttribute("opacity", 0); dots.forEach(d => d.setAttribute("opacity", 0)); hideTip(); });

    container.appendChild(svg);
  }

  function logTicks(min, max) {
    const out = [];
    const lo = Math.floor(Math.log10(Math.max(min, 1e-3))), hi = Math.ceil(Math.log10(max));
    for (let e = lo; e <= hi; e++) out.push(Math.pow(10, e));
    return out;
  }
  function nearest(points, xv) {
    let best = null, bd = Infinity;
    for (const p of points) { const d = Math.abs(p[0] - xv); if (d < bd) { bd = d; best = p; } }
    return best;
  }

  // NETWORK GRAPH ------------------------------------------------------------
  // opts: {nodes:[{id,x,y,civ,psi,phi,pop,capital}], edges:[{s,t,w}], civName}
  function networkGraph(container, opts) {
    clear(container);
    const W = Math.max(300, container.clientWidth || 420), H = opts.height || 360;
    const pad = 26;
    const svg = el("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, width: "100%", height: H });
    const nodes = opts.nodes || [], edges = opts.edges || [];
    const X = x => pad + (x + 1) / 2 * (W - 2 * pad);
    const Y = y => pad + (y + 1) / 2 * (H - 2 * pad);
    const pops = nodes.map(n => n.pop || 0); const pmax = Math.max(0.01, ...pops);
    const R = n => 4 + 8 * Math.sqrt((n.pop || 0) / pmax);

    // edges
    const eg = el("g", null);
    edges.forEach(e => {
      const a = nodes[e.s], b = nodes[e.t]; if (!a || !b) return;
      eg.appendChild(el("line", { x1: X(a.x), y1: Y(a.y), x2: X(b.x), y2: Y(b.y),
        stroke: "#5a7fb0", "stroke-width": 1, opacity: 0.10 + 0.5 * e.w }));
    });
    svg.appendChild(eg);

    // nodes
    nodes.forEach(n => {
      const cx = X(n.x), cy = Y(n.y), r = R(n);
      // psi halo (diverging blue↔red around 0)
      const halo = psiColor(n.psi);
      svg.appendChild(el("circle", { cx, cy, r: r + 4, fill: halo, "fill-opacity": 0.18 }));
      const fill = n.civ >= 0 ? civColor(n.civ) : "#3a3a37";
      const c = el("circle", { cx, cy, r, fill, stroke: n.capital ? INK : SURF, "stroke-width": n.capital ? 2 : 1 });
      c.style.cursor = "pointer";
      c.addEventListener("mousemove", (e) => {
        const who = n.civ >= 0 ? (opts.civName ? opts.civName(n.civ) : "Civ " + n.civ) : "uninhabited";
        showTip(`<div class="tt-title">Node ${n.id}${n.capital ? " ★ capital" : ""}</div>` +
          `<div class="tt-row">occupant<b>${who}</b></div>` +
          `<div class="tt-row">population<b>${fmt(n.pop)}</b></div>` +
          `<div class="tt-row">Field &Phi;<b>${fmt(n.phi)}</b></div>` +
          `<div class="tt-row">&psi; state<b>${fmt(n.psi)}</b></div>`, e.clientX, e.clientY);
      });
      c.addEventListener("mouseleave", hideTip);
      svg.appendChild(c);
    });
    container.appendChild(svg);
  }

  function psiColor(psi) {
    // diverging blue (adverse, <0) ↔ gray (0) ↔ red-orange (favorable, >0)
    const t = Math.max(-1, Math.min(1, (psi || 0) / 3));
    if (t < 0) return mix("#383835", "#3987e5", -t);
    return mix("#383835", "#eb6834", t);
  }
  function mix(a, b, t) {
    const pa = hex(a), pb = hex(b);
    const r = Math.round(pa[0] + (pb[0] - pa[0]) * t);
    const g = Math.round(pa[1] + (pb[1] - pa[1]) * t);
    const bl = Math.round(pa[2] + (pb[2] - pa[2]) * t);
    return `rgb(${r},${g},${bl})`;
  }
  function hex(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }

  // TIMELINE -----------------------------------------------------------------
  // opts: {events:[{t,kind,civ,node,detail}], tmax, kinds:{kind:{color,label}}}
  function timeline(container, opts) {
    clear(container);
    const events = opts.events || [];
    const kinds = opts.kinds || {};
    const order = Object.keys(kinds);
    const W = Math.max(320, container.clientWidth || 700);
    const rowH = 22, top = 10, left = 130;
    const H = top + order.length * rowH + 26;
    const tmax = opts.tmax || (events.length ? Math.max(...events.map(e => e.t)) : 1) || 1;
    const svg = el("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, width: "100%", height: H });
    const X = t => left + (t / tmax) * (W - left - 16);

    order.forEach((k, i) => {
      const y = top + i * rowH + rowH / 2;
      svg.appendChild(el("line", { x1: left, x2: W - 16, y1: y, y2: y, stroke: GRID, "stroke-width": 1 }));
      svg.appendChild(el("text", { x: left - 8, y: y + 3, "text-anchor": "end", fill: INK2, "font-size": 11 }, kinds[k].label));
      svg.appendChild(el("rect", { x: 0, y: y - 6, width: 10, height: 12, rx: 2, fill: kinds[k].color }));
    });
    // x axis
    for (let f = 0; f <= 1.0001; f += 0.25) {
      const x = X(f * tmax);
      svg.appendChild(el("line", { x1: x, x2: x, y1: top, y2: H - 20, stroke: GRID, "stroke-width": 1, opacity: 0.5 }));
      svg.appendChild(el("text", { x, y: H - 6, "text-anchor": "middle", fill: MUTED, "font-size": 10 }, fmt(f * tmax)));
    }
    svg.appendChild(el("text", { x: (left + W) / 2, y: H - 6, "text-anchor": "middle", fill: MUTED, "font-size": 10 }, ""));

    events.forEach(ev => {
      const i = order.indexOf(ev.kind); if (i < 0) return;
      const y = top + i * rowH + rowH / 2, x = X(ev.t);
      const mk = el("circle", { cx: x, cy: y, r: 3.6, fill: kinds[ev.kind].color, "fill-opacity": 0.85, stroke: SURF, "stroke-width": 0.6 });
      mk.style.cursor = "pointer";
      mk.addEventListener("mousemove", (e) => {
        showTip(`<div class="tt-title">${kinds[ev.kind].label}</div>` +
          `<div class="tt-row">time<b>${fmt(ev.t)}</b></div>` +
          `<div class="tt-row">civ<b>${ev.civ}</b></div>` +
          (ev.detail ? `<div class="tt-row">detail<b>${ev.detail}</b></div>` : ""), e.clientX, e.clientY);
      });
      mk.addEventListener("mouseleave", hideTip);
      svg.appendChild(mk);
    });
    container.appendChild(svg);
  }

  window.DTCharts = { lineChart, networkGraph, timeline, civColor, PALETTE, fmt };
})();
