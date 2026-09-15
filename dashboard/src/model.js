/* The model: how the pre-fight numbers held up against the market and a base rate. */
window.MM = window.MM || {};

MM.model = (function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);

  const VARIANT_LABEL = {
    v1: "Fighter history and stats",
    "v1+calib": "Fighter history, recalibrated",
    "v1+group": "Fighter history, per-phrase bias",
    v2: "Fighter history and event tier",
    "v2+calib": "Event tier, recalibrated",
    "v2+group": "Event tier, per-phrase bias",
  };

  function comparison(h) {
    if (![h.model_log_loss, h.base_log_loss, h.market_log_loss].every(isNum) || !h.markets) {
      return "No pre-fight comparison available yet. It needs saved predictions, prices, and settled outcomes for the same markets.";
    }
    const versus = (score) => h.model_log_loss < score ? "beats" : h.model_log_loss > score ? "trails" : "matches";
    const nights = isNum(h.cards) ? ` on ${MM.fmt.plural(h.cards, "night")}` : "";
    const wins = isNum(h.cards_model_won) && isNum(h.cards) ? ` It had the lower score on ${h.cards_model_won} of ${h.cards} nights.` : "";
    return `Lower log loss is better. Over ${h.markets} settled markets${nights}, the model ${versus(h.base_log_loss)} the base rate and ${versus(h.market_log_loss)} the market.${wins}`;
  }

  function mount(container) {
    const m = MM.select.model();
    const h = m.headToHead;
    const cal = m.calibration;
    const gate = m.gate;
    const variants = Object.entries(gate.variant_means || {}).sort((a, b) => a[1] - b[1]);
    const chosen = gate.chosen_variant;
    const holdout = (gate.holdout_cards || []).map((d) => MM.fmt.dateShort(d)).join(", ");
    const counts = m.groups.map((g) => g.scored_fights).filter(isNum);
    const lowCount = counts.length ? Math.min(...counts) : null;
    const highCount = counts.length ? Math.max(...counts) : null;
    const scoredFights = lowCount === null ? "Count unavailable" : lowCount === highCount ? lowCount.toLocaleString("en-US") : `${lowCount.toLocaleString("en-US")} to ${highCount.toLocaleString("en-US")}`;
    const folds = isNum(m.prediction.folds) ? `${m.prediction.folds} folds` : "fold count unavailable";
    const chosenLabel = VARIANT_LABEL[chosen] || chosen;
    const gateNote = chosen && isNum((gate.variant_means || {})[chosen]) ? `Selected: ${esc(chosenLabel)}. The table shows each candidate's score on the held-out nights.` : "No model selection recorded yet.";

    container.innerHTML = `
      <header class="section-head" data-reveal>
        <h2 class="section-title" id="modelTitle">The model</h2>
        <p class="section-sub">A pre-fight chance for each phrase, learned from ${isNum(m.transcripts) ? m.transcripts.toLocaleString("en-US") + " broadcast transcripts" : "historical broadcast transcripts"} and fight details. The comparison below uses the last saved prediction and price at or before noon UTC on fight day. Kalshi prices do not enter the model.</p>
      </header>

      <div class="h2h" data-reveal-group>
        <div class="h2h-item" data-reveal>
          <p class="h2h-label">Model</p>
          <p class="h2h-value" data-count="${isNum(h.model_log_loss) ? h.model_log_loss : ""}">${isNum(h.model_log_loss) ? MM.fmt.num3(h.model_log_loss) : "Unavailable"}</p>
          <p class="h2h-sub">log loss${isNum(h.model_auc) ? ` · AUC ${h.model_auc.toFixed(2)}` : ""}</p>
        </div>
        <div class="h2h-item" data-reveal>
          <p class="h2h-label">Kalshi, bid-ask midpoint</p>
          <p class="h2h-value" data-count="${isNum(h.market_log_loss) ? h.market_log_loss : ""}">${isNum(h.market_log_loss) ? MM.fmt.num3(h.market_log_loss) : "Unavailable"}</p>
          <p class="h2h-sub">log loss${isNum(h.market_auc) ? ` · AUC ${h.market_auc.toFixed(2)}` : ""}</p>
        </div>
        <div class="h2h-item" data-reveal>
          <p class="h2h-label">Base rate</p>
          <p class="h2h-value" data-count="${isNum(h.base_log_loss) ? h.base_log_loss : ""}">${isNum(h.base_log_loss) ? MM.fmt.num3(h.base_log_loss) : "Unavailable"}</p>
          <p class="h2h-sub">log loss${isNum(h.markets) ? ` · same ${h.markets} markets` : ""}</p>
        </div>
      </div>
      <p class="h2h-read" data-reveal>${comparison(h)}</p>

      <div class="model-grid">
        <figure class="figure" data-reveal>
          <figcaption class="figure-title">Calibration <span class="figure-sub">how often the phrase was said against its predicted chance${isNum(cal.markets) ? `, ${cal.markets} markets` : ""}${isNum(cal.ece) ? ` · ECE ${(cal.ece * 100).toFixed(1)} pts` : ""}</span></figcaption>
          <div class="figure-body" id="modelReliability"></div>
        </figure>
        <figure class="figure" data-reveal>
          <figcaption class="figure-title">Ranking power by phrase <span class="figure-sub">AUC on ${scoredFights} historical fights per phrase, ${folds}</span></figcaption>
          <div class="figure-body" id="modelGroups"></div>
        </figure>
      </div>

      <figure class="figure figure-table" data-reveal>
        <figcaption class="figure-title">Model selection <span class="figure-sub">${holdout ? `tested on ${holdout}; ` : ""}the lowest held-out log loss ships</span></figcaption>
        <table class="table gate-table">
          <thead><tr><th scope="col">Candidate</th><th scope="col" class="num">Held-out log loss</th><th scope="col">Decision</th></tr></thead>
          <tbody>
            ${variants.map(([key, val]) => `
              <tr class="${key === chosen ? "is-chosen" : ""}">
                <td>${esc(VARIANT_LABEL[key] || key)} <span class="mono ink-3">${esc(key)}</span></td>
                <td class="num">${MM.fmt.num3(val)}</td>
                <td>${key === chosen ? "Selected" : val > (gate.variant_means || {})[chosen] ? "Higher log loss" : "Not selected"}</td>
              </tr>`).join("") || '<tr><td colspan="3">No model comparison available yet.</td></tr>'}
          </tbody>
        </table>
        <p class="figure-note">${gateNote}${isNum(m.walkforward.labels_count) ? ` ${m.walkforward.labels_count} settled outcomes recorded${m.coverage.recording_since ? " since " + MM.fmt.dateShort(m.coverage.recording_since) : ""}.` : ""}</p>
      </figure>`;

    const paint = () => {
      const reliabilityChart = container.querySelector("#modelReliability");
      const groupChart = container.querySelector("#modelGroups");
      if (!(cal.bins || []).length) reliabilityChart.innerHTML = '<p class="figure-note">No calibration results available yet.</p>';
      else MM.charts.reliability(reliabilityChart, {
        bins: cal.bins || [],
        color: "var(--series-model)",
        size: Math.min(360, (container.querySelector("#modelReliability").clientWidth || 360)),
      });
      if (!m.groups.length) groupChart.innerHTML = '<p class="figure-note">No phrase test results available yet.</p>';
      else MM.charts.bars(groupChart, {
        ariaLabel: "AUC by phrase group",
        horizontal: true,
        labelWidth: 170,
        valueWidth: 56,
        items: m.groups.map((g) => ({ label: MM.board.splitPhrase(g.phrase).word, sub: `${g.positives} said of ${g.scored_fights}${g.beats_base ? "" : " · below base rate"}`, value: g.auc, color: g.beats_base ? "var(--series-model)" : "var(--ink-3)" })),
        format: (v) => (isNum(v) ? v.toFixed(2) : ""),
      });
      container.querySelectorAll(".h2h-value[data-count]").forEach((el) => {
        const raw = el.getAttribute("data-count");
        if (!raw) return;
        const to = Number(raw);
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
