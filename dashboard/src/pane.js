/* The word pane: one market's whole week, with our number drawn through it. */
window.MM = window.MM || {};

MM.pane = (function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);

  let el = null, backdrop = null, chart = null, current = null, lastFocus = null, lastTicker = null, onNav = () => {}, onClosed = () => {};

  function frameOf(night, iso) {
    if (!iso) return -1;
    const t = new Date(iso).getTime();
    if (!Number.isFinite(t)) return -1;
    let best = -1;
    night.stamps.forEach((s, i) => { if (new Date(s).getTime() <= t) best = i; });
    return best;
  }

  function stats(m) {
    const asks = m.ask.filter(isNum);
    const first = m.ask.find(isNum);
    return {
      open: first, high: asks.length ? Math.max(...asks) : null, low: asks.length ? Math.min(...asks) : null,
      last: asks.length ? asks[asks.length - 1] : null, model: m.model.find(isNum),
    };
  }

  function render(hit) {
    const { night, fight, market: m } = hit;
    const { word, alts } = MM.board.splitPhrase(m.phrase);
    const s = stats(m);
    const settled = m.result === "yes" || m.result === "no";
    const gap = isNum(s.model) && isNum(s.open) ? s.model - s.open : null;
    const trade = m.trade;
    const tradeFrame = trade ? frameOf(night, trade.entered_at) : -1;
    const idx = fight.markets.indexOf(m);
    const prev = idx > 0 ? fight.markets[idx - 1] : null;
    const next = idx < fight.markets.length - 1 ? fight.markets[idx + 1] : null;

    el.innerHTML = `
      <div class="pane-inner">
        <header class="pane-head">
          <p class="pane-crumb">${esc(night.label)} · <span class="corner corner-red corner-sm" aria-hidden="true"></span>${esc(fight.fighter_1)} <span class="ink-3">vs</span> <span class="corner corner-blue corner-sm" aria-hidden="true"></span>${esc(fight.fighter_2)}</p>
          <button type="button" class="pane-close" id="paneClose" aria-label="Close">
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M2 2l10 10M12 2 2 12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          </button>
        </header>
        <h2 class="pane-word">${esc(word)}</h2>
        ${alts.length ? `<p class="pane-alts">also counts: ${esc(alts.join(", "))}</p>` : ""}
        <div class="pane-verdict ${m.result === "yes" ? "is-said" : m.result === "no" ? "is-unsaid" : ""}">
          <p class="pane-price">${MM.fmt.cents(s.last)}</p>
          <p class="pane-verdict-text">${settled ? (m.result === "yes" ? "Said on the broadcast" : "Never said") : "Unsettled"}${isNum(s.model) ? ` · we priced it at <b>${MM.fmt.prob(s.model)}</b>` : ""}${isNum(gap) ? ` · opened ${MM.fmt.cents(s.open)}, <span class="${Math.abs(gap) >= 0.15 ? "ink" : "ink-2"}">${Math.abs(gap) >= 0.15 ? "a " + Math.round(Math.abs(gap) * 100) + " point gap" : "close to us"}</span>` : ""}</p>
        </div>
        <div class="pane-chart" id="paneChart"></div>
        <dl class="pane-facts">
          <div><dt>Opened</dt><dd>${MM.fmt.cents(s.open)}</dd></div>
          <div><dt>High</dt><dd>${MM.fmt.cents(s.high)}</dd></div>
          <div><dt>Low</dt><dd>${MM.fmt.cents(s.low)}</dd></div>
          <div><dt>Settled</dt><dd>${settled ? (m.result === "yes" ? "Yes" : "No") : "Open"}</dd></div>
          <div><dt>Frames</dt><dd>${night.frames}</dd></div>
          <div><dt>Ticker</dt><dd class="mono">${esc(m.ticker.split("-").slice(1).join("-"))}</dd></div>
        </dl>
        ${trade ? `
        <div class="pane-trade ${trade.won ? "is-won" : "is-lost"}">
          <p class="pane-trade-head">Paper trade</p>
          <p class="pane-trade-line">Bought <b>${trade.side === "yes" ? "Yes" : "No"}</b> at <b>${MM.fmt.cents(trade.price)}</b> on ${MM.fmt.stamp(trade.entered_at)}${isNum(trade.edge) ? `, ${MM.fmt.points(trade.edge)} of edge` : ""}.</p>
          <p class="pane-trade-result ${trade.won ? "up" : "down"}">${trade.won ? "Won" : "Lost"} ${MM.fmt.money(trade.pnl, { sign: true })}</p>
        </div>` : `<p class="pane-notrade">No paper trade. The live rule never signalled this market.</p>`}
        <nav class="pane-nav" aria-label="Other words in this fight">
          <button type="button" class="pane-nav-btn" id="panePrev" ${prev ? `data-ticker="${esc(prev.ticker)}"` : "disabled"}>← ${prev ? esc(MM.board.splitPhrase(prev.phrase).word) : ""}</button>
          <span class="pane-nav-pos">${idx + 1} of ${fight.markets.length}</span>
          <button type="button" class="pane-nav-btn" id="paneNext" ${next ? `data-ticker="${esc(next.ticker)}"` : "disabled"}>${next ? esc(MM.board.splitPhrase(next.phrase).word) : ""} →</button>
        </nav>
      </div>`;

    const markers = [];
    if (trade && tradeFrame >= 0 && isNum(m.ask[tradeFrame])) markers.push({ i: tradeFrame, y: trade.side === "yes" ? trade.price : 1 - (trade.price ?? 0), label: `Bought ${trade.side} ${MM.fmt.cents(trade.price)}`, color: trade.won ? "var(--up)" : "var(--down)", kind: "trade" });
    if (settled) markers.push({ i: night.frames - 1, y: m.result === "yes" ? 1 : 0, label: m.result === "yes" ? "Said" : "Not said", color: m.result === "yes" ? "var(--up)" : "var(--down)", kind: "settle" });

    if (chart) chart.destroy();
    chart = MM.charts.line(el.querySelector("#paneChart"), {
      ariaLabel: `Price of ${word} through the week`,
      height: 240,
      length: night.frames,
      series: [
        { key: "ask", label: "Yes price", values: m.ask, color: "var(--ink)", width: 2, draw: true },
        { key: "model", label: "Our number", values: m.model, color: "var(--series-model)", width: 2, dash: "4 5" },
      ],
      band: { lo: m.bid, hi: m.ask, color: "var(--ink-3)", label: "Bid to ask" },
      markers,
      xTicks: [0, Math.round((night.frames - 1) / 2), night.frames - 1],
      xLabel: (i, long) => (long ? MM.fmt.stamp(night.stamps[i]) : MM.fmt.stamp(night.stamps[i], { time: false })),
    });

    el.querySelector("#paneClose").addEventListener("click", close);
    el.querySelectorAll(".pane-nav-btn[data-ticker]").forEach((b) => b.addEventListener("click", () => onNav(b.getAttribute("data-ticker"))));
  }

  function open(ticker, options) {
    const hit = MM.select.market(ticker);
    if (!hit || !el) return false;
    const wasOpen = current !== null;
    current = hit;
    lastTicker = ticker;
    if (!wasOpen) lastFocus = document.activeElement;
    // Un-hide before rendering so the chart measures a real width. The pane
    // is still off screen until .is-open lands after the next paint.
    el.hidden = false;
    render(hit);
    backdrop.hidden = false;
    document.body.classList.add("has-pane");
    MM.motion.afterPaint(() => { el.classList.add("is-open"); backdrop.classList.add("is-open"); });
    if (!wasOpen || (options && options.focus)) {
      const closeBtn = el.querySelector("#paneClose");
      if (closeBtn) closeBtn.focus({ preventScroll: true });
    }
    el.scrollTop = 0;
    return true;
  }

  function close() {
    if (!current) return;
    current = null;
    el.classList.remove("is-open");
    backdrop.classList.remove("is-open");
    document.body.classList.remove("has-pane");
    const done = () => { if (!current) { el.hidden = true; backdrop.hidden = true; } };
    if (MM.motion.reduced()) done(); else setTimeout(done, 340);
    if (chart) { chart.destroy(); chart = null; }
    // Return focus to where the reader came from. Opened from a URL, there is
    // no such place, so hand it to the word's own tile if it is on the board.
    const back = lastFocus && lastFocus !== document.body && lastFocus.isConnected ? lastFocus : null;
    const tile = !back && lastTicker ? document.querySelector(`.tile[data-ticker="${lastTicker}"]`) : null;
    if (back) back.focus({ preventScroll: true });
    else if (tile) tile.focus({ preventScroll: true });
    else if (document.activeElement && el.contains(document.activeElement)) document.activeElement.blur();
    onClosed();
  }

  function mount(options) {
    el = document.getElementById("pane");
    backdrop = document.getElementById("paneBackdrop");
    onNav = (options && options.onNavigate) || onNav;
    onClosed = (options && options.onClosed) || onClosed;
    backdrop.addEventListener("click", close);
    el.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") { ev.preventDefault(); close(); }
      if (ev.key === "Tab") {
        const focusables = el.querySelectorAll("button:not([disabled]), [href], [tabindex]:not([tabindex='-1'])");
        if (!focusables.length) return;
        const first = focusables[0], last = focusables[focusables.length - 1];
        if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
        else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
      }
    });
  }

  return { mount, open, close, isOpen: () => current !== null, current: () => current };
})();
