/* Charts: small SVG builders with a hover layer.
   Thin marks, one axis, text in ink tokens, colour only on the series. */
window.MM = window.MM || {};

MM.charts = (function () {
  const NS = "http://www.w3.org/2000/svg";
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);

  function svgEl(tag, attrs) {
    const el = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (v !== null && v !== undefined) el.setAttribute(k, String(v)); });
    return el;
  }
  function htmlEl(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  /* One tooltip element shared by every chart. */
  let tip = null;
  function tooltip() {
    if (!tip) {
      tip = htmlEl("div", "chart-tip");
      tip.setAttribute("role", "status");
      tip.hidden = true;
      document.body.appendChild(tip);
    }
    return tip;
  }
  function showTip(html, x, y) {
    const t = tooltip();
    t.innerHTML = html;
    t.hidden = false;
    const w = t.offsetWidth, h = t.offsetHeight;
    const left = Math.min(window.innerWidth - w - 12, Math.max(12, x + 14));
    const top = y - h - 14 < 12 ? y + 18 : y - h - 14;
    t.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
  }
  function hideTip() { if (tip) tip.hidden = true; }

  function polyline(points) {
    return points.filter((p) => isNum(p[1])).map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  }

  /* Line chart across an index axis (frames). series: [{key,label,values,color,dash,width}]
     band: {lo:[], hi:[], color} draws a translucent ribbon (bid/ask).
     markers: [{i, y, label, color, kind}] draws dots with a 2px surface ring. */
  function line(container, cfg) {
    const o = Object.assign({ height: 220, yDomain: [0, 1], padding: { l: 8, r: 8, t: 14, b: 26 }, xLabel: (i) => String(i), yTicks: [0, 0.25, 0.5, 0.75, 1], yFormat: (v) => Math.round(v * 100) + "%", tipRow: null }, cfg || {});
    container.innerHTML = "";
    const wrap = htmlEl("div", "chart chart-line");
    const width = Math.max(240, container.clientWidth || 600);
    const height = o.height;
    const n = Math.max(2, o.length || (o.series[0] && o.series[0].values.length) || 2);
    const p = o.padding;
    const innerW = width - p.l - p.r, innerH = height - p.t - p.b;
    const x = (i) => p.l + (i / (n - 1)) * innerW;
    const y = (v) => p.t + (1 - (v - o.yDomain[0]) / (o.yDomain[1] - o.yDomain[0])) * innerH;

    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${width} ${height}`, width: "100%", height, role: "img", "aria-label": o.ariaLabel || "" });

    o.yTicks.forEach((t) => {
      svg.appendChild(svgEl("line", { x1: p.l, x2: width - p.r, y1: y(t), y2: y(t), class: "chart-grid" }));
      const label = svgEl("text", { x: width - p.r, y: y(t) - 4, class: "chart-axis chart-axis-y", "text-anchor": "end" });
      label.textContent = o.yFormat(t);
      svg.appendChild(label);
    });

    if (o.band && o.band.lo && o.band.hi) {
      const top = [], bottom = [];
      for (let i = 0; i < n; i++) {
        if (isNum(o.band.hi[i]) && isNum(o.band.lo[i])) { top.push([x(i), y(o.band.hi[i])]); bottom.push([x(i), y(o.band.lo[i])]); }
      }
      if (top.length > 1) {
        const d = polyline(top) + " " + bottom.reverse().map((pt) => "L" + pt[0].toFixed(1) + " " + pt[1].toFixed(1)).join(" ") + " Z";
        svg.appendChild(svgEl("path", { d, class: "chart-band", fill: o.band.color || "currentColor" }));
      }
    }

    o.series.forEach((s) => {
      const pts = [];
      for (let i = 0; i < n; i++) pts.push([x(i), isNum(s.values[i]) ? y(s.values[i]) : NaN]);
      const path = svgEl("path", { d: polyline(pts), class: "chart-series" + (s.draw ? " is-drawing" : ""), fill: "none", stroke: s.color || "currentColor", "stroke-width": s.width || 2, "stroke-dasharray": s.dash || null, "stroke-linejoin": "round", "stroke-linecap": "round" });
      svg.appendChild(path);
      if (s.draw && !MM.motion.reduced()) {
        const len = path.getTotalLength ? path.getTotalLength() : 0;
        if (len) {
          path.style.strokeDasharray = s.dash ? s.dash : String(len);
          path.style.strokeDashoffset = String(len);
          MM.motion.afterPaint(() => { path.style.transition = "stroke-dashoffset 900ms cubic-bezier(0.16,1,0.3,1)"; path.style.strokeDashoffset = "0"; });
        }
      }
    });

    (o.markers || []).forEach((m) => {
      if (!isNum(m.i) || !isNum(m.y)) return;
      const g = svgEl("g", { class: "chart-marker chart-marker-" + (m.kind || "dot") });
      g.appendChild(svgEl("circle", { cx: x(m.i), cy: y(m.y), r: 6, class: "chart-marker-ring" }));
      g.appendChild(svgEl("circle", { cx: x(m.i), cy: y(m.y), r: 4, fill: m.color || "currentColor" }));
      if (m.label) {
        const t = svgEl("text", { x: x(m.i), y: y(m.y) - 11, class: "chart-marker-label", "text-anchor": m.i > n * 0.8 ? "end" : m.i < n * 0.2 ? "start" : "middle" });
        t.textContent = m.label;
        g.appendChild(t);
      }
      svg.appendChild(g);
    });

    const ticks = o.xTicks || [0, Math.round((n - 1) / 2), n - 1];
    ticks.forEach((i, k) => {
      const t = svgEl("text", { x: x(i), y: height - 8, class: "chart-axis", "text-anchor": k === 0 ? "start" : k === ticks.length - 1 ? "end" : "middle" });
      t.textContent = o.xLabel(i);
      svg.appendChild(t);
    });

    const cross = svgEl("line", { x1: 0, x2: 0, y1: p.t, y2: height - p.b, class: "chart-cross" });
    cross.style.opacity = "0";
    svg.appendChild(cross);
    const dots = o.series.map((s) => { const c = svgEl("circle", { r: 4, fill: s.color || "currentColor", class: "chart-cross-dot" }); c.style.opacity = "0"; svg.appendChild(c); return c; });

    wrap.appendChild(svg);
    container.appendChild(wrap);

    const onMove = (ev) => {
      const rect = svg.getBoundingClientRect();
      const px = ((ev.clientX - rect.left) / rect.width) * width;
      const i = Math.max(0, Math.min(n - 1, Math.round(((px - p.l) / innerW) * (n - 1))));
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.style.opacity = "1";
      const rows = [];
      o.series.forEach((s, k) => {
        const v = s.values[i];
        if (isNum(v)) { dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(v)); dots[k].style.opacity = "1"; rows.push(`<span class="tip-row"><i style="background:${s.color}"></i>${s.label}<b>${o.yFormat(v)}</b></span>`); }
        else dots[k].style.opacity = "0";
      });
      if (o.band && isNum(o.band.lo[i]) && isNum(o.band.hi[i]) && o.band.label) rows.push(`<span class="tip-row"><i style="background:${o.band.color}"></i>${o.band.label}<b>${o.yFormat(o.band.lo[i])} to ${o.yFormat(o.band.hi[i])}</b></span>`);
      showTip(`<span class="tip-head">${o.xLabel(i, true)}</span>` + rows.join(""), ev.clientX, ev.clientY);
      if (o.onHover) o.onHover(i);
    };
    const onLeave = () => { cross.style.opacity = "0"; dots.forEach((d) => { d.style.opacity = "0"; }); hideTip(); if (o.onHover) o.onHover(null); };
    svg.addEventListener("pointermove", onMove);
    svg.addEventListener("pointerleave", onLeave);
    return { svg, destroy: () => { svg.removeEventListener("pointermove", onMove); svg.removeEventListener("pointerleave", onLeave); hideTip(); } };
  }

  /* Vertical or horizontal bars around a zero baseline. items: [{label, value, color, sub}] */
  function bars(container, cfg) {
    const o = Object.assign({ height: 200, horizontal: false, format: (v) => String(v), gap: 10, radius: 4, labelWidth: 150, valueWidth: 64, direct: true, animate: true }, cfg || {});
    container.innerHTML = "";
    const wrap = htmlEl("div", "chart chart-bars" + (o.horizontal ? " is-horizontal" : ""));
    const items = o.items || [];
    const max = Math.max(1e-9, ...items.map((d) => Math.abs(d.value || 0)));
    const width = Math.max(240, container.clientWidth || 600);

    if (o.horizontal) {
      const rowH = 30;
      const height = items.length * rowH + 8;
      const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${width} ${height}`, width: "100%", height, role: "img", "aria-label": o.ariaLabel || "" });
      const x0 = o.labelWidth, span = width - o.labelWidth - o.valueWidth;
      const hasNeg = items.some((d) => d.value < 0);
      const zero = hasNeg ? x0 + span / 2 : x0;
      const scale = (hasNeg ? span / 2 : span) / max;
      if (hasNeg) svg.appendChild(svgEl("line", { x1: zero, x2: zero, y1: 4, y2: height - 4, class: "chart-zero" }));
      items.forEach((d, i) => {
        const yy = 4 + i * rowH;
        const label = svgEl("text", { x: x0 - 12, y: yy + 19, class: "chart-label", "text-anchor": "end" });
        label.textContent = d.label;
        svg.appendChild(label);
        const w = Math.abs(d.value || 0) * scale;
        const rect = svgEl("rect", { x: d.value < 0 ? zero - w : zero, y: yy + 6, width: Math.max(2, w), height: rowH - 12, rx: o.radius, fill: d.color || "currentColor", class: "chart-bar" });
        if (o.animate && !MM.motion.reduced()) { rect.style.transformOrigin = `${zero}px ${yy + 6}px`; rect.style.transform = "scaleX(0)"; rect.style.transition = `transform 700ms cubic-bezier(0.16,1,0.3,1) ${Math.min(i, 20) * 28}ms`; MM.motion.afterPaint(() => { rect.style.transform = "scaleX(1)"; }); }
        svg.appendChild(rect);
        const val = svgEl("text", { x: d.value < 0 ? zero - w - 8 : zero + w + 8, y: yy + 19, class: "chart-value", "text-anchor": d.value < 0 ? "end" : "start" });
        val.textContent = o.format(d.value);
        svg.appendChild(val);
        const hit = svgEl("rect", { x: 0, y: yy, width, height: rowH, fill: "transparent", class: "chart-hit" });
        hit.addEventListener("pointermove", (ev) => showTip(`<span class="tip-head">${d.label}</span><span class="tip-row">${d.sub || ""}<b>${o.format(d.value)}</b></span>`, ev.clientX, ev.clientY));
        hit.addEventListener("pointerleave", hideTip);
        svg.appendChild(hit);
      });
      wrap.appendChild(svg);
    } else {
      const height = o.height;
      const pad = { t: 28, b: 28 };
      const n = items.length;
      const slot = width / Math.max(1, n);
      const barW = Math.max(12, Math.min(72, slot * 0.56));
      const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${width} ${height}`, width: "100%", height, role: "img", "aria-label": o.ariaLabel || "" });
      const hasNeg = items.some((d) => d.value < 0);
      const innerH = height - pad.t - pad.b;
      const zero = hasNeg ? pad.t + innerH * (max / (2 * max)) : height - pad.b;
      const scale = (hasNeg ? innerH / 2 : innerH) / max;
      svg.appendChild(svgEl("line", { x1: 0, x2: width, y1: zero, y2: zero, class: "chart-zero" }));
      items.forEach((d, i) => {
        const cx = slot * i + slot / 2;
        const h = Math.abs(d.value || 0) * scale;
        const rect = svgEl("rect", { x: cx - barW / 2, y: d.value < 0 ? zero : zero - h, width: barW, height: Math.max(2, h), rx: o.radius, fill: d.color || "currentColor", class: "chart-bar" });
        if (o.animate && !MM.motion.reduced()) { rect.style.transformOrigin = `${cx}px ${zero}px`; rect.style.transform = "scaleY(0)"; rect.style.transition = `transform 700ms cubic-bezier(0.16,1,0.3,1) ${i * 60}ms`; MM.motion.afterPaint(() => { rect.style.transform = "scaleY(1)"; }); }
        svg.appendChild(rect);
        const val = svgEl("text", { x: cx, y: d.value < 0 ? zero + h + 16 : zero - h - 8, class: "chart-value", "text-anchor": "middle" });
        val.textContent = o.format(d.value);
        svg.appendChild(val);
        const label = svgEl("text", { x: cx, y: height - 8, class: "chart-label", "text-anchor": "middle" });
        label.textContent = d.label;
        svg.appendChild(label);
        const hit = svgEl("rect", { x: slot * i, y: 0, width: slot, height, fill: "transparent", class: "chart-hit" });
        hit.addEventListener("pointermove", (ev) => showTip(`<span class="tip-head">${d.label}</span><span class="tip-row">${d.sub || ""}<b>${o.format(d.value)}</b></span>`, ev.clientX, ev.clientY));
        hit.addEventListener("pointerleave", hideTip);
        svg.appendChild(hit);
      });
      wrap.appendChild(svg);
    }
    container.appendChild(wrap);
    return { destroy: hideTip };
  }

  /* Reliability diagram: predicted vs observed, dot size by count, 45 degree reference. */
  function reliability(container, cfg) {
    const o = Object.assign({ size: 300, bins: [], color: "currentColor" }, cfg || {});
    container.innerHTML = "";
    const wrap = htmlEl("div", "chart chart-reliability");
    const size = Math.max(220, Math.min(o.size, container.clientWidth || o.size));
    const p = { l: 34, r: 12, t: 12, b: 30 };
    const inner = size - p.l - p.r, innerH = size - p.t - p.b;
    const x = (v) => p.l + v * inner, y = (v) => p.t + (1 - v) * innerH;
    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${size} ${size}`, width: size, height: size, role: "img", "aria-label": o.ariaLabel || "Reliability of the model's probabilities" });
    [0, 0.25, 0.5, 0.75, 1].forEach((t) => {
      svg.appendChild(svgEl("line", { x1: p.l, x2: size - p.r, y1: y(t), y2: y(t), class: "chart-grid" }));
      const ly = svgEl("text", { x: p.l - 8, y: y(t) + 4, class: "chart-axis", "text-anchor": "end" }); ly.textContent = Math.round(t * 100) + "%"; svg.appendChild(ly);
      const lx = svgEl("text", { x: x(t), y: size - 10, class: "chart-axis", "text-anchor": t === 0 ? "start" : t === 1 ? "end" : "middle" }); lx.textContent = Math.round(t * 100) + "%"; svg.appendChild(lx);
    });
    svg.appendChild(svgEl("line", { x1: x(0), y1: y(0), x2: x(1), y2: y(1), class: "chart-reference" }));
    const maxCount = Math.max(1, ...o.bins.map((b) => b.count || 0));
    const pts = o.bins.filter((b) => isNum(b.mean_prediction) && isNum(b.actual_rate) && b.count > 0);
    const path = svgEl("path", { d: polyline(pts.map((b) => [x(b.mean_prediction), y(b.actual_rate)])), fill: "none", stroke: o.color, "stroke-width": 2, "stroke-linejoin": "round", class: "chart-series" });
    svg.appendChild(path);
    pts.forEach((b, i) => {
      const r = 4 + 8 * Math.sqrt(b.count / maxCount);
      const g = svgEl("g", { class: "chart-marker" });
      g.appendChild(svgEl("circle", { cx: x(b.mean_prediction), cy: y(b.actual_rate), r: r + 2, class: "chart-marker-ring" }));
      const c = svgEl("circle", { cx: x(b.mean_prediction), cy: y(b.actual_rate), r, fill: o.color, "fill-opacity": 0.9 });
      if (!MM.motion.reduced()) { c.style.transformOrigin = `${x(b.mean_prediction)}px ${y(b.actual_rate)}px`; c.style.transform = "scale(0)"; c.style.transition = `transform 500ms cubic-bezier(0.16,1,0.3,1) ${i * 50}ms`; MM.motion.afterPaint(() => { c.style.transform = "scale(1)"; }); }
      g.appendChild(c);
      g.addEventListener("pointermove", (ev) => showTip(`<span class="tip-head">Predicted ${Math.round(b.low * 100)} to ${Math.round(b.high * 100)}%</span><span class="tip-row">Said<b>${Math.round(b.actual_rate * 100)}%</b></span><span class="tip-row">Mean prediction<b>${Math.round(b.mean_prediction * 100)}%</b></span><span class="tip-row">Markets<b>${b.count}</b></span>`, ev.clientX, ev.clientY));
      g.addEventListener("pointerleave", hideTip);
      svg.appendChild(g);
    });
    wrap.appendChild(svg);
    container.appendChild(wrap);
    return { destroy: hideTip };
  }

  /* Tiny inline path for a sparkline. */
  function sparkPath(values, w, h) {
    const vals = values.filter(isNum);
    if (vals.length < 2) return "";
    const n = values.length;
    return polyline(values.map((v, i) => [(i / (n - 1)) * w, isNum(v) ? (1 - v) * (h - 2) + 1 : NaN]));
  }

  return { line, bars, reliability, sparkPath, hideTip };
})();
