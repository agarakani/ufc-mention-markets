(function () {
  const data = window.UFC_MENTION_DASHBOARD_DATA;
  const state = {
    view: "edges",
    phrase: "",
    scope: "",
    search: "",
    sortKey: "",
    sortDir: "desc",
  };

  const views = {
    edges: {
      title: "Edges",
      empty: "No mapped price rows yet. The board will fill after market mappings and top-of-book prices are generated.",
      rows: () => data.edges || [],
      columns: [
        { key: "edge_to_yes_ask", label: "Edge", type: "pct", className: "num", badge: true, signed: true },
        { key: "model_probability", label: "Model", type: "pct", className: "num" },
        { key: "yes_ask", label: "Ask", type: "pct", className: "num" },
        { key: "phrase", label: "Phrase", type: "pill" },
        { key: "scope", label: "Scope", type: "scope" },
        { key: "event_date", label: "Date" },
        { key: "matchup", label: "Fight / event" },
        { key: "question", label: "Market", type: "question" },
      ],
    },
    events: {
      title: "Event probabilities",
      empty: "No event prediction rows found.",
      rows: () => data.events || [],
      columns: [
        { key: "event_probability", label: "Any fight", type: "pct", className: "num" },
        { key: "phrase", label: "Phrase", type: "pill" },
        { key: "event_date", label: "Date" },
        { key: "location", label: "Location" },
        { key: "mean_fight_probability", label: "Avg fight", type: "pct", className: "num" },
        { key: "max_fight_probability", label: "Top fight", type: "pct", className: "num" },
        { key: "fight_count", label: "Fights", className: "num" },
        { key: "profile", label: "Profile" },
      ],
    },
    fights: {
      title: "Fight probabilities",
      empty: "No fight prediction rows found.",
      rows: () => data.fights || [],
      columns: [
        { key: "probability", label: "Model", type: "pct", className: "num" },
        { key: "phrase", label: "Phrase", type: "pill" },
        { key: "matchup", label: "Fight" },
        { key: "event_date", label: "Date" },
        { key: "weight_class", label: "Weight" },
        { key: "rounds", label: "Rounds", className: "num" },
        { key: "location", label: "Location" },
      ],
    },
    markets: {
      title: "Market candidates",
      empty: "No classified mention market rows found.",
      rows: () => data.markets || [],
      columns: [
        { key: "status", label: "Status", type: "status" },
        { key: "mapped_phrase", label: "Phrase", type: "pill" },
        { key: "last_yes_price", label: "Last YES", type: "pct", className: "num" },
        { key: "volume", label: "Volume", type: "money", className: "num" },
        { key: "liquidity", label: "Liquidity", type: "money", className: "num" },
        { key: "market_complexity", label: "Type" },
        { key: "needs_manual_review", label: "Review", type: "review" },
        { key: "question", label: "Question", type: "question" },
      ],
    },
    metrics: {
      title: "Model checks",
      empty: "No model metric rows found.",
      rows: () => data.metrics || [],
      columns: [
        { key: "log_loss_improvement", label: "Lift", type: "signed", className: "num" },
        { key: "phrase", label: "Phrase", type: "pill" },
        { key: "scope", label: "Level", type: "scope" },
        { key: "profile", label: "Profile" },
        { key: "auc", label: "AUC", type: "decimal", className: "num" },
        { key: "average_precision", label: "Avg precision", type: "decimal", className: "num" },
        { key: "test_positive_rate", label: "Test Yes", type: "pct", className: "num" },
        { key: "top_decile_actual_rate", label: "Top decile Yes", type: "pct", className: "num" },
        { key: "test_rows", label: "Test rows", className: "num" },
      ],
    },
  };

  const els = {
    status: document.getElementById("dataStatus"),
    stats: document.getElementById("stats"),
    viewButtons: document.getElementById("viewButtons"),
    phraseFilter: document.getElementById("phraseFilter"),
    scopeFilter: document.getElementById("scopeFilter"),
    searchInput: document.getElementById("searchInput"),
    resetButton: document.getElementById("resetButton"),
    tableTitle: document.getElementById("tableTitle"),
    tableMeta: document.getElementById("tableMeta"),
    tableHead: document.getElementById("tableHead"),
    tableBody: document.getElementById("tableBody"),
    diagnostics: document.getElementById("modelDiagnostics"),
    calibrationMeta: document.getElementById("calibrationMeta"),
    calibrationChart: document.getElementById("calibrationChart"),
    liftChart: document.getElementById("liftChart"),
    featureChart: document.getElementById("featureChart"),
    backtestChart: document.getElementById("backtestChart"),
  };

  function init() {
    if (!data) {
      els.status.textContent = "Run python3 build_dashboard_data.py";
      els.tableBody.innerHTML = '<tr><td class="empty">No local dashboard data found.</td></tr>';
      return;
    }

    populatePhraseFilter();
    renderStats();
    bindEvents();
    render();
  }

  function bindEvents() {
    els.viewButtons.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-view]");
      if (!button) return;
      state.view = button.dataset.view;
      state.sortKey = "";
      state.sortDir = "desc";
      document.querySelectorAll(".segment").forEach((item) => item.classList.toggle("is-active", item === button));
      render();
    });

    els.phraseFilter.addEventListener("change", () => {
      state.phrase = els.phraseFilter.value;
      render();
    });

    els.scopeFilter.addEventListener("change", () => {
      state.scope = els.scopeFilter.value;
      render();
    });

    els.searchInput.addEventListener("input", () => {
      state.search = els.searchInput.value.trim().toLowerCase();
      render();
    });

    els.resetButton.addEventListener("click", () => {
      state.phrase = "";
      state.scope = "";
      state.search = "";
      state.sortKey = "";
      state.sortDir = "desc";
      els.phraseFilter.value = "";
      els.scopeFilter.value = "";
      els.searchInput.value = "";
      render();
    });
  }

  function populatePhraseFilter() {
    const phrases = new Set();
    ["edges", "events", "fights", "markets", "metrics"].forEach((view) => {
      views[view].rows().forEach((row) => {
        const phrase = row.phrase || row.mapped_phrase;
        if (phrase) phrases.add(phrase);
      });
    });

    [...phrases].sort((a, b) => a.localeCompare(b)).forEach((phrase) => {
      const option = document.createElement("option");
      option.value = phrase.toLowerCase();
      option.textContent = phrase;
      els.phraseFilter.appendChild(option);
    });
  }

  function renderStats() {
    const summary = data.summary || {};
    const stats = [
      [summary.fight_count || 0, "upcoming fights"],
      [summary.phrase_count || 0, "tracked phrases"],
      [summary.active_market_candidate_count || 0, "active market candidates"],
      [summary.priced_edge_count || 0, "priced edge rows"],
    ];

    els.stats.innerHTML = stats.map(([value, label]) => (
      `<div class="stat"><strong>${formatInteger(value)}</strong><span>${escapeHtml(label)}</span></div>`
    )).join("");

    const generated = data.generated_at ? new Date(data.generated_at).toLocaleString() : "unknown";
    const dateRange = summary.min_event_date && summary.max_event_date
      ? ` card date ${summary.min_event_date === summary.max_event_date ? summary.max_event_date : `${summary.min_event_date} to ${summary.max_event_date}`}`
      : "";
    const stale = summary.upcoming_input_is_stale ? " stale upcoming input" : " current upcoming input";
    els.status.textContent = `Local data built ${generated};${dateRange};${stale}`;
  }

  function render() {
    const view = views[state.view];
    let rows = view.rows().map(deriveRow);
    rows = applyFilters(rows);
    rows = applySort(rows, view.columns);

    els.scopeFilter.disabled = state.view !== "edges";
    els.tableTitle.textContent = view.title;
    els.tableMeta.textContent = `${formatInteger(rows.length)} rows`;
    els.diagnostics.hidden = state.view !== "metrics";
    if (state.view === "metrics") renderDiagnostics(rows);
    renderHeader(view.columns);
    renderBody(view.columns, rows, view.empty);
  }

  function selectedModelPhrase(metricRows) {
    if (state.phrase) return state.phrase;
    const eventWinner = metricRows.find((row) => row.scope === "event" && parseNumber(row.log_loss_improvement) > 0);
    return String((eventWinner || metricRows[0] || {}).phrase || "").toLowerCase();
  }

  function renderDiagnostics(metricRows) {
    const phrase = selectedModelPhrase(metricRows);
    renderCalibration(phrase);
    renderLift();
    renderFeatures(phrase);
    renderBacktest();
  }

  function renderCalibration(phrase) {
    const rows = (data.calibration || []).filter((row) => String(row.phrase || "").toLowerCase() === phrase);
    els.calibrationMeta.textContent = phrase || "Select a phrase";
    if (!rows.length) {
      els.calibrationChart.innerHTML = '<p class="chart-empty">No calibration rows for this phrase.</p>';
      return;
    }
    const left = 42;
    const top = 14;
    const size = 210;
    const point = (row) => {
      const x = left + Math.max(0, Math.min(1, Number(row.mean_predicted))) * size;
      const y = top + (1 - Math.max(0, Math.min(1, Number(row.actual_rate)))) * size;
      return [x, y];
    };
    const series = ["fight", "event"].map((scope) => {
      const scoped = rows.filter((row) => row.scope === scope).sort((a, b) => Number(a.mean_predicted) - Number(b.mean_predicted));
      if (!scoped.length) return "";
      const points = scoped.map(point);
      const circles = points.map(([x, y], index) => (
        `<circle class="cal-point ${scope}" cx="${x}" cy="${y}" r="5"><title>${scope}: predicted ${formatPercent(scoped[index].mean_predicted)}, actual ${formatPercent(scoped[index].actual_rate)}</title></circle>`
      )).join("");
      return `<polyline class="cal-line ${scope}" points="${points.map((p) => p.join(",")).join(" ")}"/>${circles}`;
    }).join("");
    els.calibrationChart.innerHTML = `
      <svg class="calibration-svg" viewBox="0 0 300 260" role="img" aria-label="Predicted versus actual mention rate">
        <line class="cal-axis" x1="${left}" y1="${top + size}" x2="${left + size}" y2="${top + size}"/>
        <line class="cal-axis" x1="${left}" y1="${top}" x2="${left}" y2="${top + size}"/>
        <line class="cal-perfect" x1="${left}" y1="${top + size}" x2="${left + size}" y2="${top}"/>
        ${series}
        <text x="${left + size / 2}" y="254" text-anchor="middle">Predicted probability</text>
        <text x="12" y="${top + size / 2}" text-anchor="middle" transform="rotate(-90 12 ${top + size / 2})">Actual rate</text>
        <text x="${left}" y="240" text-anchor="middle">0</text><text x="${left + size}" y="240" text-anchor="middle">1</text>
        <text x="32" y="${top + size + 4}" text-anchor="end">0</text><text x="32" y="${top + 4}" text-anchor="end">1</text>
      </svg>
      <div class="legend"><span><i class="fight"></i>Fight</span><span><i class="event"></i>Event</span><span><i class="perfect"></i>Perfect</span></div>`;
  }

  function renderLift() {
    const rows = (data.metrics || [])
      .filter((row) => row.scope === "event" && parseNumber(row.log_loss_improvement) !== null)
      .sort((a, b) => Number(b.log_loss_improvement) - Number(a.log_loss_improvement))
      .slice(0, 8);
    renderBars(els.liftChart, rows.map((row) => ({
      label: row.phrase,
      value: Number(row.log_loss_improvement),
      display: formatSigned(row.log_loss_improvement),
    })));
  }

  function renderFeatures(phrase) {
    const rows = (data.features || [])
      .filter((row) => String(row.phrase || "").toLowerCase() === phrase && parseNumber(row.coefficient) !== null)
      .sort((a, b) => Math.abs(Number(b.coefficient)) - Math.abs(Number(a.coefficient)))
      .slice(0, 8)
      .map((row) => ({
        label: cleanFeature(row.feature),
        value: Number(row.coefficient),
        display: `${Number(row.coefficient) > 0 ? "+" : ""}${Number(row.coefficient).toFixed(2)}`,
      }));
    renderBars(els.featureChart, rows);
  }

  function renderBars(element, rows) {
    if (!rows.length) {
      element.innerHTML = '<p class="chart-empty">No diagnostic rows available.</p>';
      return;
    }
    const max = Math.max(...rows.map((row) => Math.abs(row.value)), 0.0001);
    element.innerHTML = rows.map((row) => `
      <div class="bar-row">
        <div class="bar-label"><span title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span><strong>${escapeHtml(row.display)}</strong></div>
        <div class="bar-track"><span class="bar-fill ${row.value >= 0 ? "good" : "bad"}" style="width:${Math.max(2, Math.abs(row.value) / max * 100)}%"></span></div>
      </div>`).join("");
  }

  function renderBacktest() {
    const summary = data.backtest || {};
    const trades = Number(summary.trades || 0);
    const minimum = Number(summary.minimum_trades_for_claim || 30);
    const progress = Math.min(100, trades / Math.max(minimum, 1) * 100);
    els.backtestChart.innerHTML = `
      <div class="readiness-number"><strong>${formatInteger(trades)}</strong><span>of ${formatInteger(minimum)} minimum trades</span></div>
      <div class="readiness-track"><span style="width:${progress}%"></span></div>
      <p class="readiness-note">${escapeHtml(summary.claim_status === "sufficient_sample" ? "Evidence threshold reached" : "No performance claim yet")}</p>`;
  }

  function cleanFeature(value) {
    return String(value || "")
      .replace(/^(num|cat)__/, "")
      .replace(/^kaggle_/, "")
      .replace(/^fighter_history_/, "history: ")
      .replace(/_/g, " ");
  }

  function deriveRow(row) {
    const out = { ...row };
    const fighter1 = row.fighter_1 || "";
    const fighter2 = row.fighter_2 || "";
    out.matchup = fighter1 && fighter2 ? `${fighter1} vs ${fighter2}` : row.location || row.event_title || "";
    out.search_blob = Object.values(out).join(" ").toLowerCase();
    return out;
  }

  function applyFilters(rows) {
    return rows.filter((row) => {
      const rowPhrase = (row.phrase || row.mapped_phrase || "").toLowerCase();
      if (state.phrase && rowPhrase !== state.phrase) return false;
      if (state.scope && (row.scope || "").toLowerCase() !== state.scope) return false;
      if (state.search && !row.search_blob.includes(state.search)) return false;
      return true;
    });
  }

  function applySort(rows, columns) {
    const defaultKey = state.sortKey || columns[0].key;
    const dir = state.sortDir === "asc" ? 1 : -1;
    return rows.slice().sort((a, b) => compareValues(a[defaultKey], b[defaultKey]) * dir);
  }

  function compareValues(a, b) {
    const na = parseNumber(a);
    const nb = parseNumber(b);
    if (na !== null && nb !== null) return na - nb;
    return String(a || "").localeCompare(String(b || ""));
  }

  function renderHeader(columns) {
    const cells = columns.map((column) => (
      `<th data-key="${escapeHtml(column.key)}" class="${column.className || ""}">${escapeHtml(column.label)}</th>`
    ));
    els.tableHead.innerHTML = `<tr>${cells.join("")}</tr>`;
    els.tableHead.querySelectorAll("th").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.key;
        if (state.sortKey === key) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = key;
          state.sortDir = "desc";
        }
        render();
      });
    });
  }

  function renderBody(columns, rows, emptyMessage) {
    if (!rows.length) {
      els.tableBody.innerHTML = `<tr><td class="empty" colspan="${columns.length}">${escapeHtml(emptyMessage)}</td></tr>`;
      return;
    }

    els.tableBody.innerHTML = rows.map((row) => {
      const cells = columns.map((column) => (
        `<td class="${column.className || ""}">${formatCell(row[column.key], column, row)}</td>`
      ));
      return `<tr>${cells.join("")}</tr>`;
    }).join("");
  }

  function formatCell(value, column, row) {
    if (column.badge) {
      const number = parseNumber(value);
      const tone = number > 0 ? "good" : number < 0 ? "bad" : "";
      return pill(formatPercent(value, column), tone);
    }
    if (column.type === "pct") return formatPercent(value);
    if (column.type === "signed") return formatSigned(value);
    if (column.type === "decimal") return formatDecimal(value);
    if (column.type === "money") return formatMoney(value);
    if (column.type === "pill") return pill(value);
    if (column.type === "scope") return pill(value || "event", "warn");
    if (column.type === "status") return pill(value, value === "active" ? "good" : "");
    if (column.type === "review") return pill(value === "yes" ? "review" : "clean", value === "yes" ? "warn" : "good");
    if (column.type === "question") return `<span class="question" title="${escapeHtml(value || "")}">${escapeHtml(value || "")}</span>`;
    if (value === null || value === undefined || value === "") return '<span class="muted">--</span>';
    if (column.key === "rounds" || column.key === "fight_count" || column.key === "test_rows") return formatInteger(value);
    return escapeHtml(String(value));
  }

  function pill(value, tone) {
    if (value === null || value === undefined || value === "") return '<span class="muted">--</span>';
    return `<span class="pill ${tone || ""}">${escapeHtml(String(value))}</span>`;
  }

  function parseNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function formatPercent(value, column = {}) {
    const number = parseNumber(value);
    if (number === null) return '<span class="muted">--</span>';
    const sign = column.signed && number > 0 ? "+" : "";
    return `${sign}${(number * 100).toFixed(Math.abs(number) < 0.01 ? 2 : 1)}%`;
  }

  function formatSigned(value) {
    const number = parseNumber(value);
    if (number === null) return '<span class="muted">--</span>';
    const sign = number > 0 ? "+" : "";
    return `${sign}${number.toFixed(4)}`;
  }

  function formatDecimal(value) {
    const number = parseNumber(value);
    if (number === null) return '<span class="muted">--</span>';
    return number.toFixed(3);
  }

  function formatMoney(value) {
    const number = parseNumber(value);
    if (number === null) return '<span class="muted">--</span>';
    return number.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function formatInteger(value) {
    const number = parseNumber(value);
    if (number === null) return "0";
    return number.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  init();
})();
