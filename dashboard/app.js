(function () {
  let data = window.UFC_MENTION_DASHBOARD_DATA;
  const state = {
    selectedCard: "",
    selectedEvent: "",
    phrase: "",
    search: "",
    sortKey: "",
    sortDir: "desc",
    refreshing: false,
    loadingData: false,
  };

  const columns = [
    { key: "call", label: "Call", type: "signal" },
    { key: "phrase", label: "Phrase", type: "phrase" },
    { key: "matchup", label: "Fight", type: "fight" },
    { key: "model_probability", label: "Our %", type: "pct", className: "num" },
    { key: "yes_ask", label: "YES price", type: "pct", className: "num" },
    { key: "no_ask", label: "NO price", type: "pct", className: "num" },
    { key: "side", label: "Side", type: "side" },
    { key: "edge", label: "Edge", type: "pct", className: "num", badge: true, signed: true },
    { key: "reason", label: "Why", type: "reason" },
  ];

  const els = {
    status: document.getElementById("dataStatus"),
    stats: document.getElementById("stats"),
    phraseFilter: document.getElementById("phraseFilter"),
    searchInput: document.getElementById("searchInput"),
    refreshButton: document.getElementById("refreshButton"),
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
    chooseDefaultCard();
    setupRefreshButton();
    bindEvents();
    renderStats();
    renderTracking();
    render();
    scheduleAutoUpdate();
  }

  function isServerMode() {
    return window.location.protocol === "http:" || window.location.protocol === "https:";
  }

  function setupRefreshButton() {
    if (!els.refreshButton) return;
    if (!isServerMode()) {
      els.refreshButton.hidden = true;
      return;
    }
    els.refreshButton.hidden = false;
    setRefreshButton("Update now");
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

    if (els.refreshButton) {
      els.refreshButton.addEventListener("click", manualRefresh);
    }
  }

  async function manualRefresh() {
    if (!isServerMode() || state.refreshing) return;
    state.refreshing = true;
    setRefreshButton("Updating...");
    try {
      const response = await fetch(`/api/refresh?ts=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`refresh failed: ${response.status}`);
      await loadFreshData();
      renderFromData();
    } catch (error) {
      if (els.status) {
        els.status.textContent = `Refresh failed. ${error.message || error}`;
      }
    } finally {
      state.refreshing = false;
      setRefreshButton("Update now");
    }
  }

  function setRefreshButton(label) {
    if (!els.refreshButton) return;
    els.refreshButton.textContent = label;
    els.refreshButton.disabled = state.refreshing;
  }

  function loadFreshData() {
    return new Promise((resolve, reject) => {
      if (state.loadingData) {
        resolve();
        return;
      }
      state.loadingData = true;
      const script = document.createElement("script");
      script.src = `data.js?v=${Date.now()}`;
      script.onload = () => {
        data = window.UFC_MENTION_DASHBOARD_DATA;
        state.loadingData = false;
        script.remove();
        resolve();
      };
      script.onerror = () => {
        state.loadingData = false;
        script.remove();
        reject(new Error("could not load dashboard data"));
      };
      document.body.appendChild(script);
    });
  }

  function renderFromData() {
    chooseDefaultCard();
    populatePhraseFilter();
    renderStats();
    renderTracking();
    render();
  }

  function populatePhraseFilter() {
    const current = state.phrase;
    els.phraseFilter.innerHTML = '<option value="">All phrases</option>';
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
    els.phraseFilter.value = current;
    if (current && els.phraseFilter.value !== current) {
      state.phrase = "";
    }
  }

  function chooseDefaultCard() {
    const cards = getCards();
    if (!cards.length) {
      state.selectedCard = "";
      state.selectedEvent = "";
      return;
    }
    if (!state.selectedCard || !cards.some((card) => card.card_id === state.selectedCard)) {
      state.selectedCard = cards[0].card_id;
      state.selectedEvent = "";
    }
    const card = getSelectedCard();
    if (state.selectedEvent && (!card || !(card.fights || []).some((fight) => fight.event_ticker === state.selectedEvent))) {
      state.selectedEvent = "";
    }
  }

  function renderStats() {
    const summary = data.summary || {};
    const stats = [
      [summary.kalshi_card_count || 0, "cards"],
      [summary.kalshi_event_count || 0, "listed fights"],
      [summary.kalshi_priced_count || 0, "Kalshi phrases"],
      [summary.kalshi_watch_count || 0, "watch rows"],
    ];

    els.stats.innerHTML = stats.map(([value, label]) => (
      `<div class="stat"><strong>${escapeHtml(formatInteger(value))}</strong><span>${escapeHtml(label)}</span></div>`
    )).join("");

    const snapshot = summary.kalshi_snapshot_timestamp
      ? formatTimestamp(summary.kalshi_snapshot_timestamp)
      : "not refreshed yet";
    const age = summary.kalshi_snapshot_timestamp ? snapshotAge(summary.kalshi_snapshot_timestamp) : "";
    const stale = summary.kalshi_snapshot_timestamp ? isStale(summary.kalshi_snapshot_timestamp, summary.kalshi_poll_seconds) : false;
    const access = summary.kalshi_authenticated ? "authenticated read" : "public read";
    const polling = summary.kalshi_poll_seconds > 0
      ? `; auto-updates every ${formatInteger(summary.kalshi_poll_seconds)}s`
      : "";
    const paper = summary.paper_tracking_card
      ? `; paper: ${formatInteger(summary.paper_tracking_total_entries)} entries, ${formatInteger(summary.paper_tracking_pending)} pending`
      : "";
    els.status.textContent = `${stale ? "STALE " : "Updated"} ${snapshot}${age ? ` (${age})` : ""}; ${access}; read-only${polling}${paper}`;
  }

  function render() {
    chooseDefaultCard();
    let rows = getRows().map(deriveRow);
    rows = applyFilters(rows);
    rows = applySort(rows);

    els.tableTitle.textContent = selectedTableTitle();
    els.tableMeta.textContent = tableMeta(rows);
    renderFightCards();
    renderHeader();
    renderBody(rows);
  }

  function tableMeta(rows) {
    const fight = getSelectedFight();
    if (fight && fight.odds_status === "tbd") {
      return "Kalshi lists this fight event, but mention odds are not posted yet.";
    }
    const summary = data.summary || {};
    const backtestGroups = Number(summary.kalshi_backtest_measured_groups || 0);
    const backtestWins = Number(summary.kalshi_backtest_groups_beating_base || 0);
    const base = `${formatInteger(rows.length)} rows shown. YES uses the YES buy price; NO uses the NO buy price.`;
    if (!backtestGroups) return base;
    return `${base} Old-fight test: ${formatInteger(backtestWins)}/${formatInteger(backtestGroups)} phrase groups beat the simple average.`;
  }

  function selectedTableTitle() {
    const fight = getSelectedFight();
    if (fight) return fight.matchup || fight.event_title || "Selected fight";
    const card = getSelectedCard();
    if (card) return card.card_title || "Selected card";
    return "Live fight prices";
  }

  function renderFightCards() {
    const cards = getCards();
    if (!cards.length) {
      els.kalshiCards.innerHTML = '<article class="card-folder empty-card"><strong>No Kalshi UFC cards yet</strong><span>Run the Kalshi refresher and open fight events will appear here.</span></article>';
      return;
    }

    els.kalshiCards.innerHTML = cards.map((card) => {
      const selected = card.card_id === state.selectedCard;
      const bestEdge = parseNumber(card.best_edge);
      const edgeText = bestEdge === null ? "no edge yet" : `best edge ${formatPlainPercent(bestEdge, true)}`;
      const call = Number(card.watch_count || 0) > 0 ? `${formatInteger(card.watch_count)} watch` : edgeText;
      const fights = selected ? renderFightList(card) : "";
      return `<article class="card-folder ${selected ? "is-open" : ""} ${Number(card.watch_count || 0) > 0 ? "is-live" : ""}">
        <button class="card-folder-head" type="button" data-card-select="${escapeHtml(card.card_id)}">
          <div>
            <p class="eyebrow">${escapeHtml(formatDate(card.event_date) || "Upcoming")}</p>
            <h2>${escapeHtml(card.card_title || "UFC card")}</h2>
            <span>${escapeHtml(card.source_note || "From Kalshi")}</span>
          </div>
          <div class="fight-card-meta">
            <span>${formatInteger(card.tradable_fight_count)} tradable fights</span>
            <span>${formatInteger(card.phrase_count)} phrases</span>
            <strong>${escapeHtml(call)}</strong>
          </div>
        </button>
        ${fights}
      </article>`;
    }).join("");

    els.kalshiCards.querySelectorAll("[data-card-select]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedCard = button.dataset.cardSelect || "";
        state.selectedEvent = "";
        render();
      });
    });
    els.kalshiCards.querySelectorAll("[data-fight-select]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        state.selectedCard = button.dataset.cardId || state.selectedCard;
        state.selectedEvent = button.dataset.fightSelect || "";
        render();
      });
    });
  }

  function renderFightList(card) {
    const fights = card.fights || [];
    if (!fights.length) {
      return '<div class="fight-list"><div class="fight-option is-tbd"><strong>TBD fights</strong><span>Kalshi has not listed fight-level mention events yet.</span></div></div>';
    }

    const allSelected = !state.selectedEvent;
    const allButton = `<button class="fight-option ${allSelected ? "is-selected" : ""}" type="button" data-card-id="${escapeHtml(card.card_id)}" data-fight-select="">
      <strong>All tradable fights</strong>
      <span>${formatInteger(card.phrase_count)} phrase markets on this card</span>
      <em>${formatInteger(card.watch_count)} watch rows</em>
    </button>`;

    const fightButtons = fights.map((fight) => {
      const selected = state.selectedEvent === fight.event_ticker;
      const tbd = fight.odds_status === "tbd";
      const bestEdge = parseNumber(fight.best_edge);
      const right = tbd
        ? "TBD odds"
        : Number(fight.watch_count || 0) > 0
          ? `${formatInteger(fight.watch_count)} watch`
          : bestEdge === null ? "no edge yet" : formatPlainPercent(bestEdge, true);
      return `<button class="fight-option ${selected ? "is-selected" : ""} ${tbd ? "is-tbd" : ""}" type="button" data-card-id="${escapeHtml(card.card_id)}" data-fight-select="${escapeHtml(fight.event_ticker)}">
        <strong>${escapeHtml(fight.matchup || fight.event_title || "TBD fight")}</strong>
        <span>${tbd ? "Mention markets not posted yet" : `${formatInteger(fight.priced_count)} live phrases · ${formatInteger(fight.model_ready_count)} modeled`}</span>
        <em>${escapeHtml(right)}</em>
      </button>`;
    }).join("");

    return `<div class="fight-list">${allButton}${fightButtons}</div>`;
  }

  function renderTracking() {
    const cards = data.tracking_cards || [];
    const positions = data.tracking_positions || [];
    const summary = data.summary || {};

    if (!cards.length) {
      els.trackingMeta.textContent = "No paper-tracking cards saved yet.";
      els.trackingCards.innerHTML = '<article class="tracking-card empty-card"><strong>No tracking cards yet</strong><span>Run the live dashboard with a paper card name and entries will show here.</span></article>';
      els.trackingBody.innerHTML = '<tr><td class="empty" colspan="9">No tracked rows yet.</td></tr>';
      return;
    }

    els.trackingMeta.textContent = [
      `${formatInteger(summary.tracking_card_count)} card${Number(summary.tracking_card_count) === 1 ? "" : "s"}`,
      `${formatInteger(summary.tracking_official_trade_count)} official paper trades`,
      `${formatInteger(summary.tracking_lean_count)} leans`,
      `${formatInteger(summary.tracking_outcomes_filled)} outcomes filled`,
      `${formatInteger(summary.tracking_pending_count)} pending`,
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
          <span><strong>${formatInteger(card.pending)}</strong> pending</span>
          <span class="${pnlClass(officialPnl)}"><strong>${formatMoney(officialPnl)}</strong> official P/L</span>
          <span class="${pnlClass(leanPnl)}"><strong>${formatMoney(leanPnl)}</strong> lean P/L</span>
        </div>
      </article>`;
    }).join("");

    const shown = positions.slice(0, 12);
    if (!shown.length) {
      els.trackingBody.innerHTML = '<tr><td class="empty" colspan="9">This card has no paper trades yet.</td></tr>';
      return;
    }

    els.trackingBody.innerHTML = shown.map((row) => {
      const actionTone = row.paper_action === "trade" ? "warn" : "quiet-warn";
      const outcome = outcomeLabel(row);
      const outcomeTone = outcomeToneFor(row, outcome);
      const entryTime = formatShortTimestamp(row.entered_at || row.tracked_at);
      return `<tr>
        <td>${pill(trackingAction(row), actionTone)}</td>
        <td><span class="muted">${escapeHtml(row.card || "")}</span></td>
        <td>${escapeHtml(row.matchup || "")}</td>
        <td>${pill(row.phrase || "")}</td>
        <td>${escapeHtml(entryTime || "--")}</td>
        <td>${sidePill(row.paper_side || row.side)}</td>
        <td class="num">${formatPlainPercent(row.paper_price)}</td>
        <td class="num">${pill(formatPlainPercent(row.edge, true), parseNumber(row.edge) > 0 ? "good" : "bad")}</td>
        <td>${pill(outcome, outcomeTone)}</td>
      </tr>`;
    }).join("");
  }

  function outcomeLabel(row) {
    if (row.outcome) return String(row.outcome).toUpperCase();
    if (row.resolution_status === "pending") return "PENDING";
    if (row.resolution_status === "resolved") return "RESOLVED";
    return "OPEN";
  }

  function outcomeToneFor(row, label) {
    if (row.outcome === "yes") return "good";
    if (row.outcome === "no") return "bad";
    if (label === "PENDING") return "quiet-warn";
    return "";
  }

  function getRows() {
    return data.kalshi || [];
  }

  function getCards() {
    return data.kalshi_cards || [];
  }

  function getSelectedCard() {
    return getCards().find((card) => card.card_id === state.selectedCard) || null;
  }

  function getSelectedFight() {
    const card = getSelectedCard();
    if (!card || !state.selectedEvent) return null;
    return (card.fights || []).find((fight) => fight.event_ticker === state.selectedEvent) || null;
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
    const side = String(row.side || "").toUpperCase();
    if (row.watch) return side ? `WATCH ${side}${row.data_risk ? " DATA" : ""}` : "WATCH";
    if (row.status === "error") return "ERROR";
    if (row.probability_source !== "fight_context_model") return "HISTORY ONLY";
    if (row.data_risk && parseNumber(row.edge) > 0 && side) return `DATA LEAN ${side}`;
    if (row.data_risk) return "LOW DATA";
    if (parseNumber(row.edge) > 0 && side) return `LEAN ${side}`;
    return "PASS";
  }

  function reasonForRow(row) {
    if (row.status === "error") return row.error || "This market could not be priced.";
    if (row.yes_ask === null || row.yes_ask === undefined || row.yes_ask === "" || row.no_ask === null || row.no_ask === undefined || row.no_ask === "") {
      return "No live YES/NO ask is available in the book yet.";
    }
    if (row.probability_source !== "fight_context_model") {
      return "No fight-level number was available, so this is history only and cannot be a watch row.";
    }

    const model = formatPlainPercent(row.model_probability);
    const side = String(row.side || "").toUpperCase();
    const sidePrice = formatPlainPercent(row.side_price);
    const yesEdge = formatPlainPercent(row.yes_edge, true);
    const noEdge = formatPlainPercent(row.no_edge, true);
    const edge = formatPlainPercent(row.edge, true);
    const dataBuffer = formatPlainPercent(row.data_buffer);
    const priorFights = Number(row.fighter_fights || 0);

    if (row.watch) {
      if (row.data_risk) {
        return `Data-risk watch. Our YES chance is ${model}. Best side is ${side} at ${sidePrice}, edge ${edge}. Low-data buffer added: ${dataBuffer}.`;
      }
      return `Our YES chance is ${model}. Best side is ${side} at ${sidePrice}, with edge ${edge} after the spread/fee check.`;
    }
    if (row.data_risk) {
      return `Low data: ${formatInteger(priorFights)} prior fighter fights. YES edge ${yesEdge}; NO edge ${noEdge}. Extra required edge: ${dataBuffer}.`;
    }
    if (parseNumber(row.edge) <= 0) {
      return `Our YES chance is ${model}. YES edge ${yesEdge}; NO edge ${noEdge}. No side is cheap enough.`;
    }
    return `Best side is ${side} at ${sidePrice}. Edge is ${edge}, but it does not clear the spread/fee check.`;
  }

  function applyFilters(rows) {
    return rows.filter((row) => {
      if (state.selectedEvent) {
        if (row.event_ticker !== state.selectedEvent) return false;
      } else if (state.selectedCard) {
        const card = getSelectedCard();
        const tickers = new Set((card ? card.fights || [] : []).map((fight) => fight.event_ticker));
        if (tickers.size && !tickers.has(row.event_ticker)) return false;
      }
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
      const fight = getSelectedFight();
      const message = fight && fight.odds_status === "tbd"
        ? "Kalshi has listed this fight event, but the mention market odds are not posted yet."
        : "No rows match those filters.";
      els.tableBody.innerHTML = `<tr><td class="empty" colspan="${columns.length}">${escapeHtml(message)}</td></tr>`;
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
    if (column.type === "side") return sidePill(value);
    if (column.type === "fight") return fightCell(row);
    if (column.type === "reason") return `<span class="reason" title="${escapeHtml(value || "")}">${escapeHtml(value || "")}</span>`;
    if (value === null || value === undefined || value === "") return '<span class="muted">--</span>';
    return escapeHtml(String(value));
  }

  function signalPill(value) {
    const label = String(value || "");
    const tone = label.startsWith("WATCH") ? "warn" : label === "ERROR" ? "bad" : label === "LOW DATA" || label.startsWith("DATA LEAN") ? "quiet-warn" : label.startsWith("LEAN") ? "quiet-warn" : "";
    return pill(label, tone);
  }

  function sidePill(value) {
    const label = String(value || "").toUpperCase();
    return label ? pill(label, label === "YES" ? "good" : "quiet-warn") : '<span class="muted">--</span>';
  }

  function trackingAction(row) {
    const action = String(row.paper_action || "").toUpperCase();
    const side = String(row.paper_side || row.side || "").toUpperCase();
    return side ? `${action} ${side}` : action;
  }

  function fightCell(row) {
    const detail = [formatDate(row.event_date), row.event_ticker].filter(Boolean).join(" · ");
    return `<div class="fight-cell"><strong>${escapeHtml(row.matchup || "--")}</strong>${detail ? `<span>${escapeHtml(detail)}</span>` : ""}</div>`;
  }

  function pill(value, tone) {
    if (value === null || value === undefined || value === "") return '<span class="muted">--</span>';
    return `<span class="pill ${tone || ""}">${escapeHtml(String(value))}</span>`;
  }

  function scheduleAutoUpdate() {
    const seconds = Number((data.summary || {}).kalshi_poll_seconds || 0);
    if (!isServerMode() || seconds <= 0) return;
    window.setInterval(async () => {
      if (state.refreshing || state.loadingData) return;
      try {
        await loadFreshData();
        renderFromData();
      } catch (error) {
        if (els.status) {
          els.status.textContent = `Auto-update failed. ${error.message || error}`;
        }
      }
    }, Math.max(5, seconds) * 1000);
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

  function formatShortTimestamp(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function snapshotAge(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
    if (seconds < 60) return `${seconds}s old`;
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes}m old`;
    const hours = Math.round(minutes / 60);
    return `${hours}h old`;
  }

  function isStale(value, pollSeconds) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return false;
    const ageSeconds = (Date.now() - date.getTime()) / 1000;
    const expected = Number(pollSeconds || 0);
    const limit = expected > 0 ? Math.max(90, expected * 3) : 120;
    return ageSeconds > limit;
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
