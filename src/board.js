/* The board: every fight on the night, every word priced as a tile.
   The fill is the market's YES price. The line across it is our number.
   At the final frame the tiles resolve: said or not said. */
window.MM = window.MM || {};

MM.board = (function () {
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function splitPhrase(phrase) {
    const parts = String(phrase || "").split("/").map((s) => s.trim()).filter(Boolean);
    return { word: parts[0] || String(phrase || ""), alts: parts.slice(1) };
  }

  function tileHtml(m, index) {
    const { word, alts } = splitPhrase(m.phrase);
    const trade = m.trade;
    let tradeLine = "";
    if (trade) {
      const won = trade.won;
      tradeLine = `<span class="tile-trade ${won ? "up" : "down"}">${esc(trade.side === "yes" ? "Yes" : "No")} at ${MM.fmt.cents(trade.price)} · ${MM.fmt.money(trade.pnl, { sign: true })}</span>`;
    }
    return `
      <button class="tile" type="button" data-ticker="${esc(m.ticker)}" style="--i:${index}">
        <span class="tile-fill" aria-hidden="true"></span>
        <span class="tile-model" aria-hidden="true"></span>
        <span class="tile-top">
          <span class="tile-word">${esc(word)}</span>
          ${alts.length ? `<span class="tile-alts">${esc(alts.join(", "))}</span>` : ""}
        </span>
        <span class="tile-state" aria-hidden="true"></span>
        <span class="tile-foot">
          <span class="tile-price"></span>
          <span class="tile-us"></span>
          ${tradeLine}
        </span>
      </button>`;
  }

  function fightHtml(f, index) {
    const pnl = f.trades ? ` · <span class="${f.pnl >= 0 ? "up" : "down"}">${MM.fmt.money(f.pnl, { sign: true })}</span>` : "";
    return `
      <section class="fight" data-event="${esc(f.event_ticker)}" data-reveal style="--i:${index}">
        <header class="fight-head">
          <h3 class="fight-names">
            <span class="corner corner-red" aria-hidden="true"></span><span class="fight-name">${esc(f.fighter_1)}</span>
            <span class="fight-vs">vs</span>
            <span class="corner corner-blue" aria-hidden="true"></span><span class="fight-name">${esc(f.fighter_2)}</span>
          </h3>
          <p class="fight-meta">${MM.fmt.plural(f.markets.length, "word")} · ${f.said} said${f.trades ? ` · ${MM.fmt.plural(f.trades, "trade")}` : ""}${pnl}</p>
        </header>
        <div class="fight-tiles">${f.markets.map((m, i) => tileHtml(m, i)).join("")}</div>
      </section>`;
  }

  function mount(container, night, options) {
    const opts = Object.assign({ frame: night.frames - 1, onOpen: () => {} }, options || {});
    const last = night.frames - 1;
    let frame = Math.max(0, Math.min(last, opts.frame));

    container.innerHTML = `<div class="board is-entering" data-reveal-group>${night.fights.map((f, i) => fightHtml(f, i)).join("")}</div>`;
    const board = container.firstElementChild;

    const tiles = new Map();
    board.querySelectorAll(".tile").forEach((el) => {
      const ticker = el.getAttribute("data-ticker");
      const found = night.markets.find((m) => m.ticker === ticker);
      if (!found) return;
      tiles.set(ticker, {
        el,
        m: found,
        price: el.querySelector(".tile-price"),
        us: el.querySelector(".tile-us"),
        state: el.querySelector(".tile-state"),
        trade: el.querySelector(".tile-trade"),
      });
    });

    function paintTile(t, i, settled) {
      const ask = t.m.ask[i];
      const model = t.m.model[i];
      const p = isNum(ask) ? Math.max(0.02, Math.min(1, ask)) : 0;
      t.el.style.setProperty("--p", p.toFixed(3));
      t.el.style.setProperty("--m", isNum(model) ? Math.max(0, Math.min(1, model)).toFixed(3) : "0");
      t.price.textContent = isNum(ask) ? MM.fmt.cents(ask) : "No quote";
      t.us.textContent = isNum(model) ? "Our " + MM.fmt.prob(model) : "No estimate";
      const gap = isNum(ask) && isNum(model) ? model - ask : 0;
      t.el.classList.toggle("is-divergent", Math.abs(gap) >= 0.15);
      t.el.classList.toggle("is-over", gap >= 0.15);
      t.el.classList.toggle("is-under", gap <= -0.15);
      const result = settled ? t.m.result : null;
      t.el.classList.toggle("is-said", result === "yes");
      t.el.classList.toggle("is-unsaid", result === "no");
      t.el.classList.toggle("is-pending", settled && !result);
      t.state.textContent = result === "yes" ? "Said" : result === "no" ? "Not said" : settled ? "Pending" : "";
      // Keep the visible label intact for voice control; describe the units
      // and matchup separately for screen-reader users.
      t.el.setAttribute("aria-label", t.el.textContent.trim().replace(/\s+/g, " "));
      t.el.setAttribute("aria-description", [
        `${t.m.phrase}. ${t.m.fighter_1} versus ${t.m.fighter_2}`,
        settled && !result ? "Result pending" : settled ? t.state.textContent : "Recorded quote",
        isNum(ask) ? `Yes price ${Math.round(ask * 100)} cents` : "Yes price unavailable",
        isNum(model) ? `Our number ${MM.fmt.prob(model)}` : "Our number unavailable",
      ].join(". "));
    }

    function paintAll() {
      const settled = frame === last;
      tiles.forEach((t) => paintTile(t, frame, settled));
      board.classList.toggle("is-settled", settled);
    }

    // Fills start at zero and rise once the first paint has landed.
    tiles.forEach((t) => { t.el.style.setProperty("--p", "0"); });
    MM.motion.afterPaint(() => {
      paintAll();
      board.classList.remove("is-entering");
    });

    const onClick = (ev) => {
      const tile = ev.target.closest(".tile");
      if (tile) opts.onOpen(tile.getAttribute("data-ticker"));
    };
    board.addEventListener("click", onClick);

    let raf = 0;
    return {
      setFrame(i) {
        const next = Math.max(0, Math.min(last, Math.round(i)));
        if (next === frame) return;
        frame = next;
        cancelAnimationFrame(raf);
        raf = requestAnimationFrame(paintAll);
      },
      focusTile(ticker) {
        const t = tiles.get(ticker);
        if (t) { t.el.scrollIntoView({ block: "center", behavior: MM.motion.reduced() ? "auto" : "smooth" }); t.el.focus({ preventScroll: true }); }
      },
      tickers: () => Array.from(tiles.keys()),
      destroy() { cancelAnimationFrame(raf); board.removeEventListener("click", onClick); container.innerHTML = ""; },
    };
  }

  return { mount, splitPhrase };
})();
