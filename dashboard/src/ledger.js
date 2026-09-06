/* The record: every paper contract, sortable, filterable, each one a door to its word. */
window.MM = window.MM || {};

MM.ledger = (function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);

  const COLUMNS = [
    { key: "event_date", label: "Night", sort: (t) => t.event_date + t.entered_at },
    { key: "fight", label: "Fight", sort: (t) => MM.fmt.lastName(t.fighter_1) },
    { key: "phrase", label: "Word", sort: (t) => t.phrase },
    { key: "side", label: "Side", sort: (t) => t.side },
    { key: "price", label: "Entry", num: true, sort: (t) => t.price ?? -1 },
    { key: "model_probability", label: "Us", num: true, sort: (t) => t.model_probability ?? -1 },
    { key: "edge", label: "Edge", num: true, sort: (t) => t.edge ?? -1 },
    { key: "result", label: "Result", sort: (t) => (t.won ? 1 : 0) },
    { key: "pnl", label: "P&L", num: true, sort: (t) => t.pnl ?? 0 },
  ];

  function mount(container, options) {
    const opts = Object.assign({ onOpen: () => {} }, options || {});
    const all = MM.select.trades();
    const nights = MM.select.nights();
    const state = { night: "", side: "", result: "", sortKey: "event_date", dir: -1 };

    container.innerHTML = `
      <header class="section-head" data-reveal>
        <h2 class="section-title" id="recordTitle">The record</h2>
        <p class="section-sub">Every contract the live rule signalled, in the order it happened. Click a row to see the word's whole week.</p>
      </header>
      <div class="ledger-bar" data-reveal>
        <div class="seg" role="group" aria-label="Night">
          <button type="button" class="seg-btn is-active" data-filter="night" data-value="">All nights</button>
          ${nights.slice().reverse().map((n) => `<button type="button" class="seg-btn" data-filter="night" data-value="${esc(n.date)}">${esc(n.label)}</button>`).join("")}
        </div>
        <div class="seg" role="group" aria-label="Result">
          <button type="button" class="seg-btn is-active" data-filter="result" data-value="">All</button>
          <button type="button" class="seg-btn" data-filter="result" data-value="won">Won</button>
          <button type="button" class="seg-btn" data-filter="result" data-value="lost">Lost</button>
        </div>
        <p class="ledger-count" id="ledgerCount" aria-live="polite"></p>
      </div>
      <div class="table-wrap" data-reveal>
        <table class="table ledger">
          <thead><tr>${COLUMNS.map((c) => `<th scope="col" class="${c.num ? "num" : ""}"><button type="button" class="th-btn" data-sort="${c.key}">${c.label}<span class="th-arrow" aria-hidden="true"></span></button></th>`).join("")}</tr></thead>
          <tbody id="ledgerBody"></tbody>
        </table>
      </div>`;

    const body = container.querySelector("#ledgerBody");
    const count = container.querySelector("#ledgerCount");

    function rows() {
      let list = all.filter((t) => (!state.night || t.event_date === state.night) && (!state.result || (state.result === "won") === Boolean(t.won)));
      const col = COLUMNS.find((c) => c.key === state.sortKey) || COLUMNS[0];
      list = list.slice().sort((a, b) => {
        const va = col.sort(a), vb = col.sort(b);
        if (va < vb) return -1 * state.dir;
        if (va > vb) return 1 * state.dir;
        return 0;
      });
      return list;
    }

    function paint() {
      const list = rows();
      const pnl = list.reduce((s, t) => s + (isNum(t.pnl) ? t.pnl : 0), 0);
      const won = list.filter((t) => t.won).length;
      count.innerHTML = `${MM.fmt.plural(list.length, "contract")} · ${won} won · <span class="${pnl >= 0 ? "up" : "down"}">${MM.fmt.money(pnl, { sign: true })}</span>`;
      body.innerHTML = list.map((t, i) => `
        <tr class="ledger-row" data-ticker="${esc(t.ticker)}" tabindex="0" style="--i:${Math.min(i, 30)}">
          <td><span class="ledger-date">${MM.fmt.dateShort(t.event_date)}</span> <span class="ink-3 ledger-time">${MM.fmt.stamp(t.entered_at)}</span></td>
          <td><span class="corner corner-red corner-sm" aria-hidden="true"></span>${esc(MM.fmt.lastName(t.fighter_1))} <span class="ink-3">vs</span> <span class="corner corner-blue corner-sm" aria-hidden="true"></span>${esc(MM.fmt.lastName(t.fighter_2))}</td>
          <td class="ledger-word">${esc(MM.board.splitPhrase(t.phrase).word)}</td>
          <td>${t.side === "yes" ? "Yes" : "No"}</td>
          <td class="num">${MM.fmt.cents(t.price)}</td>
          <td class="num">${MM.fmt.prob(t.model_probability)}</td>
          <td class="num">${MM.fmt.points(t.edge)}</td>
          <td>${t.result ? `<span class="result ${t.won ? "up" : "down"}">${t.won ? "Won" : "Lost"}</span> <span class="ink-3">${t.result === "yes" ? "said" : "not said"}</span>` : "<span class=\"ink-3\">Open</span>"}</td>
          <td class="num ${isNum(t.pnl) ? (t.pnl >= 0 ? "up" : "down") : ""}">${MM.fmt.money(t.pnl, { sign: true })}</td>
        </tr>`).join("");
      container.querySelectorAll(".th-btn").forEach((btn) => {
        const th = btn.closest("th");
        const active = btn.getAttribute("data-sort") === state.sortKey;
        th.setAttribute("aria-sort", active ? (state.dir > 0 ? "ascending" : "descending") : "none");
        btn.classList.toggle("is-active", active);
        btn.classList.toggle("is-desc", active && state.dir < 0);
      });
    }

    const onClick = (ev) => {
      const filter = ev.target.closest("[data-filter]");
      if (filter) {
        state[filter.getAttribute("data-filter")] = filter.getAttribute("data-value");
        filter.parentElement.querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("is-active", b === filter));
        paint();
        return;
      }
      const sort = ev.target.closest("[data-sort]");
      if (sort) {
        const key = sort.getAttribute("data-sort");
        if (state.sortKey === key) state.dir *= -1; else { state.sortKey = key; state.dir = key === "event_date" ? -1 : 1; }
        paint();
        return;
      }
      const row = ev.target.closest(".ledger-row");
      if (row) opts.onOpen(row.getAttribute("data-ticker"));
    };
    const onKey = (ev) => {
      if ((ev.key === "Enter" || ev.key === " ") && ev.target.classList.contains("ledger-row")) { ev.preventDefault(); opts.onOpen(ev.target.getAttribute("data-ticker")); }
    };
    container.addEventListener("click", onClick);
    container.addEventListener("keydown", onKey);
    paint();
    return { destroy() { container.removeEventListener("click", onClick); container.removeEventListener("keydown", onKey); } };
  }

  return { mount };
})();
