(function () {
  const data = window.UFC_MENTION_DASHBOARD_DATA;
  const state = {
    phrase: "",
    search: "",
    sortKey: "",
    sortDir: "desc",
  };

  const columns = [
    { key: "call", label: "Call", type: "signal" },
    { key: "phrase", label: "Phrase", type: "phrase" },
    { key: "matchup", label: "Fight", type: "fight" },
    { key: "model_probability", label: "Our %", type: "pct", className: "num" },
    { key: "yes_ask", label: "Kalshi", type: "pct", className: "num" },
    { key: "edge", label: "Edge", type: "pct", className: "num", badge: true, signed: true },
    { key: "reason", label: "Why", type: "reason" },
  ];

  const els = {
    status: document.getElementById("dataStatus"),
    stats: document.getElementById("stats"),
    phraseFilter: document.getElementById("phraseFilter"),
    searchInput: document.getElementById("searchInput"),
    tableTitle: document.getElementById("tableTitle"),
    tableMeta: document.getElementById("tableMeta"),
    tableHead: document.getElementById("tableHead"),
    tableBody: document.getElementById("tableBody"),
    kalshiCards: document.getElementById("kalshiCards"),
    trackingMeta: document.getElementById("trackingMeta"),
    trackingCards: document.getElementById("trackingCards"),
    trackingBody: document.getElementById("trackingBody"),
  };

  function init() {
    if (!data) {
      els.status.textContent = "Run build_dashboard_data.py to create local data.";
      els.tableBody.innerHTML = `<tr><td class="empty" colspan="${columns.length}">No local dashboard data found.</td></tr>`;
      return;
    }

    populatePhraseFilter();
    bindEvents();
    renderStats();
    renderTracking();
    render();
    scheduleReload();
  }

  function bindEvents() {
    els.phraseFilter.addEventListener("change", () => {
      state.phrase = els.phraseFilter.value;
      render();
    });

    els.searchInput.addEventListener("input", () => {
      state.search = els.searchInput.value.trim().toLowerCase();
      render();
    });
  }

  function populatePhraseFilter() {
    const phrases = new Map();
    getRows().forEach((row) => {
      if (!row.phrase) return;
      phrases.set(String(row.phrase).toLowerCase(), row.phrase);
    });

    [...phrases.entries()]
      .sort((a, b) => a[1].localeCompare(b[1]))
      .forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        els.phraseFilter.appendChild(option);
      });
  }

  function renderStats() {
    const summary = data.summary || {};
    const stats = [
      [summary.kalshi_event_count || 0, "listed fights"],
      [summary.kalshi_priced_count || 0, "Kalshi phrases"],
      [summary.kalshi_fight_model_count || 0, "fight-level rows"],
      [summary.kalshi_watch_count || 0, "watch rows"],
    ];

    els.stats.innerHTML = stats.map(([value, label]) => (
      `<div class="stat"><strong>${escapeHtml(formatInteger(value))}</strong><span>${escapeHtml(label)}</span></div>`
    )).join("");

    const snapshot = summary.kalshi_snapshot_timestamp
      ? formatTimestamp(summary.kalshi_snapshot_timestamp)
      : "not refreshed yet";
    const access = summary.kalshi_authenticated ? "authenticated read" : "public read";
    const polling = summary.kalshi_poll_seconds > 0
      ? `; refreshes every ${formatInteger(summary.kalshi_poll_seconds)}s`
      : "";
    els.status.textContent = `Updated ${snapshot}; ${access}; read-only${polling}`;
  }

  function render() {
    let rows = getRows().map(deriveRow);
    rows = applyFilters(rows);
    rows = applySort(rows);

    els.tableTitle.textContent = "Live fight prices";
    els.tableMeta.textContent = tableMeta(rows);
    renderFightCards();
    renderHeader();
    renderBody(rows);
  }

  function tableMeta(rows) {
    const summary = data.summary || {};
    const backtestGroups = Number(summary.kalshi_backtest_measured_groups || 0);
    const backtestWins = Number(summary.kalshi_backtest_groups_beating_base || 0);
    const base = `${formatInteger(rows.length)} rows shown. Fight-level model first; Kalshi price only checks the edge.`;
    if (!backtestGroups) return base;
    return `${base} Old-fight test: ${formatInteger(backtestWins)}/${formatInteger(backtestGroups)} phrase groups beat the simple average.`;
  }

  function renderFightCards() {
    const events = data.kalshi_events || [];
    if (!events.length) {
      els.kalshiCards.innerHTML = '<article class="fight-card empty-card"><strong>No listed fight markets yet</strong><span>Run the Kalshi refresher and open fight markets will appear here.</span></article>';
      return;
    }

    els.kalshiCards.innerHTML = events.map((event) => {
      const matchup = event.fighter_1 && event.fighter_2
        ? `${event.fighter_1} vs ${event.fighter_2}`
        : event.event_title || event.event_ticker || "Upcoming fight";
      const watchCount = Number(event.watch_count || 0);
      const bestEdge = parseNumber(event.best_edge);
      const edgeText = bestEdge === null ? "no edge yet" : `best edge ${formatPlainPercent(bestEdge, true)}`;
      const call = watchCount > 0 ? `${formatInteger(watchCount)} watch` : edgeText;
      return `<article class="fight-card ${watchCount > 0 ? "is-live" : ""}">
        <div>
          <p class="eyebrow">${escapeHtml(formatDate(event.event_date) || "Upcoming")}</p>
          <h2>${escapeHtml(matchup)}</h2>
        </div>
        <div class="fight-card-meta">
          <span>${formatInteger(event.priced_count)} phrases</span>
          <span>${formatInteger(event.model_ready_count)} modeled</span>
          <strong>${escapeHtml(call)}</strong>
        </div>
      </article>`;
    }).join("");
  }

  function renderTracking() {
    const cards = data.tracking_cards || [];
    const positions = data.tracking_positions || [];
    const summary = data.summary || {};

    if (!cards.length) {
      els.trackingMeta.textContent = "No paper-tracking cards saved yet.";
      els.trackingCards.innerHTML = '<article class="tracking-card empty-card"><strong>No tracking cards yet</strong><span>Run snapshot_card.py before a card and it will show here.</span></article>';
      els.trackingBody.innerHTML = '<tr><td class="empty" colspan="7">No tracked rows yet.</td></tr>';
      return;
    }

    els.trackingMeta.textContent = [
      `${formatInteger(summary.tracking_card_count)} card${Number(summary.tracking_card_count) === 1 ? "" : "s"}`,
      `${formatInteger(summary.tracking_official_trade_count)} official paper trades`,
      `${formatInteger(summary.tracking_lean_count)} leans`,
      `${formatInteger(summary.tracking_outcomes_filled)} outcomes filled`,
    ].join(" · ");

    els.trackingCards.innerHTML = cards.map((card) => {
      const officialPnl = parseNumber(card.official_pnl);
      const leanPnl = parseNumber(card.lean_pnl);
      return `<article class="tracking-card">
        <div>
          <p class="eyebrow">${escapeHtml(card.path || "local tracking")}</p>
          <h2>${escapeHtml(card.label || card.card)}</h2>
        </div>
        <div class="tracking-card-stats">
          <span><strong>${formatInteger(card.official_trades)}</strong> official</span>
          <span><strong>${formatInteger(card.leans)}</strong> leans</span>
          <span><strong>${formatInteger(card.outcomes_filled)}</strong> outcomes</span>
          <span class="${pnlClass(officialPnl)}"><strong>${formatMoney(officialPnl)}</strong> official P/L</span>
          <span class="${pnlClass(leanPnl)}"><strong>${formatMoney(leanPnl)}</strong> lean P/L</span>
        </div>
      </article>`;
    }).join("");

    const shown = positions.slice(0, 12);
    if (!shown.length) {
      els.trackingBody.innerHTML = '<tr><td class="empty" colspan="7">This card has no paper trades or leans.</td></tr>';
      return;
    }

    els.trackingBody.innerHTML = shown.map((row) => {
      const actionTone = row.paper_action === "trade" ? "warn" : "quiet-warn";
      const outcome = row.outcome ? row.outcome.toUpperCase() : "OPEN";
      const outcomeTone = row.outcome === "yes" ? "good" : row.outcome === "no" ? "bad" : "";
      return `<tr>
        <td>${pill((row.paper_action || "").toUpperCase(), actionTone)}</td>
        <td><span class="muted">${escapeHtml(row.card || "")}</span></td>
        <td>${escapeHtml(row.matchup || "")}</td>
        <td>${pill(row.phrase || "")}</td>
        <td class="num">${formatPlainPercent(row.paper_price)}</td>
        <td class="num">${pill(formatPlainPercent(row.edge, true), parseNumber(row.edge) > 0 ? "good" : "bad")}</td>
        <td>${pill(outcome, outcomeTone)}</td>
      </tr>`;
    }).join("");
  }

  function getRows() {
    return data.kalshi || [];
  }

  function deriveRow(row) {
    const out = { ...row };
    const fighter1 = row.fighter_1 || "";
    const fighter2 = row.fighter_2 || "";
    out.matchup = fighter1 && fighter2 ? `${fighter1} vs ${fighter2}` : row.event_title || row.event_ticker || "";
    out.call = callLabel(row);
    out.reason = reasonForRow(row);
    out.search_blob = [
      out.call,
      out.phrase,
      out.matchup,
      out.event_date,
      out.ticker,
      out.reason,
    ].join(" ").toLowerCase();
    return out;
  }

  function callLabel(row) {
    if (row.watch) return "WATCH";
    if (row.status === "error") return "ERROR";
    if (row.probability_source !== "fight_context_model") return "HISTORY ONLY";
    if (row.confidence_ok === false) return "LOW DATA";
    return "PASS";
  }

  function reasonForRow(row) {
    if (row.status === "error") return row.error || "This market could not be priced.";
    if (row.yes_ask === null || row.yes_ask === undefined || row.yes_ask === "") {
      return "No live YES ask is available in the book yet.";
    }
    if (row.probability_source !== "fight_context_model") {
      return "No fight-level number was available, so this is history only and cannot be a watch row.";
    }

    const model = formatPlainPercent(row.model_probability);
    const ask = formatPlainPercent(row.yes_ask);
    const edge = formatPlainPercent(row.edge, true);
    const priorFights = Number(row.fighter_fights || 0);

    if (row.watch) {
      return `Our number is ${model}, Kalshi asks ${ask}, and the edge is ${edge} after the spread/fee check.`;
    }
    if (row.confidence_ok === false) {
      return `Low data: only ${formatInteger(priorFights)} prior fighter fights matched this phrase setup, so it stays off watch.`;
    }
    if (parseNumber(row.edge) <= 0) {
      return `Kalshi asks ${ask}; our number is ${model}. Edge is ${edge}, so no play.`;
    }
    return `Edge is ${edge}, but it does not clear the spread/fee check.`;
  }

  function applyFilters(rows) {
    return rows.filter((row) => {
      const rowPhrase = String(row.phrase || "").toLowerCase();
      if (state.phrase && rowPhrase !== state.phrase) return false;
      if (state.search && !row.search_blob.includes(state.search)) return false;
      return true;
    });
  }

  function applySort(rows) {
    if (!state.sortKey) {
      return rows.slice().sort(defaultCompare);
    }
    const dir = state.sortDir === "asc" ? 1 : -1;
    return rows.slice().sort((a, b) => compareValues(a[state.sortKey], b[state.sortKey]) * dir);
  }

  function defaultCompare(a, b) {
    const watchDiff = Number(b.watch) - Number(a.watch);
    if (watchDiff) return watchDiff;
    const edgeDiff = compareNumbers(b.edge, a.edge);
    if (edgeDiff) return edgeDiff;
    return String(a.matchup || "").localeCompare(String(b.matchup || ""));
  }

  function compareNumbers(a, b) {
    const na = parseNumber(a);
    const nb = parseNumber(b);
    if (na !== null && nb !== null) return na - nb;
    if (na !== null) return 1;
    if (nb !== null) return -1;
    return 0;
  }

  function compareValues(a, b) {
    const na = parseNumber(a);
    const nb = parseNumber(b);
    if (na !== null && nb !== null) return na - nb;
    return String(a || "").localeCompare(String(b || ""));
  }

  function renderHeader() {
    els.tableHead.innerHTML = `<tr>${columns.map((column) => (
      `<th data-key="${escapeHtml(column.key)}" class="${column.className || ""}">${escapeHtml(column.label)}</th>`
    )).join("")}</tr>`;
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

  function renderBody(rows) {
    if (!rows.length) {
      els.tableBody.innerHTML = `<tr><td class="empty" colspan="${columns.length}">No rows match those filters.</td></tr>`;
      return;
    }

    els.tableBody.innerHTML = rows.map((row) => {
      const rowClass = row.watch ? "is-watch" : row.call === "LOW DATA" ? "is-low-data" : "";
      const cells = columns.map((column) => (
        `<td class="${column.className || ""}">${formatCell(row[column.key], column, row)}</td>`
      )).join("");
      return `<tr class="${rowClass}">${cells}</tr>`;
    }).join("");
  }

  function formatCell(value, column, row) {
    if (column.badge) {
      const number = parseNumber(value);
      if (number === null) return '<span class="muted">--</span>';
      const tone = number > 0 ? "good" : number < 0 ? "bad" : "";
      return pill(formatPercent(value, column), tone);
    }
    if (column.type === "pct") return formatPercent(value, column);
    if (column.type === "phrase") return pill(value);
    if (column.type === "signal") return signalPill(value);
    if (column.type === "fight") return fightCell(row);
    if (column.type === "reason") return `<span class="reason" title="${escapeHtml(value || "")}">${escapeHtml(value || "")}</span>`;
    if (value === null || value === undefined || value === "") return '<span class="muted">--</span>';
    return escapeHtml(String(value));
  }

  function signalPill(value) {
    const label = String(value || "");
    const tone = label === "WATCH" ? "warn" : label === "ERROR" ? "bad" : label === "LOW DATA" ? "quiet-warn" : "";
    return pill(label, tone);
  }

  function fightCell(row) {
    const detail = [formatDate(row.event_date), row.event_ticker].filter(Boolean).join(" · ");
    return `<div class="fight-cell"><strong>${escapeHtml(row.matchup || "--")}</strong>${detail ? `<span>${escapeHtml(detail)}</span>` : ""}</div>`;
  }

  function pill(value, tone) {
    if (value === null || value === undefined || value === "") return '<span class="muted">--</span>';
    return `<span class="pill ${tone || ""}">${escapeHtml(String(value))}</span>`;
  }

  function scheduleReload() {
    const seconds = Number((data.summary || {}).kalshi_poll_seconds || 0);
    if (seconds > 0) {
      window.setTimeout(() => window.location.reload(), Math.max(5, seconds) * 1000);
    }
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

  function formatPlainPercent(value, signed = false) {
    const number = parseNumber(value);
    if (number === null) return "--";
    const sign = signed && number > 0 ? "+" : "";
    return `${sign}${(number * 100).toFixed(Math.abs(number) < 0.01 ? 2 : 1)}%`;
  }

  function formatInteger(value) {
    const number = parseNumber(value);
    if (number === null) return "0";
    return number.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function formatMoney(value) {
    const number = parseNumber(value);
    if (number === null) return "$0.00";
    const sign = number > 0 ? "+" : number < 0 ? "-" : "";
    return `${sign}$${Math.abs(number).toFixed(2)}`;
  }

  function pnlClass(value) {
    const number = parseNumber(value);
    if (number > 0) return "good-text";
    if (number < 0) return "bad-text";
    return "";
  }

  function formatDate(value) {
    if (!value) return "";
    const date = new Date(`${value}T00:00:00`);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function formatTimestamp(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
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
