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
    expanded: new Set(),
  };

  const els = {
    countsLine: document.getElementById("countsLine"),
    status: document.getElementById("dataStatus"),
    refreshButton: document.getElementById("refreshButton"),
    cardNav: document.getElementById("cardNav"),
    fightHeader: document.getElementById("fightHeader"),
    phraseFilter: document.getElementById("phraseFilter"),
    searchInput: document.getElementById("searchInput"),
    tableMeta: document.getElementById("tableMeta"),
    tableHead: document.getElementById("tableHead"),
    tableBody: document.getElementById("tableBody"),
    healthSummary: document.getElementById("healthSummary"),
    healthGrid: document.getElementById("healthGrid"),
    trackingSummary: document.getElementById("trackingSummary"),
    trackingCards: document.getElementById("trackingCards"),
    trackingBody: document.getElementById("trackingBody"),
  };

  function init() {
    if (!data) {
      els.status.textContent = "No local data yet. Run ./start_live_dashboard.command";
      els.tableBody.innerHTML = '<tr><td class="empty">No local dashboard data found.</td></tr>';
      return;
    }
    chooseDefaultCard();
    populatePhraseFilter();
    setupRefreshButton();
    bindEvents();
    renderAll();
    scheduleAutoUpdate();
  }

  function renderAll() {
    renderTopline();
    renderNav();
    renderFightHeader();
    renderTable();
    renderHealth();
    renderTracking();
  }

  /* ---------- data access ---------- */

  function getRows() { return data.kalshi || []; }
  function getCards() { return data.kalshi_cards || []; }

  function getSelectedCard() {
    return getCards().find((card) => card.card_id === state.selectedCard) || null;
  }

  function getSelectedFight() {
    const card = getSelectedCard();
    if (!card || !state.selectedEvent) return null;
    return (card.fights || []).find((fight) => fight.event_ticker === state.selectedEvent) || null;
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
    if (state.selectedEvent && (!card || !(card.fights || []).some((f) => f.event_ticker === state.selectedEvent))) {
      state.selectedEvent = "";
    }
  }

  /* ---------- server plumbing ---------- */

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

  async function manualRefresh() {
    if (!isServerMode() || state.refreshing) return;
    state.refreshing = true;
    setRefreshButton("Updating…");
    try {
      const response = await fetch(`/api/refresh?ts=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`refresh failed: ${response.status}`);
      const payload = await response.json().catch(() => null);
      if (payload && payload.ok === false) {
        els.status.textContent = payload.error || "Not ready yet; try again in a minute.";
        return;
      }
      await loadFreshData();
      chooseDefaultCard();
      populatePhraseFilter();
      renderAll();
    } catch (error) {
      els.status.textContent = `Refresh failed. ${error.message || error}`;
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
      if (state.loadingData) { resolve(); return; }
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

  function scheduleAutoUpdate() {
    const seconds = Number((data.summary || {}).kalshi_poll_seconds || 0);
    if (!isServerMode() || seconds <= 0) return;
    window.setInterval(async () => {
      if (state.refreshing || state.loadingData) return;
      try {
        await loadFreshData();
        chooseDefaultCard();
        populatePhraseFilter();
        renderAll();
      } catch (error) {
        els.status.textContent = `Auto-update failed. ${error.message || error}`;
      }
    }, Math.max(5, seconds) * 1000);
  }

  /* ---------- events ---------- */

  function bindEvents() {
    els.phraseFilter.addEventListener("change", () => {
      state.phrase = els.phraseFilter.value;
      renderTable();
    });
    els.searchInput.addEventListener("input", () => {
      state.search = els.searchInput.value.trim().toLowerCase();
      renderTable();
    });
    if (els.refreshButton) els.refreshButton.addEventListener("click", manualRefresh);
  }

  function populatePhraseFilter() {
    const current = state.phrase;
    els.phraseFilter.innerHTML = '<option value="">All phrases</option>';
    const phrases = new Map();
    getRows().forEach((row) => {
      if (row.phrase) phrases.set(String(row.phrase).toLowerCase(), row.phrase);
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
    if (current && els.phraseFilter.value !== current) state.phrase = "";
  }

  /* ---------- top line ---------- */

  function renderTopline() {
    const summary = data.summary || {};
    const gapCount = parseNumber(summary.kalshi_gap_blocked_count) || 0;
    els.countsLine.textContent = [
      `${formatInteger(summary.kalshi_card_count)} card${plural(summary.kalshi_card_count)}`,
      `${formatInteger(summary.kalshi_event_count)} fights`,
      `${formatInteger(summary.kalshi_priced_count)} phrase books`,
      `${formatInteger(summary.kalshi_watch_count)} watch row${plural(summary.kalshi_watch_count)}`,
      gapCount ? `${formatInteger(gapCount)} big gap${plural(gapCount)}` : "",
    ].filter(Boolean).join(" · ");

    const ts = summary.kalshi_snapshot_timestamp;
    const stale = ts ? isStale(ts, summary.kalshi_poll_seconds) : false;
    const when = ts ? `${formatTimestamp(ts)} (${snapshotAge(ts)})` : "not refreshed yet";
    const polling = summary.kalshi_poll_seconds > 0
      ? ` · auto-updates every ${formatInteger(summary.kalshi_poll_seconds)}s`
      : "";
    els.status.innerHTML = `${stale ? '<span class="stale">Stale</span> · ' : ""}updated ${escapeHtml(when)} · read-only${polling}`;
  }

  /* ---------- sidebar nav ---------- */

  function renderNav() {
    const cards = getCards();
    if (!cards.length) {
      els.cardNav.innerHTML = '<div class="nav-empty">No Kalshi UFC mention markets are open right now. This page checks again automatically.</div>';
      return;
    }

    els.cardNav.innerHTML = cards.map((card) => {
      const current = card.card_id === state.selectedCard;
      const watch = Number(card.watch_count || 0);
      const sub = [
        `${formatInteger(card.tradable_fight_count)} fight${plural(card.tradable_fight_count)} with odds`,
        `${formatInteger(card.phrase_count)} markets`,
        watch ? `${formatInteger(watch)} watch` : "",
      ].filter(Boolean).join(" · ");
      const fights = current ? navFights(card) : "";
      return `<div class="nav-card ${current ? "is-current" : ""}">
        <button class="nav-card-head" type="button" data-nav-card="${escapeHtml(card.card_id)}">
          <span class="nav-date">${escapeHtml(formatDate(card.event_date) || "Date TBD")}</span>
          <h2>${escapeHtml(card.card_title || "UFC card")}</h2>
          <span class="nav-sub">${escapeHtml(sub)}</span>
        </button>
        ${fights}
      </div>`;
    }).join("");

    els.cardNav.querySelectorAll("[data-nav-card]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedCard = button.dataset.navCard || "";
        state.selectedEvent = "";
        renderNav();
        renderFightHeader();
        renderTable();
      });
    });
    els.cardNav.querySelectorAll("[data-nav-fight]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedEvent = button.dataset.navFight || "";
        renderNav();
        renderFightHeader();
        renderTable();
      });
    });
  }

  function navFights(card) {
    const fights = card.fights || [];
    if (!fights.length) {
      return '<div class="nav-fights"><div class="nav-empty">Kalshi has not listed fights for this card yet.</div></div>';
    }
    const allSelected = !state.selectedEvent;
    const items = [
      `<button class="nav-fight ${allSelected ? "is-selected" : ""}" type="button" data-nav-fight="">
        <strong>All fights</strong>
        <span class="nav-tag">${formatInteger(card.phrase_count)}</span>
      </button>`,
    ];
    fights.forEach((fight) => {
      const selected = state.selectedEvent === fight.event_ticker;
      const tbd = fight.odds_status === "tbd";
      const watch = Number(fight.watch_count || 0);
      const tag = tbd ? "TBD" : watch ? `${formatInteger(watch)} watch` : formatInteger(fight.priced_count);
      items.push(`<button class="nav-fight ${selected ? "is-selected" : ""} ${tbd ? "is-tbd" : ""}" type="button" data-nav-fight="${escapeHtml(fight.event_ticker)}">
        <strong>${escapeHtml(fight.matchup || "TBD fight")}</strong>
        <span class="nav-tag ${watch ? "watch" : ""}">${escapeHtml(tag)}</span>
      </button>`);
    });
    return `<div class="nav-fights">${items.join("")}</div>`;
  }

  /* ---------- fight header ---------- */

  function renderFightHeader() {
    const card = getSelectedCard();
    const fight = getSelectedFight();

    if (!card) {
      els.fightHeader.innerHTML = "<h2>No cards yet</h2><p class=\"fight-sub\">When Kalshi lists UFC mention markets, they show up here on their own.</p>";
      return;
    }

    if (fight) {
      const tbd = fight.odds_status === "tbd";
      const watch = Number(fight.watch_count || 0);
      const bits = tbd
        ? ["Kalshi lists this fight, but mention odds are not posted yet."]
        : [
          `${formatInteger(fight.priced_count)} phrase markets with live prices`,
          `${formatInteger(fight.model_ready_count)} with a fight-level model number`,
          watch ? `<span class="watch-note">${formatInteger(watch)} watch row${plural(watch)}</span>` : "no watch rows right now",
        ];
      els.fightHeader.innerHTML = `
        <p class="crumb">${escapeHtml(card.card_title || "UFC card")} · ${escapeHtml(formatDate(fight.event_date) || "date TBD")}</p>
        <h2>${escapeHtml(fight.matchup || "TBD fight")}</h2>
        <p class="fight-sub">${bits.join(" · ")}</p>`;
      return;
    }

    const watch = Number(card.watch_count || 0);
    els.fightHeader.innerHTML = `
      <p class="crumb">${escapeHtml(formatDate(card.event_date) || "Date TBD")}</p>
      <h2>${escapeHtml(card.card_title || "UFC card")}</h2>
      <p class="fight-sub">${formatInteger(card.fight_count)} fight${plural(card.fight_count)} listed · ${formatInteger(card.phrase_count)} phrase markets · ${watch ? `<span class="watch-note">${formatInteger(watch)} watch row${plural(watch)}</span>` : "no watch rows right now"}</p>`;
  }

  /* ---------- market table ---------- */

  function activeColumns() {
    const cols = [
      { key: "call", label: "Call", type: "signal" },
      { key: "phrase", label: "Phrase", type: "phrase" },
      { key: "model_probability", label: "Our %", type: "pct", className: "num" },
      { key: "yes_ask", label: "YES price", type: "pct", className: "num" },
      { key: "no_ask", label: "NO price", type: "pct", className: "num" },
      { key: "side", label: "Side", type: "side" },
      { key: "edge", label: "Edge", type: "pct", className: "num", badge: true, signed: true },
    ];
    if (!state.selectedEvent) {
      cols.splice(2, 0, { key: "matchup", label: "Fight", type: "fight" });
    }
    return cols;
  }

  function renderTable() {
    const columns = activeColumns();
    let rows = getRows().map(deriveRow);
    rows = applyFilters(rows);
    rows = applySort(rows);
    els.tableMeta.textContent = `${formatInteger(rows.length)} market${plural(rows.length)} · WATCH clears the entry bar, LEAN is positive but under it · click a row for the why`;
    renderHeader(columns);
    renderBody(columns, rows);
  }

  function deriveRow(row) {
    const out = { ...row };
    const f1 = row.fighter_1 || "";
    const f2 = row.fighter_2 || "";
    out.matchup = f1 && f2 ? `${f1} vs ${f2}` : row.event_title || row.event_ticker || "";
    out.call = callLabel(row);
    out.reason = reasonForRow(row);
    out.search_blob = [out.call, out.phrase, out.matchup, out.event_date, out.ticker, out.reason]
      .join(" ").toLowerCase();
    return out;
  }

  function missingPrices(row) {
    return parseNumber(row.yes_ask) === null || parseNumber(row.no_ask) === null;
  }

  function callLabel(row) {
    if (row.status === "error") return "ERROR";
    if (missingPrices(row)) return "NO PRICES";
    if (row.probability_source !== "fight_context_model") return "NO MODEL";
    const side = String(row.side || "").toUpperCase();
    if (row.watch) return side ? `WATCH ${side}` : "WATCH";
    if (row.block_reason === "big_gap") return "BIG GAP";
    if (parseNumber(row.edge) > 0 && side) return `LEAN ${side}`;
    return "PASS";
  }

  function reasonForRow(row) {
    if (row.status === "error") return row.error || "This market could not be priced.";
    if (missingPrices(row)) {
      return "No live YES/NO buy price is posted yet, so there is nothing to compare against.";
    }
    if (row.probability_source !== "fight_context_model") {
      return "No fight-level model number was available here, so there is only a rough history average. Rows like this never become watches.";
    }

    const model = formatPlainPercent(row.model_probability);
    const side = String(row.side || "").toUpperCase();
    const sidePrice = formatPlainPercent(row.side_price);
    const edge = formatPlainPercent(row.edge, true);
    const hurdle = formatPlainPercent(row.hurdle);
    const cap = formatPlainPercent(row.edge_cap);
    const thin = row.data_risk ? " Fighter history is thin here, so the bar was raised — it cleared anyway, but trust it less." : "";

    if (row.watch) {
      return `Our model thinks YES is ${model}. Buying ${side} costs ${sidePrice}, so ${side} has ${edge} of edge. The entry bar is ${hurdle} and the cap is ${cap}, so this clears and becomes WATCH ${side}.${thin}`;
    }
    if (row.block_reason === "big_gap") {
      return `Our model thinks YES is ${model} — a ${edge} disagreement with the market. On settled cards, gaps over ${cap} were almost always the model's mistake, not the market's, so this is flagged instead of traded.`;
    }
    if (row.block_reason === "low_trust") {
      return `Our model thinks YES is ${model} and ${side} has ${edge} of edge, but ${row.trust_note || "this phrase group has not shown real skill on old fights"}.`;
    }
    if (parseNumber(row.edge) <= 0) {
      return `Our model thinks YES is ${model}. Neither side is cheap compared to that, so there is nothing to do here.`;
    }
    return `Our model thinks YES is ${model}. ${side} at ${sidePrice} has ${edge} of edge — positive, but under the ${hurdle} entry bar${row.data_risk ? " (raised because fighter history is thin)" : ""}, so it is only a lean.`;
  }

  function applyFilters(rows) {
    return rows.filter((row) => {
      if (state.selectedEvent) {
        if (row.event_ticker !== state.selectedEvent) return false;
      } else if (state.selectedCard) {
        const card = getSelectedCard();
        const tickers = new Set((card ? card.fights || [] : []).map((f) => f.event_ticker));
        if (tickers.size && !tickers.has(row.event_ticker)) return false;
      }
      const rowPhrase = String(row.phrase || "").toLowerCase();
      if (state.phrase && rowPhrase !== state.phrase) return false;
      if (state.search && !row.search_blob.includes(state.search)) return false;
      return true;
    });
  }

  function applySort(rows) {
    if (!state.sortKey) return rows.slice().sort(defaultCompare);
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

  function renderHeader(columns) {
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
        renderTable();
      });
    });
  }

  function renderBody(columns, rows) {
    if (!rows.length) {
      const fight = getSelectedFight();
      const message = fight && fight.odds_status === "tbd"
        ? "Kalshi lists this fight, but the mention odds are not posted yet. It will fill in on its own."
        : "No markets match those filters.";
      els.tableBody.innerHTML = `<tr><td class="empty" colspan="${columns.length}">${escapeHtml(message)}</td></tr>`;
      return;
    }

    els.tableBody.innerHTML = rows.map((row) => {
      const key = String(row.ticker || "");
      const open = key && state.expanded.has(key);
      const rowClass = [
        row.watch ? "is-watch" : (row.call === "NO PRICES" || row.call === "NO MODEL") ? "is-quiet" : "",
        "is-expandable",
        open ? "is-open" : "",
      ].filter(Boolean).join(" ");
      const cells = columns.map((column) => (
        `<td class="${column.className || ""}">${formatCell(row[column.key], column, row)}</td>`
      )).join("");
      const detail = open
        ? `<tr class="detail-row"><td colspan="${columns.length}">${auditDetail(row)}</td></tr>`
        : "";
      return `<tr class="${rowClass}" data-expand="${escapeHtml(key)}">${cells}</tr>${detail}`;
    }).join("");

    els.tableBody.querySelectorAll("tr[data-expand]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const key = tr.dataset.expand;
        if (!key) return;
        if (state.expanded.has(key)) state.expanded.delete(key);
        else state.expanded.add(key);
        renderTable();
      });
    });
  }

  function auditDetail(row) {
    const lines = [];
    const fightModel = row.probability_source === "fight_context_model";
    const model = formatPlainPercent(row.model_probability);
    const noChance = parseNumber(row.model_probability) === null
      ? "--"
      : formatPlainPercent(1 - parseNumber(row.model_probability));

    if (fightModel) {
      lines.push(["Number source", "Fight-specific model, trained on old fights and scored for this exact matchup and phrase."]);
    } else {
      lines.push(["Number source", "Fallback only: fighter history average. No fight-specific model number, so this row can never be a watch."]);
    }
    if (row.context_note) lines.push(["Model note", String(row.context_note)]);

    const what = [row.phrase, row.forms && row.forms !== row.phrase ? `counts any of: ${row.forms}` : ""].filter(Boolean).join(" — ");
    lines.push(["What it prices", `"${what}" said during ${row.matchup || "this fight"}${row.event_date ? ` on ${formatDate(row.event_date)}` : ""}.`]);

    if (fightModel && parseNumber(row.context_training_rows) !== null) {
      const validation = parseNumber(row.context_validation_rows) !== null
        ? `, checked on ${formatInteger(row.context_validation_rows)} held-out fights`
        : "";
      lines.push(["Trained from", `${formatInteger(row.context_training_rows)} older fights with known transcripts${validation}.`]);
    }

    if (parseNumber(row.fighter_fights) !== null) {
      const leagueBit = parseNumber(row.league_rate) !== null
        ? `; the league average is ${formatPlainPercent(row.league_rate)}`
        : "";
      lines.push(["Fighter history", `These fighters' past fights said it ${formatInteger(row.fighter_hits)} of ${formatInteger(row.fighter_fights)} times${leagueBit}.`]);
    }

    if (row.data_risk) {
      lines.push(["Thin data", `Yes. Fighter history is small, so this row must clear an extra ${formatPlainPercent(row.data_buffer)} of edge before it can be a watch.`]);
    }

    if (row.trust_ok === false) {
      lines.push(["Phrase trust", `Low. ${row.trust_note || "This phrase group has not shown real skill in the old-fight prediction test."} It can lean but never watch.`]);
    } else if (row.trust_note) {
      lines.push(["Phrase trust", row.trust_note]);
    }

    if (parseNumber(row.yes_ask) !== null || parseNumber(row.no_ask) !== null) {
      lines.push(["Prices", `Model says YES ${model} / NO ${noChance}. Buying YES costs ${formatPlainPercent(row.yes_ask)}, buying NO costs ${formatPlainPercent(row.no_ask)}.`]);
      const side = String(row.side || "").toUpperCase();
      if (side) {
        const sideEdge = side === "YES" ? row.yes_edge : row.no_edge;
        const otherEdge = side === "YES" ? row.no_edge : row.yes_edge;
        lines.push(["Side picked", `${side}, because its edge (${formatPlainPercent(sideEdge, true)}) beats the other side (${formatPlainPercent(otherEdge, true)}).`]);
      }
      if (parseNumber(row.hurdle) !== null) {
        const parts = [
          parseNumber(row.spread) !== null ? `spread ${formatPlainPercent(row.spread)}` : "",
          parseNumber(row.fee_buffer) !== null ? `fee buffer ${formatPlainPercent(row.fee_buffer)}` : "",
          parseNumber(row.data_buffer) ? `thin-data buffer ${formatPlainPercent(row.data_buffer)}` : "",
        ].filter(Boolean).join(" + ");
        const cap = parseNumber(row.edge_cap) !== null
          ? ` Edge must also stay at or under the ${formatPlainPercent(row.edge_cap)} cap — bigger gaps were usually model mistakes on settled cards.`
          : "";
        const verdict = row.watch
          ? "This one clears, so it is a watch row."
          : row.block_reason === "big_gap"
            ? "This edge is over the cap, so it is flagged BIG GAP instead."
            : row.block_reason === "low_trust"
              ? "The edge clears the bar, but the phrase group is low-trust, so it stays a lean."
              : "The edge does not clear it, so this is not a watch row.";
        lines.push(["Entry bar", `${parts ? `${parts} → ` : ""}needs more than ${formatPlainPercent(row.hurdle)} of edge.${cap} Current edge is ${formatPlainPercent(row.edge, true)}. ${verdict}`]);
      }
    }

    return `<div class="audit">
      <p class="audit-reason">${escapeHtml(row.reason || "")}</p>
      <p class="audit-title">How this number was made</p>
      ${lines.map(([label, text]) => `<div class="audit-line"><span>${escapeHtml(label)}</span><p>${escapeHtml(text)}</p></div>`).join("")}
    </div>`;
  }

  /* ---------- cell formatting ---------- */

  function formatCell(value, column, row) {
    if (column.badge) {
      const number = parseNumber(value);
      if (number === null) return '<span class="muted">--</span>';
      const tone = number > 0 ? "good" : number < 0 ? "bad" : "";
      return pill(formatPercent(value, column), tone);
    }
    if (column.type === "pct") return formatPercent(value, column);
    if (column.type === "phrase") return pill(value);
    if (column.type === "signal") {
      let chips = "";
      if (row.status !== "error" && !missingPrices(row)) {
        if (row.data_risk) {
          chips += ' <span class="chip-thin" title="Fighter history is small; this row needs extra edge">thin data</span>';
        }
        if (row.trust_ok === false) {
          chips += ' <span class="chip-thin" title="This phrase group has not shown real skill in the prediction test">low trust</span>';
        }
      }
      return signalPill(value) + chips;
    }
    if (column.type === "side") return sidePill(value);
    if (column.type === "fight") return fightCell(row);
    if (value === null || value === undefined || value === "") return '<span class="muted">--</span>';
    return escapeHtml(String(value));
  }

  function signalPill(value) {
    const label = String(value || "");
    const tone = label.startsWith("WATCH") ? "warn"
      : label === "ERROR" ? "bad"
        : label === "BIG GAP" ? "gap"
          : label.startsWith("LEAN") ? "quiet-warn"
            : "";
    return pill(label, tone);
  }

  function sidePill(value) {
    const label = String(value || "").toUpperCase();
    return label ? pill(label, label === "YES" ? "good" : "quiet-warn") : '<span class="muted">--</span>';
  }

  function fightCell(row) {
    return `<div class="fight-cell"><strong>${escapeHtml(row.matchup || "--")}</strong><span>${escapeHtml(formatDate(row.event_date) || "")}</span></div>`;
  }

  function pill(value, tone) {
    if (value === null || value === undefined || value === "") return '<span class="muted">--</span>';
    return `<span class="pill ${tone || ""}">${escapeHtml(String(value))}</span>`;
  }

  /* ---------- model health ---------- */

  function renderHealth() {
    if (!els.healthGrid) return;
    const health = data.model_health || {};
    const prediction = health.prediction || {};
    const groups = health.groups || [];
    const pl = health.pl || {};

    if (!prediction.prediction_rows && !groups.length) {
      els.healthSummary.textContent = "no backtest outputs yet";
      els.healthGrid.innerHTML = '<article class="health-block"><p class="health-note">Run scripts/model/backtest_context_model.py and scripts/model/backtest_pl.py to fill this in.</p></article>';
      return;
    }

    const settledThrough = pl.latest_settled_event_date ? formatDate(pl.latest_settled_event_date) : "";
    const enough = pl.claim_status === "sufficient_sample";
    const plBit = pl.available
      ? `Money test: <span class="${toneClass(pl.official_pnl)}">${formatMoney(pl.official_pnl)}</span> on ${formatInteger(pl.official_trades)} settled trades${settledThrough ? ` (through ${settledThrough})` : ""} — ${enough ? "enough sample to review" : "still too small to trust"}`
      : "Money test: no settled markets yet";
    els.healthSummary.innerHTML = `Prediction test: ${formatInteger(prediction.groups_beating_base)} of ${formatInteger(prediction.measured_groups)} phrase groups pass · ${plBit}`;

    const strongBit = (prediction.strongest || []).length
      ? `<p class="health-note">Strongest: ${escapeHtml((prediction.strongest || []).join(", "))}. Weakest: ${escapeHtml((prediction.weakest || []).join(", "))} — the weakest groups can lean but never watch.</p>`
      : "";
    const weakest = prediction.weakest_phrase
      ? `<p class="health-note">Bottom of the table: <strong>${escapeHtml(prediction.weakest_phrase)}</strong> (${formatSignedDecimal(prediction.weakest_improvement)} vs baseline${parseNumber(prediction.weakest_improvement) <= 0 ? " — fails it" : ""}).</p>`
      : "";

    const max = Math.max(...groups.map((g) => Math.abs(parseNumber(g.log_loss_improvement) || 0)), 0.0001);
    const groupBars = groups.length
      ? groups.map((group) => {
        const value = parseNumber(group.log_loss_improvement);
        const width = Math.max(2, Math.abs(value || 0) / max * 100);
        return `<div class="bar-row">
          <div class="bar-label"><span title="${escapeHtml(group.phrase)}">${escapeHtml(group.phrase)}</span><strong>${formatSignedDecimal(value)}</strong></div>
          <div class="bar-track"><span class="bar-fill ${group.beats_base ? "good" : "bad"}" style="width:${width}%"></span></div>
        </div>`;
      }).join("")
      : '<p class="health-note">No per-phrase results yet.</p>';

    const officialTrades = parseNumber(pl.official_trades) || 0;
    const needed = parseNumber(pl.minimum_trades_for_claim) || 30;
    const ruleBit = parseNumber(pl.current_rule_trades) !== null
      ? `<p class="health-note">The entry rule was tightened after this card (edge cap + phrase trust). Replayed on the same snapshots, today's rule takes ${formatInteger(pl.current_rule_trades)} trades, ${formatInteger(pl.current_rule_wins)} wins, <span class="${toneClass(pl.current_rule_pnl)}">${formatMoney(pl.current_rule_pnl)}</span>. That number is in-sample — the next cards are the real test.</p>`
      : "";
    const plBlock = pl.available
      ? `
        <p class="health-big ${toneClass(pl.official_pnl)}">${formatMoney(pl.official_pnl)}<span>watch-rule paper P/L: ${formatInteger(officialTrades)} trades, ${formatInteger(pl.official_wins)} wins, $${formatDecimal2(pl.official_staked)} staked</span></p>
        <p class="health-note">Looser leans (positive edge, below the bar): ${formatInteger(pl.lean_trades)} trades, ${formatInteger(pl.lean_wins)} wins, <span class="${toneClass(pl.lean_pnl)}">${formatMoney(pl.lean_pnl)}</span>.</p>
        ${ruleBit}
        <p class="health-note">Everything here is from cards that already happened${settledThrough ? ` (latest: ${settledThrough})` : ""} — ${formatInteger(pl.markets_with_results)} settled markets, replayed from recorded live snapshots against final Kalshi results. Upcoming cards settle in on their own.</p>
        <p class="health-note">${formatInteger(officialTrades)} of the ${formatInteger(needed)} settled trades needed before this means anything.</p>`
      : '<p class="health-note">No settled markets replayed yet. This fills in by itself after a tracked card finishes.</p>';

    els.healthGrid.innerHTML = `
      <article class="health-block">
        <p class="health-kicker">Prediction test (old fights)</p>
        <p class="health-big">${formatInteger(prediction.groups_beating_base)}<span> of ${formatInteger(prediction.measured_groups)} phrase groups beat the simple average</span></p>
        <p class="health-note">${formatInteger(prediction.prediction_rows)} old fight predictions scored across ${formatInteger(prediction.folds)} time-ordered folds. This checks guessing quality only, not profit.</p>
        ${strongBit}
      </article>
      <article class="health-block">
        <p class="health-kicker">By phrase group (higher is better)</p>
        <div class="bar-chart">${groupBars}</div>
      </article>
      <article class="health-block">
        <p class="health-kicker">Money test</p>
        <p class="health-warn">${enough ? "Enough sample to review" : "Still too small to trust"}</p>
        ${plBlock}
      </article>`;
  }

  /* ---------- paper tracking ---------- */

  function renderTracking() {
    const cards = data.tracking_cards || [];
    const positions = data.tracking_positions || [];

    if (!cards.length) {
      els.trackingSummary.textContent = "nothing tracked yet";
      els.trackingCards.innerHTML = "";
      els.trackingBody.innerHTML = '<tr><td class="tracking-empty" colspan="7">No paper tracking yet. Start the dashboard with PAPER_CARD="Card name" and watch rows get logged as pretend one-contract entries. No real money is ever used.</td></tr>';
      return;
    }

    const summary = data.summary || {};
    els.trackingSummary.innerHTML = [
      `${formatInteger(summary.tracking_card_count)} card${plural(summary.tracking_card_count)}`,
      `${formatInteger(summary.tracking_official_trade_count)} paper trades`,
      `${formatInteger(summary.tracking_pending_count)} pending`,
      `P/L <span class="${toneClass(summary.tracking_official_pnl)}">${formatMoney(summary.tracking_official_pnl)}</span>`,
    ].join(" · ");

    els.trackingCards.innerHTML = cards.map((card) => {
      const officialPnl = parseNumber(card.official_pnl);
      const leanPnl = parseNumber(card.lean_pnl);
      return `<article class="tracking-card">
        <p class="tracking-date">${escapeHtml(formatDate(card.settled_at ? String(card.settled_at).slice(0, 10) : "") || "in progress")}</p>
        <h3>${escapeHtml(card.label || card.card)}</h3>
        <div class="tracking-card-stats">
          <span><strong>${formatInteger(card.official_trades)}</strong> trades</span>
          <span><strong>${formatInteger(card.leans)}</strong> leans</span>
          <span><strong>${formatInteger(card.pending)}</strong> pending</span>
          <span class="${pnlClass(officialPnl)}"><strong>${formatMoney(officialPnl)}</strong> trade P/L</span>
          <span class="${pnlClass(leanPnl)}"><strong>${formatMoney(leanPnl)}</strong> lean P/L</span>
        </div>
      </article>`;
    }).join("");

    const shown = positions.slice(0, 12);
    if (!shown.length) {
      els.trackingBody.innerHTML = '<tr><td class="tracking-empty" colspan="7">No paper entries logged yet.</td></tr>';
      return;
    }
    els.trackingBody.innerHTML = shown.map((row) => {
      const outcome = outcomeLabel(row);
      return `<tr>
        <td>${pill(trackingAction(row), row.paper_action === "trade" ? "warn" : "quiet-warn")}</td>
        <td><div class="fight-cell"><strong>${escapeHtml(row.matchup || "")}</strong><span>${escapeHtml(row.card || "")}</span></div></td>
        <td>${pill(row.phrase || "")}</td>
        <td>${sidePill(row.paper_side || row.side)}</td>
        <td class="num">${formatPlainPercent(row.paper_price)}</td>
        <td class="num">${pill(formatPlainPercent(row.edge, true), parseNumber(row.edge) > 0 ? "good" : "bad")}</td>
        <td>${pill(outcome, outcomeToneFor(row, outcome))}</td>
      </tr>`;
    }).join("");
  }

  function trackingAction(row) {
    const action = String(row.paper_action || "").toUpperCase();
    const side = String(row.paper_side || row.side || "").toUpperCase();
    return side ? `${action} ${side}` : action;
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

  /* ---------- formatters ---------- */

  function parseNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function plural(value) {
    return (parseNumber(value) || 0) === 1 ? "" : "s";
  }

  function toneClass(value) {
    const number = parseNumber(value);
    if (number > 0) return "pos";
    if (number < 0) return "neg";
    return "";
  }

  function pnlClass(value) {
    const number = parseNumber(value);
    if (number > 0) return "good-text";
    if (number < 0) return "bad-text";
    return "";
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

  function formatDecimal2(value) {
    const number = parseNumber(value);
    if (number === null) return "0.00";
    return number.toFixed(2);
  }

  function formatSignedDecimal(value) {
    const number = parseNumber(value);
    if (number === null) return "--";
    const sign = number > 0 ? "+" : "";
    const digits = number !== 0 && Math.abs(number) < 0.0005 ? 5 : 3;
    return `${sign}${number.toFixed(digits)}`;
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
    return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
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
    // Polling mode should stay fresh within a few cycles; a one-shot refresh
    // is fine for a while before it deserves the stale flag.
    const limit = expected > 0 ? Math.max(90, expected * 3) : 1800;
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
