/* Search: jump to any word, fight, or night, or run an action. */
window.MM = window.MM || {};

MM.palette = (function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let el = null, backdrop = null, input = null, list = null, items = [], results = [], active = 0, opened = false, lastFocus = null, onPick = () => {};

  function buildIndex(actions) {
    const out = [];
    const nights = MM.select.nights();
    nights.slice().reverse().forEach((n) => out.push({ group: "Nights", title: `${n.label} · ${n.title}`, sub: `${n.fights.length} fights, ${n.markets.length} words`, text: `${n.label} ${n.title} ${n.date}`, action: { type: "night", card: n.card } }));
    nights.slice().reverse().forEach((n) => n.fights.forEach((f) => out.push({ group: "Fights", title: `${f.fighter_1} vs ${f.fighter_2}`, sub: `${n.label} · ${f.markets.length} words, ${f.said} said`, text: `${f.fighter_1} ${f.fighter_2} ${n.label}`, action: { type: "fight", card: n.card, event: f.event_ticker } })));
    MM.select.allMarkets().forEach(({ night, fight, market }) => {
      const w = MM.board.splitPhrase(market.phrase);
      out.push({ group: "Words", title: w.word, sub: `${MM.fmt.lastName(fight.fighter_1)} vs ${MM.fmt.lastName(fight.fighter_2)} · ${night.label}${market.result ? (market.result === "yes" ? " · said" : " · not said") : ""}${market.trade ? " · traded" : ""}`, text: `${market.phrase} ${fight.fighter_1} ${fight.fighter_2} ${night.label}`, action: { type: "word", ticker: market.ticker } });
    });
    (actions || []).forEach((a) => out.push({ group: "Go to", title: a.title, sub: a.sub || "", text: a.title, action: a.action }));
    return out;
  }

  function score(item, q) {
    const hay = item.text.toLowerCase();
    if (!q) return item.group === "Go to" || item.group === "Nights" ? 2 : 0;
    if (hay.startsWith(q)) return 100;
    const idx = hay.indexOf(q);
    if (idx >= 0) return 80 - Math.min(40, idx);
    // subsequence: every query character in order
    let i = 0;
    for (const ch of hay) { if (ch === q[i]) i++; if (i === q.length) return 30 - Math.min(20, hay.length / 10); }
    return -1;
  }

  function search(q) {
    const query = q.trim().toLowerCase();
    results = items.map((it) => ({ it, s: score(it, query) })).filter((r) => r.s >= 0).sort((a, b) => b.s - a.s).slice(0, 48).map((r) => r.it);
    active = 0;
    paint();
  }

  function paint() {
    if (!results.length) { list.innerHTML = `<p class="palette-empty">Nothing matches.</p>`; return; }
    let lastGroup = "";
    list.innerHTML = results.map((r, i) => {
      const head = r.group !== lastGroup ? `<p class="palette-group">${esc(r.group)}</p>` : "";
      lastGroup = r.group;
      return `${head}<button type="button" class="palette-item ${i === active ? "is-active" : ""}" data-i="${i}" role="option" aria-selected="${i === active}" tabindex="-1"><span class="palette-title">${esc(r.title)}</span><span class="palette-sub">${esc(r.sub)}</span></button>`;
    }).join("");
    const act = list.querySelector(".palette-item.is-active");
    if (act) act.scrollIntoView({ block: "nearest" });
  }

  function pick(i) {
    const r = results[i];
    if (!r) return;
    close();
    onPick(r.action);
  }

  function open() {
    if (opened) return;
    opened = true;
    lastFocus = document.activeElement;
    el.hidden = false; backdrop.hidden = false;
    document.body.classList.add("has-palette");
    input.value = "";
    search("");
    MM.motion.afterPaint(() => { el.classList.add("is-open"); backdrop.classList.add("is-open"); input.focus(); });
  }

  function close() {
    if (!opened) return;
    opened = false;
    el.classList.remove("is-open"); backdrop.classList.remove("is-open");
    document.body.classList.remove("has-palette");
    const done = () => { if (!opened) { el.hidden = true; backdrop.hidden = true; } };
    if (MM.motion.reduced()) done(); else setTimeout(done, 200);
    if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
  }

  function mount(options) {
    onPick = (options && options.onPick) || onPick;
    el = document.getElementById("palette");
    backdrop = document.getElementById("paletteBackdrop");
    el.innerHTML = `
      <div class="palette-box">
        <input class="palette-input" id="paletteInput" type="text" placeholder="Search words, fights, nights" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="true" aria-controls="paletteList" aria-autocomplete="list">
        <div class="palette-list" id="paletteList" role="listbox"></div>
        <p class="palette-foot"><kbd>↑↓</kbd> move <kbd>↵</kbd> open <kbd>esc</kbd> close</p>
      </div>`;
    input = el.querySelector("#paletteInput");
    list = el.querySelector("#paletteList");
    items = buildIndex(options && options.actions);
    input.addEventListener("input", () => search(input.value));
    // Keys are handled on the dialog, not the input, so they work wherever
    // focus sits inside it. Escape stops here: the word pane behind must not
    // see the same keypress. Tab is swallowed; the input is the only stop.
    el.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowDown") { ev.preventDefault(); active = Math.min(results.length - 1, active + 1); paint(); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); active = Math.max(0, active - 1); paint(); }
      else if (ev.key === "Enter") { ev.preventDefault(); pick(active); }
      else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); close(); }
      else if (ev.key === "Tab") { ev.preventDefault(); input.focus(); }
    });
    list.addEventListener("click", (ev) => { const b = ev.target.closest(".palette-item"); if (b) pick(Number(b.getAttribute("data-i"))); });
    list.addEventListener("pointermove", (ev) => { const b = ev.target.closest(".palette-item"); if (b) { const i = Number(b.getAttribute("data-i")); if (i !== active) { active = i; paint(); } } });
    backdrop.addEventListener("click", close);
  }

  return { mount, open, close, isOpen: () => opened };
})();
