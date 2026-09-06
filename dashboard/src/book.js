/* The book: what the paper trades did, night by night. */
window.MM = window.MM || {};

MM.book = (function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function honestLine(book, nights) {
    const eq = book.equity;
    if (!eq.length) return "";
    const best = eq.reduce((a, b) => (b.card_pnl > a.card_pnl ? b : a));
    const rest = eq.filter((e) => e !== best).reduce((s, e) => s + e.card_pnl, 0);
    const bestNight = nights.find((n) => n.date === best.date);
    const name = bestNight ? bestNight.title : MM.fmt.dateShort(best.date);
    if (eq.length < 2) return `One settled night so far. ${MM.fmt.money(best.card_pnl, { sign: true })} is a sample of one.`;
    return `${MM.fmt.dateShort(best.date)} (${esc(name)}) made ${MM.fmt.money(best.card_pnl, { sign: true })}. The other ${eq.length - 1} nights ${rest < 0 ? "lost" : "made"} ${MM.fmt.money(Math.abs(rest))} between them. Four nights is a record, not a proof.`;
  }

  function mount(container) {
    const book = MM.select.book();
    const nights = MM.select.nights();
    const sign = book.pnl >= 0 ? "up" : "down";
    const hit = book.trades ? book.wins / book.trades : null;

    container.innerHTML = `
      <header class="section-head" data-reveal>
        <h2 class="section-title" id="bookTitle">The book</h2>
        <p class="section-sub">One paper contract per signal, bought at the live price the moment the model flagged it. Nothing here is real money and nothing is edited after the fact.</p>
      </header>
      <div class="book-hero" data-reveal>
        <p class="book-number ${sign}"><span class="book-value">${MM.fmt.money(0)}</span></p>
        <p class="book-sub">
          <span class="${sign}">${MM.fmt.pct(book.ret, { sign: true })}</span> on ${MM.fmt.money(book.staked)} staked
          <span class="dot">·</span> ${MM.fmt.plural(book.trades, "contract")}
          <span class="dot">·</span> ${book.wins} won${hit !== null ? ` (${MM.fmt.pct(hit, { digits: 0 })})` : ""}
          <span class="dot">·</span> ${MM.fmt.plural(book.equity.length, "night")}
        </p>
      </div>
      <div class="book-grid">
        <figure class="figure" data-reveal>
          <figcaption class="figure-title">Profit by night</figcaption>
          <div class="figure-body" id="bookNights"></div>
        </figure>
        <figure class="figure" data-reveal>
          <figcaption class="figure-title">Profit by word, all nights</figcaption>
          <div class="figure-body" id="bookPhrases"></div>
        </figure>
      </div>
      <p class="book-note" data-reveal>${honestLine(book, nights)}</p>`;

    const valueEl = container.querySelector(".book-value");
    const startCount = () => MM.motion.countUp(valueEl, book.pnl, { duration: 1100, format: (v) => MM.fmt.money(v, { sign: true }) });

    const paintCharts = () => {
      MM.charts.bars(container.querySelector("#bookNights"), {
        ariaLabel: "Paper profit for each recorded night",
        height: 240,
        items: book.equity.map((e) => {
          const night = nights.find((n) => n.date === e.date);
          return { label: MM.fmt.dateShort(e.date), sub: night ? night.title : "", value: e.card_pnl, color: e.card_pnl >= 0 ? "var(--up-fill)" : "var(--down-fill)" };
        }),
        format: (v) => MM.fmt.money(v, { sign: true }),
      });
      MM.charts.bars(container.querySelector("#bookPhrases"), {
        ariaLabel: "Paper profit by phrase across all nights",
        horizontal: true,
        labelWidth: 180,
        items: book.byPhrase.slice().sort((a, b) => b.pnl - a.pnl).map((p) => ({ label: MM.board.splitPhrase(p.phrase).word, sub: `${p.wins} of ${p.trades} won`, value: p.pnl, color: p.pnl >= 0 ? "var(--up-fill)" : "var(--down-fill)" })),
        format: (v) => MM.fmt.money(v, { sign: true }),
      });
    };

    // Charts draw when the section scrolls in, so their entrances are seen.
    if ("IntersectionObserver" in window && !MM.motion.reduced()) {
      const io = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) { io.disconnect(); startCount(); paintCharts(); }
      }, { threshold: 0.15 });
      io.observe(container);
    } else { startCount(); paintCharts(); }

    let resizeTimer = 0;
    const onResize = () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(paintCharts, 160); };
    window.addEventListener("resize", onResize);
    return { destroy() { window.removeEventListener("resize", onResize); } };
  }

  return { mount };
})();
