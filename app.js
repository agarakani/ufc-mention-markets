/* Mention Markets. Four nights of UFC announcer-mention markets, priced by a
   transcript model and scored in public. This file wires the sections
   together: routing, the night switch, theme, search, and the footer. */
(function () {
  "use strict";
  const $ = (sel, root) => (root || document).querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const state = { card: null, frame: null, ticker: null };
  const mounted = { timeline: null, board: null, book: null, model: null, ledger: null };

  /* ---------- theme ---------- */
  function theme() { return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark"; }
  function paintTheme() {
    const btn = $("#themeBtn");
    const dark = theme() === "dark";
    btn.setAttribute("aria-label", dark ? "Switch to light" : "Switch to dark");
    btn.innerHTML = dark
      ? `<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="3.2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`
      : `<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M13.5 9.6A6 6 0 0 1 6.4 2.5a6 6 0 1 0 7.1 7.1Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
  }
  function toggleTheme() {
    const next = theme() === "dark" ? "light" : "dark";
    if (next === "light") document.documentElement.setAttribute("data-theme", "light");
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem("mm_theme", next); } catch (e) { /* private mode */ }
    paintTheme();
  }

  /* ---------- routes ---------- */
  function readRoute() {
    const hash = window.location.hash || "";
    let m;
    if ((m = hash.match(/^#\/w\/([A-Z0-9-]+)$/i))) return { type: "word", ticker: m[1] };
    if ((m = hash.match(/^#\/n\/([A-Z0-9]+)$/i))) return { type: "night", card: m[1].toUpperCase() };
    if ((m = hash.match(/^#\/(book|model|record|night)$/))) return { type: "section", id: m[1] };
    return { type: "home" };
  }
  function writeRoute(hash, replace) {
    if (window.location.hash === hash) return;
    if (replace) history.replaceState(null, "", hash); else history.pushState(null, "", hash);
  }

  /* ---------- night ---------- */
  function paintNightSwitch() {
    const nav = $("#nightSwitch");
    nav.innerHTML = MM.select.nights().map((n) => `<a class="night-btn ${n.card === state.card ? "is-active" : ""}" href="#/n/${esc(n.card)}" data-card="${esc(n.card)}" aria-current="${n.card === state.card ? "page" : "false"}"><span class="night-btn-date">${esc(n.label)}</span><span class="night-btn-title">${esc(n.title)}</span></a>`).join("");
  }

  function nightHeadHtml(night) {
    const pnlClass = night.pnl >= 0 ? "up" : "down";
    return `
      <header class="night-head" data-reveal>
        <p class="night-kicker">${esc(MM.fmt.weekday(night.date))}, ${esc(MM.fmt.dateShort(night.date, true))}</p>
        <h2 class="night-title" id="nightTitle">${esc(night.title)}</h2>
        <p class="night-meta">
          <span>${MM.fmt.plural(night.fights.length, "fight")}</span>
          <span>${MM.fmt.plural(night.markets.length, "word")} priced</span>
          <span>${night.said} said</span>
          <span>${MM.fmt.plural(night.trades, "paper trade")}${night.trades ? `, <b class="${pnlClass}">${MM.fmt.money(night.pnl, { sign: true })}</b>` : ""}</span>
        </p>
      </header>
      <div class="night-scrub" id="nightScrub" data-reveal></div>
      <p class="night-key" data-reveal>
        <span class="key-item"><i class="key-fill"></i>Yes price</span>
        <span class="key-item"><i class="key-model"></i>Our number</span>
        <span class="key-item"><i class="key-said"></i>Said</span>
        <span class="key-item"><i class="key-unsaid"></i>Not said</span>
      </p>
      <div class="night-board" id="nightBoard"></div>`;
  }

  function showNight(card, options) {
    const opts = Object.assign({ frame: null, animate: true }, options || {});
    const night = MM.select.night(card) || MM.select.latestNight();
    if (!night) return;
    const changed = night.card !== state.card;
    state.card = night.card;
    paintNightSwitch();

    const section = $("#night");
    if (mounted.timeline) mounted.timeline.destroy();
    if (mounted.board) mounted.board.destroy();
    section.classList.toggle("is-swapping", changed && opts.animate);
    section.innerHTML = nightHeadHtml(night);
    const startFrame = opts.frame === null ? night.frames - 1 : opts.frame;
    state.frame = startFrame;
    mounted.board = MM.board.mount($("#nightBoard", section), night, { frame: startFrame, onOpen: openWord });
    mounted.timeline = MM.timeline.mount($("#nightScrub", section), night, {
      frame: startFrame,
      onFrame: (i) => { state.frame = i; mounted.board.setFrame(i); },
    });
    MM.motion.afterPaint(() => section.classList.remove("is-swapping"));
    MM.motion.reveal(section);
    document.title = `${night.title} · Mention Markets`;
    if (changed && opts.animate) announce(`${night.title}, ${night.label}. ${MM.fmt.plural(night.trades, "paper trade")}.`);
  }

  /* ---------- word ---------- */
  function openWord(ticker, opts) {
    const hit = MM.select.market(ticker);
    if (!hit) return false;
    if (hit.night.card !== state.card) showNight(hit.night.card, { animate: false });
    // Scroll the board to the tile first; the pane must take focus last so
    // the dialog's focus trap holds and the tile is where focus returns.
    if (mounted.board && opts && opts.scroll) mounted.board.focusTile(ticker);
    MM.pane.open(ticker, opts);
    writeRoute(`#/w/${ticker}`, Boolean(opts && opts.replace));
    return true;
  }
  function closedWord() {
    if (readRoute().type === "word") writeRoute(`#/n/${state.card}`, true);
  }

  /* ---------- footer ---------- */
  function paintFooter() {
    const cov = MM.select.model().coverage || {};
    const build = MM.select.build();
    const since = cov.last_card_date ? MM.fmt.dateShort(cov.last_card_date) : "";
    const stamp = MM.select.generatedAt() ? MM.fmt.stamp(MM.select.generatedAt()) : "";
    $("#footer").innerHTML = `
      <div class="footer-inner">
        <div class="footer-col">
          <p class="footer-lead">${since ? `Last recorded night: ${esc(since)}. No later recording is included in this snapshot.` : "No recording dates are available in this snapshot."} Saved data does not confirm whether the recorder is running now.</p>
          <p class="footer-fine">Paper trading only. This site cannot place a trade. The board shows Kalshi's Yes buy prices. Model scoring uses pre-fight bid-ask midpoints adjusted for the spread.</p>
        </div>
        <div class="footer-col footer-meta">
          ${cov.recording_since ? `<p>Recording since ${esc(MM.fmt.dateShort(cov.recording_since))}</p>` : ""}
          ${MM.fmt.isNum(cov.cards_recorded) && MM.fmt.isNum(cov.cards_with_markets) ? `<p>${cov.cards_recorded} of ${cov.cards_with_markets} listed nights captured</p>` : ""}
          ${stamp || build.commit ? `<p>${stamp ? `Data ${esc(stamp)}` : ""} ${build.commit ? `<span class="mono ink-3">build ${esc(build.commit)}</span>` : ""}</p>` : ""}
          <p><a class="footer-link" href="https://github.com/agarakani/ufc-mention-markets" rel="noopener">Source on GitHub</a></p>
        </div>
      </div>`;
  }

  /* ---------- quiet state ---------- */
  function paintEmpty() {
    $("#night").innerHTML = `
      <header class="night-head"><h2 class="night-title" id="nightTitle">Nothing recorded yet</h2>
      <p class="night-meta"><span>No saved fight prices are available in this snapshot.</span></p></header>`;
    ["#book", "#model", "#record"].forEach((id) => { $(id).hidden = true; });
  }

  /* ---------- routing ---------- */
  function applyRoute(initial) {
    const r = readRoute();
    if (r.type === "word") {
      if (openWord(r.ticker, { replace: true, scroll: initial, focus: !initial })) return;
      // unknown ticker: fall through to the night rather than a blank page
      if (!state.card) showNight(null, { animate: false });
      writeRoute(state.card ? `#/n/${state.card}` : "#/", true);
    }
    if (MM.pane.isOpen()) MM.pane.close();
    if (r.type === "night") { if (r.card !== state.card) showNight(r.card); return; }
    if (r.type === "section") {
      if (!state.card) showNight(null, { animate: false });
      const target = $("#" + r.id);
      if (target) target.scrollIntoView({ behavior: initial || MM.motion.reduced() ? "auto" : "smooth", block: "start" });
      return;
    }
    if (!state.card) showNight(null, { animate: false });
  }

  function onPaletteAction(a) {
    if (!a) return;
    if (["night", "fight", "section"].includes(a.type) && MM.pane.isOpen()) MM.pane.close();
    if (a.type === "word") openWord(a.ticker, { scroll: true, focus: true });
    else if (a.type === "night") { writeRoute(`#/n/${a.card}`); showNight(a.card); $("#night").scrollIntoView({ behavior: "smooth", block: "start" }); }
    else if (a.type === "fight") { if (a.card !== state.card) { writeRoute(`#/n/${a.card}`); showNight(a.card, { animate: false }); } const el = document.querySelector(`.fight[data-event="${a.event}"]`); if (el) el.scrollIntoView({ behavior: MM.motion.reduced() ? "auto" : "smooth", block: "start" }); }
    else if (a.type === "section") { writeRoute(`#/${a.id}`); const el = $("#" + a.id); if (el) el.scrollIntoView({ behavior: "smooth", block: "start" }); }
    else if (a.type === "theme") toggleTheme();
    else if (a.type === "copy") { try { navigator.clipboard.writeText(window.location.href); announce("Link copied"); } catch (e) { /* no clipboard */ } }
  }

  function announce(text) { const el = $("#announce"); if (el) { el.textContent = ""; setTimeout(() => { el.textContent = text; }, 30); } }

  /* ---------- boot ---------- */
  function init() {
    paintTheme();
    $("#themeBtn").addEventListener("click", toggleTheme);
    const nights = MM.select.nights();
    MM.pane.mount({ onNavigate: (t) => openWord(t, { focus: true }), onClosed: closedWord });
    MM.palette.mount({
      onPick: onPaletteAction,
      actions: [
        ...(nights.length ? [
        { title: "The board", sub: "Every word on the night", action: { type: "section", id: "night" } },
        { title: "The book", sub: "Paper profit by night and by word", action: { type: "section", id: "book" } },
        { title: "The model", sub: "Calibration, ranking power, the gate", action: { type: "section", id: "model" } },
        { title: "The record", sub: "Every contract, sortable", action: { type: "section", id: "record" } },
        ] : []),
        { title: theme() === "dark" ? "Switch to light" : "Switch to dark", action: { type: "theme" } },
        { title: "Copy link to this view", action: { type: "copy" } },
      ],
    });
    $("#searchBtn").addEventListener("click", MM.palette.open);

    if (nights.length) {
      mounted.book = MM.book.mount($("#book"));
      mounted.model = MM.model.mount($("#model"));
      mounted.ledger = MM.ledger.mount($("#record"), { onOpen: (t) => openWord(t, { focus: true }) });
    } else paintEmpty();
    paintFooter();
    applyRoute(true);
    MM.motion.reveal(document);

    window.addEventListener("hashchange", () => applyRoute(false));
    document.addEventListener("keydown", (ev) => {
      const meta = ev.metaKey || ev.ctrlKey;
      if (meta && (ev.key === "k" || ev.key === "K")) { ev.preventDefault(); MM.palette.isOpen() ? MM.palette.close() : MM.palette.open(); return; }
      if (ev.key === "/" && !ev.target.closest("input, textarea, [contenteditable]")) { ev.preventDefault(); MM.palette.open(); return; }
      if (ev.key === "Escape" && !ev.defaultPrevented && MM.pane.isOpen() && !MM.palette.isOpen()) MM.pane.close();
    });
    $("#nightSwitch").addEventListener("click", (ev) => {
      const a = ev.target.closest(".night-btn");
      if (!a) return;
      ev.preventDefault();
      const card = a.getAttribute("data-card");
      writeRoute(`#/n/${card}`);
      showNight(card);
      $("#night").scrollIntoView({ behavior: MM.motion.reduced() ? "auto" : "smooth", block: "start" });
    });
    const topbar = $("#topbar");
    const onScroll = () => topbar.classList.toggle("is-stuck", window.scrollY > 4);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
