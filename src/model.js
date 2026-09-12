/* The model: how the pre-fight numbers held up against the market and a base rate. */
window.MM = window.MM || {};

MM.model = (function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);

  const VARIANT_LABEL = {
    v1: "Fighter history only",
    "v1+calib": "Fighter history, recalibrated",
    "v1+group": "Fighter history, per-phrase bias",
    v2: "Fighter history and event tier",
    "v2+calib": "Event tier, recalibrated",
    "v2+group": "Event tier, per-phrase bias",
  };

  function mount(container) {
    const m = MM.select.model();
    const h = m.headToHead;
    const cal = m.calibration;
    const gate = m.gate;
    const variants = Object.entries(gate.variant_means || {}).sort((a, b) => a[1] - b[1]);
    const chosen = gate.chosen_variant;
    const holdout = (gate.holdout_cards || []).map((d) => MM.fmt.dateShort(d)).join(", ");
    const cardsWon = isNum(h.cards_model_won) ? h.cards_model_won : null;
    const scoredFights = m.groups.reduce((s, g) => Math.max(s, isNum(g.scored_fights) ? g.scored_fights : 0), 0);

    container.innerHTML = `
      <header class="section-head" data-reveal>
        <h2 class="section-title" id="modelTitle">The model</h2>
        <p class="section-sub">A pre-fight probability for every phrase, built from ${isNum(m.transcripts) ? m.transcripts.toLocaleString("en-US") : "the"} broadcast transcripts: how often each fighter's fights produce the word, what the event tier does to the commentary, and the phrase's base rate. Frozen at noon on fight day, before any market could know the answer.</p>
      </header>

      <div class="h2h" data-reveal-group>
        <div class="h2h-item" data-reveal>
          <p class="h2h-label">Model</p>
          <p class="h2h-value" data-count="${isNum(h.model_log_loss) ? h.model_log_loss : ""}">${MM.fmt.num3(h.model_log_loss)}</p>
          <p class="h2h-sub">log loss · AUC ${isNum(h.model_auc) ? h.model_auc.toFixed(2) : ""}</p>
        </div>
        <div class="h2h-item" data-reveal>
          <p class="h2h-label">Kalshi, de-vigged</p>
          <p class="h2h-value" data-count="${isNum(h.market_log_loss) ? h.market_log_loss : ""}">${MM.fmt.num3(h.market_log_loss)}</p>
          <p class="h2h-sub">log loss · AUC ${isNum(h.market_auc) ? h.market_auc.toFixed(2) : ""}</p>
        </div>
        <div class="h2h-item" data-reveal>
          <p class="h2h-label">Base rate</p>
          <p class="h2h-value" data-count="${isNum(h.base_log_loss) ? h.base_log_loss : ""}">${MM.fmt.num3(h.base_log_loss)}</p>
          <p class="h2h-sub">log loss · same ${h.markets || ""} markets</p>
        </div>
      </div>
      <p class="h2h-read" data-reveal>Lower is better. Over ${h.markets || 0} settled markets on ${h.cards || 0} nights, the model beats the base rate and trails the market${cardsWon !== null ? `, winning ${cardsWon} of ${h.cards} nights head to head` : ""}. The market's edge is the crowd's read on storylines the transcripts cannot see.</p>

      <div class="model-grid">
        <figure class="figure" data-reveal>
          <figcaption class="figure-title">Calibration <span class="figure-sub">said rate against predicted, ${cal.markets || 0} markets · ECE ${isNum(cal.ece) ? (cal.ece * 100).toFixed(1) + " pts" : ""}</span></figcaption>
          <div class="figure-body" id="modelReliability"></div>
        </figure>
        <figure class="figure" data-reveal>
          <figcaption class="figure-title">Ranking power by phrase <span class="figure-sub">AUC on ${scoredFights.toLocaleString("en-US")} historical fights per phrase, ${m.prediction.folds || 5} folds</span></figcaption>
          <div class="figure-body" id="modelGroups"></div>
        </figure>
      </div>

      <figure class="figure figure-table" data-reveal>
        <figcaption class="figure-title">The gate <span class="figure-sub">every candidate is walked forward over ${holdout}; the lowest held-out log loss ships</span></figcaption>
        <table class="table gate-table">
          <thead><tr><th scope="col">Candidate</th><th scope="col" class="num">Held-out log loss</th><th scope="col">Decision</th></tr></thead>
          <tbody>
            ${variants.map(([key, val]) => `
              <tr class="${key === chosen ? "is-chosen" : ""}">
                <td>${esc(VARIANT_LABEL[key] || key)} <span class="mono ink-3">${esc(key)}</span></td>
                <td class="num">${MM.fmt.num3(val)}</td>
                <td>${key === chosen ? "Live" : val > (gate.variant_means || {})[chosen] ? "Rejected, worse held out" : "Rejected"}</td>
              </tr>`).join("")}
          </tbody>
        </table>
        <p class="figure-note">Recalibration and per-phrase bias corrections both fit the training nights and lost on the held-out ones, so the gate refused them. ${isNum(m.walkforward.labels_count) ? m.walkforward.labels_count + " settled labels" : ""}${m.coverage.recording_since ? ", recorded since " + MM.fmt.dateShort(m.coverage.recording_since) : ""}.</p>
      </figure>`;

    const paint = () => {
      MM.charts.reliability(container.querySelector("#modelReliability"), {
        bins: cal.bins || [],
        color: "var(--series-model)",
        size: Math.min(360, (container.querySelector("#modelReliability").clientWidth || 360)),
      });
      MM.charts.bars(container.querySelector("#modelGroups"), {
        ariaLabel: "AUC by phrase group",
        horizontal: true,
        labelWidth: 170,
        valueWidth: 56,
        items: m.groups.map((g) => ({ label: MM.board.splitPhrase(g.phrase).word, sub: `${g.positives} said of ${g.scored_fights}${g.beats_base ? "" : " · below base rate"}`, value: g.auc, color: g.beats_base ? "var(--series-model)" : "var(--ink-3)" })),
        format: (v) => (isNum(v) ? v.toFixed(2) : ""),
      });
      container.querySelectorAll(".h2h-value[data-count]").forEach((el) => {
        const to = Number(el.getAttribute("data-count"));
        if (Number.isFinite(to)) MM.motion.countUp(el, to, { from: 0, duration: 900, format: (v) => v.toFixed(3) });
      });
    };
    if ("IntersectionObserver" in window && !MM.motion.reduced()) {
      const io = new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting)) { io.disconnect(); paint(); } }, { threshold: 0.12 });
      io.observe(container);
    } else paint();

    let timer = 0;
    const onResize = () => { clearTimeout(timer); timer = setTimeout(paint, 160); };
    window.addEventListener("resize", onResize);
    return { destroy() { window.removeEventListener("resize", onResize); } };
  }

  return { mount };
})();
