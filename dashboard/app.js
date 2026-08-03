/* Replay Timeline — signature scrub bar for UFC Mention Markets.
   window.mountTimeline(container, opts) -> { update({ frame, playing, speed }) }
   Built once via innerHTML; every later repaint mutates styles/text only. */
(function () {
  const SPEEDS = [1, 2, 4];
  const PAD_MIN = 2;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatStamp(raw) {
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw ? String(raw) : "--:--:--";
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
  }

  function mountTimeline(container, opts) {
    const frames = Math.max(1, Math.floor(Number(opts.frames) || (opts.stamps ? opts.stamps.length : 0) || 1));
    const activity = opts.activity || [];
    const markers = opts.markers || [];
    const cb = {
      onSeek: typeof opts.onSeek === "function" ? opts.onSeek : function () {},
      onPlayPause: typeof opts.onPlayPause === "function" ? opts.onPlayPause : function () {},
      onSpeed: typeof opts.onSpeed === "function" ? opts.onSpeed : function () {},
    };

    function clampFrame(frame) {
      frame = Math.round(Number(frame) || 0);
      return Math.max(0, Math.min(frame, frames - 1));
    }

    // Precompute per-frame labels once so paint() never touches Date at 60fps.
    const stampLabels = [];
    for (let i = 0; i < frames; i++) stampLabels.push(formatStamp(opts.stamps && opts.stamps[i]));

    const pad = Math.max(PAD_MIN, String(frames).length);
    const framesLabel = String(frames).padStart(pad, "0");

    const state = {
      frame: clampFrame(opts.frame),
      playing: !!opts.playing,
      speed: SPEEDS.indexOf(opts.speed) === -1 ? 1 : opts.speed,
    };

    /* ---------- build (once) ---------- */

    const bars = [];
    for (let i = 0; i < frames; i++) {
      const level = Math.max(0, Math.min(1, Number(activity[i]) || 0));
      // 8% floor so silent frames still read as tape, not gaps.
      bars.push(`<span class="rtl-bar" style="height:${(8 + level * 92).toFixed(1)}%"></span>`);
    }
    const barsHtml = bars.join("");

    const markersHtml = markers
      .filter((marker) => marker && marker.frame >= 0 && marker.frame < frames)
      .map((marker) => {
        const left = (((marker.frame + 0.5) / frames) * 100).toFixed(3);
        return `<span class="rtl-marker" style="left:${left}%" aria-hidden="true">` +
          `<span class="rtl-marker-tip">${escapeHtml(marker.label)}</span></span>`;
      })
      .join("");

    container.innerHTML = `
      <div class="rtl">
        <div class="rtl-cluster">
          <button type="button" class="rtl-btn rtl-play" data-act="play" aria-label="Play replay">
            <svg viewBox="0 0 16 16" focusable="false" aria-hidden="true">
              <path class="rtl-ic-play" d="M4.6 2.7 13.2 8 4.6 13.3z"/>
              <g class="rtl-ic-pause"><rect x="3.4" y="2.9" width="3.5" height="10.2" rx="1"/><rect x="9.1" y="2.9" width="3.5" height="10.2" rx="1"/></g>
            </svg>
          </button>
          <button type="button" class="rtl-btn rtl-speed" data-act="speed" aria-label="Playback speed"></button>
        </div>
        <div class="rtl-track" role="slider" tabindex="0" aria-label="Replay position"
             aria-orientation="horizontal" aria-valuemin="0" aria-valuemax="${frames - 1}" aria-valuenow="0">
          <div class="rtl-bars">${barsHtml}</div>
          <div class="rtl-bars rtl-bars--lit" aria-hidden="true">${barsHtml}</div>
          ${markersHtml}
          <div class="rtl-playhead" aria-hidden="true"><span class="rtl-knob"></span></div>
        </div>
        <div class="rtl-cluster rtl-cluster--right">
          <span class="rtl-timecode"></span>
          <span class="rtl-count"></span>
          <span class="rtl-badge">Replay</span>
        </div>
      </div>`;

    const root = container.querySelector(".rtl");
    const track = container.querySelector(".rtl-track");
    const litBars = container.querySelector(".rtl-bars--lit");
    const playhead = container.querySelector(".rtl-playhead");
    const playBtn = container.querySelector(".rtl-play");
    const speedBtn = container.querySelector(".rtl-speed");
    const timecode = container.querySelector(".rtl-timecode");
    const count = container.querySelector(".rtl-count");

    /* ---------- paint (style + text mutations only) ---------- */

    const painted = { frame: -1, playing: null, speed: 0 };

    function paint() {
      if (painted.frame !== state.frame) {
        const centerPct = (((state.frame + 0.5) / frames) * 100).toFixed(4);
        const litPct = (100 - ((state.frame + 1) / frames) * 100).toFixed(4);
        playhead.style.left = `${centerPct}%`;
        litBars.style.clipPath = `inset(0 ${litPct}% 0 0)`;
        timecode.textContent = stampLabels[state.frame];
        count.textContent = `${String(state.frame + 1).padStart(pad, "0")} / ${framesLabel}`;
        track.setAttribute("aria-valuenow", String(state.frame));
        track.setAttribute("aria-valuetext", `${stampLabels[state.frame]}, frame ${state.frame + 1} of ${frames}`);
        painted.frame = state.frame;
      }
      if (painted.playing !== state.playing) {
        root.classList.toggle("rtl--playing", state.playing);
        playBtn.setAttribute("aria-label", state.playing ? "Pause replay" : "Play replay");
        painted.playing = state.playing;
      }
      if (painted.speed !== state.speed) {
        speedBtn.textContent = `${state.speed}×`;
        speedBtn.setAttribute("aria-label", `Playback speed ${state.speed}x`);
        painted.speed = state.speed;
      }
    }

    /* ---------- interaction (delegated on root/track) ---------- */

    root.addEventListener("click", (event) => {
      const button = event.target.closest("[data-act]");
      if (!button || !root.contains(button)) return;
      if (button.dataset.act === "play") {
        cb.onPlayPause();
      } else if (button.dataset.act === "speed") {
        cb.onSpeed(SPEEDS[(SPEEDS.indexOf(state.speed) + 1) % SPEEDS.length]);
      }
    });

    let dragRect = null;

    function frameFromX(clientX) {
      const rect = dragRect || track.getBoundingClientRect();
      const ratio = (clientX - rect.left) / (rect.width || 1);
      return clampFrame(Math.floor(ratio * frames));
    }

    function seek(frame) {
      frame = clampFrame(frame);
      if (frame === state.frame) return;
      state.frame = frame;
      paint(); // optimistic local paint; the host's update() with the same frame is a no-op
      cb.onSeek(frame);
    }

    function endDrag() {
      dragRect = null;
      root.classList.remove("rtl--dragging");
    }

    track.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault(); // no text selection / scroll-start
      try { track.setPointerCapture(event.pointerId); } catch (err) { /* stale pointer id */ }
      track.focus({ preventScroll: true }); // arrows work right after a click; ring stays :focus-visible only
      dragRect = track.getBoundingClientRect();
      root.classList.add("rtl--dragging");
      seek(frameFromX(event.clientX));
    });
    track.addEventListener("pointermove", (event) => {
      if (dragRect) seek(frameFromX(event.clientX));
    });
    track.addEventListener("pointerup", endDrag);
    track.addEventListener("pointercancel", endDrag);

    track.addEventListener("keydown", (event) => {
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        cb.onPlayPause();
        return;
      }
      const step = event.shiftKey ? 10 : 1;
      let next = null;
      if (event.key === "ArrowLeft") next = state.frame - step;
      else if (event.key === "ArrowRight") next = state.frame + step;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = frames - 1;
      if (next === null) return;
      event.preventDefault();
      seek(next);
    });

    paint();

    return {
      update(next) {
        if (!next) return;
        if (next.frame !== undefined) state.frame = clampFrame(next.frame);
        if (next.playing !== undefined) state.playing = !!next.playing;
        if (next.speed !== undefined && SPEEDS.indexOf(next.speed) !== -1) state.speed = next.speed;
        paint();
      },
    };
  }

  window.mountTimeline = mountTimeline;
})();

(function () {
  let data = window.UFC_MENTION_DASHBOARD_DATA;
  const state = {
    tab: "markets",
    mode: "next",          // "live" | "next" | "replay" — one mode owns the page
    signal: "watch",
    signalUserSet: false,
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
    fightPage: document.getElementById("fightPage"),
    countsLine: document.getElementById("countsLine"),
    status: document.getElementById("dataStatus"),
    refreshButton: document.getElementById("refreshButton"),
    tabBar: document.getElementById("tabBar"),
    portfolioChip: document.getElementById("portfolioChip"),
    paperBadge: document.getElementById("paperBadge"),
    pages: {
      markets: document.getElementById("page-markets"),
      fight: document.getElementById("page-fight"),
      paper: document.getElementById("page-paper"),
      model: document.getElementById("page-model"),
    },
    signalFilter: document.getElementById("signalFilter"),
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
    paperStats: document.getElementById("paperStats"),
    footerStamp: document.getElementById("footerStamp"),
  };

  function init() {
    if (!data) {
      els.status.textContent = "No local data yet. Run ./start_live_dashboard.command";
      els.tableBody.innerHTML = '<tr><td class="empty">No local dashboard data found.</td></tr>';
      return;
    }
    readRoute();
    chooseDefaultCard();
    populatePhraseFilter();
    setupRefreshButton();
    bindEvents();
    bindTickerPause();
    deriveMode();
    seedAmbientPhrases();
    if (state.routedFrame !== null && replayTape()) enterReplay(state.routedFrame, { autoplay: false });
    renderAll();
    state.dataStamp = dataFingerprint();
    scheduleAutoUpdate();
    window.addEventListener("hashchange", () => {
      readRoute();
      renderAll();
    });
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => { fitCache.clear(); fitNames(document); });
    }
    let resizeTimer = 0;
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => { fitCache.clear(); fitNames(document); }, 150);
    });
  }

  const ROUTES = {
    "": "markets", desk: "markets", replay: "markets",
    ledger: "paper", paper: "paper", lab: "model", model: "model",
  };

  function readRoute() {
    const raw = window.location.hash.replace(/^#\/?/, "");
    const legacyFight = raw.match(/^fight\/(.+)$/);
    const parts = raw.split("/").map(decodeURIComponent);
    state.fightRoute = "";
    state.routedMarket = "";
    state.routedFrame = null;
    if (legacyFight) {
      state.fightRoute = legacyFight[1];
      state.tab = "fight";
      return;
    }
    const head = parts[0] || "";
    if (head === "fight" && parts[1]) {
      state.fightRoute = parts[1];
      state.tab = "fight";
      return;
    }
    state.tab = ROUTES[head] || "markets";
    if (head === "replay") {
      const tape = replayTape();
      state.mode = tape ? "replay" : state.mode;
      if (parts[1] !== undefined && parts[1] !== "") {
        const frame = Number(parts[1]);
        if (Number.isFinite(frame)) state.routedFrame = frame;
      }
      // A shared or history-navigated frame seeks the tape directly
      if (tape && state.routedFrame !== null) {
        replay.frame = Math.max(0, Math.min(tape.frames - 1, state.routedFrame));
      }
    } else if (state.mode === "replay" && head !== "replay") {
      // leaving the tape by navigation pauses it; state stays consistent
      stopReplay();
      state.mode = getRows().length ? "live" : "next";
    }
    if (head === "desk" && parts[1] === "m" && parts[2]) {
      state.routedMarket = parts[2];
      state.expanded = new Set([state.routedMarket]);
    }
  }

  function routeTo(hash, { replaceState = false } = {}) {
    const target = hash.startsWith("#") ? hash : `#${hash}`;
    if (window.location.hash === target) return;
    if (replaceState) {
      window.history.replaceState(null, "", target);
      readRoute();
      renderAll();
    } else {
      window.location.hash = target;   // hashchange listener does the rest
    }
  }

  function openFight(eventTicker) {
    routeTo(`/fight/${encodeURIComponent(eventTicker)}`);
  }

  function renderAll() {
    autoPickSignal();
    renderTopline();
    renderTabs();
    renderEventStage();
    renderTicker();
    renderCardBoard();
    renderNav();
    renderFightHeader();
    renderSignalFeed();
    renderTable();
    paintReplayBar();
    renderFightPage();
    renderHealth();
    renderTracking();
    renderPerformance();
    if (state.tab === "markets") markSeen();
    window.requestAnimationFrame(() => fitNames(document));
  }

  /* ---------- replay ----------
     Kalshi opens these markets a couple of nights a month. The rest of the
     time the board sits still, which tells you nothing about how it behaves
     when money is moving. This plays back a night we already recorded: real
     asks, real model numbers, frame by frame. */

  const replay = { frame: 0, timer: 0, playing: false, speed: 1 };

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function replayTape() {
    const tape = data.replay;
    return tape && tape.markets && tape.markets.length ? tape : null;
  }

  function replayRows() {
    const tape = replayTape();
    if (!tape) return [];
    const frame = Math.min(replay.frame, tape.frames - 1);
    return tape.markets.map((market) => {
      const ask = market.ask[frame];
      const bid = market.bid[frame];
      const model = market.model[frame];
      const edge = ask === null || model === null ? null : model - ask;
      return {
        ticker: market.ticker,
        event_ticker: market.event_ticker,
        event_date: market.event_date,
        phrase: market.phrase,
        forms: market.phrase,
        fighter_1: market.fighter_1,
        fighter_2: market.fighter_2,
        matchup: `${market.fighter_1} vs ${market.fighter_2}`,
        yes_ask: ask,
        yes_bid: bid,
        no_ask: ask === null ? null : Math.round((1 - ask) * 100) / 100 + 0.02,
        model_probability: model,
        edge,
        side: edge !== null && edge > 0 ? "yes" : "no",
        hurdle: 0.05,
        league_rate: null,
        watch: edge !== null && edge > 0.06,
        status: "ok",
        probability_source: "fight_context_model",
        context_status: "ok",
        trust_ok: true,
        block_reason: "",
        search_blob: `${market.phrase} ${market.fighter_1} ${market.fighter_2}`.toLowerCase(),
      };
    });
  }

  let replayIndex = null;

  function replayMarket(ticker) {
    const tape = replayTape();
    if (!tape) return null;
    if (!replayIndex) {
      replayIndex = new Map();
      tape.markets.forEach((market) => replayIndex.set(market.ticker, market));
    }
    return replayIndex.get(ticker) || null;
  }

  function replayStamp() {
    const tape = replayTape();
    if (!tape) return "";
    const raw = tape.stamps[Math.min(replay.frame, tape.frames - 1)];
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw;
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function setReplayFrame(frame, animate) {
    const tape = replayTape();
    if (!tape) return;
    // Scrubbing jumps the whole board at once. Flapping 90 cells together
    // reads as noise and costs a frame, so only a playback step animates.
    state.suppressFlap = !animate;
    replay.frame = Math.max(0, Math.min(frame, tape.frames - 1));
    renderTable();
    state.suppressFlap = false;
    paintReplayBar();
  }

  function seedAmbientPhrases() {
    const phrases = [];
    boardRows().concat(replayTape() ? replayRows() : []).forEach((row) => {
      const head = String(row.phrase || "").split(/\s*\/\s*/)[0].trim();
      if (head && !phrases.includes(head)) phrases.push(head);
    });
    const picks = phrases.length ? phrases : ["Knockout", "Decision", "What a fight"];
    document.querySelectorAll(".amb-phrase").forEach((el, i) => {
      el.textContent = (picks[i % picks.length] || "").toUpperCase();
    });
  }

  function deriveMode() {
    if (state.mode === "replay") return;
    state.mode = getRows().length ? "live" : "next";
  }

  function enterReplay(frame, { autoplay = true } = {}) {
    const tape = replayTape();
    if (!tape) return;
    state.mode = "replay";
    replay.frame = Math.max(0, Math.min(tape.frames - 1, Number(frame) || 0));
    if (autoplay && !prefersReducedMotion()) startReplay();
    if (!window.location.hash.startsWith("#/replay")) {
      window.history.replaceState(null, "", `#/replay/${replay.frame}`);
    }
  }

  function exitReplay() {
    stopReplay();
    state.mode = getRows().length ? "live" : "next";
    routeTo("/desk", { replaceState: true });
  }

  function stopReplay() {
    replay.playing = false;
    window.clearInterval(replay.timer);
    replay.timer = 0;
    paintReplayBar();
  }

  function startReplay() {
    const tape = replayTape();
    if (!tape) return;
    replay.playing = true;
    if (replay.frame >= tape.frames - 1) replay.frame = 0;
    window.clearInterval(replay.timer);
    replay.timer = window.setInterval(() => {
      if (replay.frame >= tape.frames - 1) { stopReplay(); return; }
      setReplayFrame(replay.frame + 1, true);
    }, Math.round(900 / replay.speed));
    paintReplayBar();
  }

  /* Frame-to-frame board movement drives the timeline's activity strip:
     the strip literally shows when the night moved. */
  let tapeActivityCache = null;

  function tapeActivity() {
    if (tapeActivityCache) return tapeActivityCache;
    const tape = replayTape();
    if (!tape) return [];
    const out = new Array(tape.frames).fill(0);
    for (let f = 1; f < tape.frames; f += 1) {
      let moved = 0;
      tape.markets.forEach((market) => {
        const a = market.ask[f];
        const b = market.ask[f - 1];
        if (a !== null && b !== null && a !== undefined && b !== undefined) moved += Math.abs(a - b);
      });
      out[f] = moved;
    }
    const peak = Math.max(...out, 0.001);
    tapeActivityCache = out.map((v) => v / peak);
    return tapeActivityCache;
  }

  function tapeMarkers() {
    const activity = tapeActivity();
    if (!activity.length) return [];
    let bigFrame = 0;
    activity.forEach((v, i) => { if (v > activity[bigFrame]) bigFrame = i; });
    return [{ frame: bigFrame, label: "Biggest move" }];
  }

  let timelineHandle = null;

  function paintReplayBar() {
    const holder = document.getElementById("replayBar");
    const tape = replayTape();
    if (!holder) return;
    if (!tape || state.mode !== "replay") {
      holder.hidden = true;
      holder.innerHTML = "";
      timelineHandle = null;
      return;
    }
    holder.hidden = false;
    if (!timelineHandle || !holder.firstChild) {
      timelineHandle = mountTimeline(holder, {
        frames: tape.frames,
        frame: replay.frame,
        stamps: tape.stamps,
        activity: tapeActivity(),
        markers: tapeMarkers(),
        playing: replay.playing,
        speed: replay.speed,
        onSeek: (frame) => { stopReplay(); setReplayFrame(frame, false); syncReplayRoute(); },
        onPlayPause: () => { replay.playing ? stopReplay() : startReplay(); paintReplayBar(); },
        onSpeed: (next) => { replay.speed = next; if (replay.playing) startReplay(); paintReplayBar(); },
      });
    } else {
      timelineHandle.update({ frame: replay.frame, playing: replay.playing, speed: replay.speed });
    }
  }

  let routeSyncTimer = 0;

  function syncReplayRoute() {
    window.clearTimeout(routeSyncTimer);
    routeSyncTimer = window.setTimeout(() => {
      if (state.mode === "replay") {
        window.history.replaceState(null, "", `#/replay/${replay.frame}`);
      }
    }, 300);
  }

  /* ---------- the stage ----------
     The card is an event, so the page opens like one: the octagon lit from
     above, the name at poster scale, and a clock running down to first bell. */

  const FIGHT_ACCENTS = ["#ff6b2c", "#ffc53d", "#3ddc97", "#22d3ee", "#5b9dff", "#ff5c8a"];

  function accentFor(key) {
    const text = String(key || "");
    let h = 0;
    for (let i = 0; i < text.length; i += 1) h = (h * 31 + text.charCodeAt(i)) >>> 0;
    return FIGHT_ACCENTS[h % FIGHT_ACCENTS.length];
  }

  function stageCard() {
    // One mode owns the stage. The numbers on it always describe the same
    // event as the board below it.
    if (state.mode === "replay" && replayTape()) {
      const tape = replayTape();
      const rows = replayRows();
      return {
        title: `The ${formatDate(tape.event_date) || tape.card} tape`,
        date: tape.event_date,
        venue: "Recorded card", location: "",
        fights: new Set(rows.map((row) => row.event_ticker)).size,
        markets: rows.length,
        mode: "replay",
      };
    }
    const live = getSelectedCard() || getCards()[0];
    if (getRows().length && live) {
      return {
        title: live.card_title || "UFC card",
        date: live.event_date,
        venue: live.card_venue || "",
        location: live.card_location || "",
        fights: live.fight_count || (live.fights || []).length,
        markets: live.phrase_count || 0,
        mode: "live",
      };
    }
    const next = (data.upcoming_events || [])[0];
    if (!next) return null;
    return {
      title: next.name, date: next.date, venue: next.venue || "",
      location: next.location || "",
      fights: 0, markets: 0,
      mode: "next",
      hasTape: Boolean(replayTape()),
      tapeDate: replayTape() ? replayTape().event_date : "",
    };
  }

  function boardRows() {
    if (getRows().length) return getRows();
    if (state.mode === "replay" && replayTape()) return replayRows();
    return [];
  }

  function bestEdgeOnCard() {
    let best = null;
    boardRows().forEach((row) => {
      const edge = parseNumber(row.edge);
      if (edge !== null && (best === null || edge > best)) best = edge;
    });
    return best;
  }

  function octagonSvg() {
    const pts = [];
    for (let i = 0; i < 8; i += 1) {
      const a = (Math.PI / 4) * i + Math.PI / 8;
      pts.push(`${(50 + 46 * Math.cos(a)).toFixed(2)},${(50 + 46 * Math.sin(a)).toFixed(2)}`);
    }
    const inner = [];
    for (let i = 0; i < 8; i += 1) {
      const a = (Math.PI / 4) * i + Math.PI / 8;
      inner.push(`${(50 + 34 * Math.cos(a)).toFixed(2)},${(50 + 34 * Math.sin(a)).toFixed(2)}`);
    }
    return `<svg class="cage" viewBox="0 0 100 100" aria-hidden="true">
      <polygon points="${pts.join(" ")}" />
      <polygon points="${inner.join(" ")}" class="cage-inner" />
    </svg>`;
  }

  function renderEventStage() {
    const holder = document.getElementById("eventStage");
    if (!holder) return;
    const card = stageCard();
    if (!card) { holder.innerHTML = ""; holder.hidden = true; return; }
    holder.hidden = false;
    const best = bestEdgeOnCard();
    const where = [card.venue, card.location].filter(Boolean).join(" · ");
    const tonight = card.mode === "live" && card.date === todayLocal();
    const isReplay = card.mode === "replay";

    const modeBadge = isReplay
      ? '<span class="mode-badge mode-badge--replay">Replay</span>'
      : card.mode === "live"
        ? '<span class="mode-badge mode-badge--live">Live</span>'
        : '<span class="mode-badge mode-badge--next">Next event</span>';

    const rightRail = isReplay
      ? `<button class="stage-exit" id="exitReplay" type="button">Leave the tape</button>`
      : "";

    // NEXT mode: the board is empty on purpose; the tape is an invitation,
    // not a default. One clear entry, no historical numbers in the hero.
    const tapeInvite = card.mode === "next" && card.hasTape
      ? `<button class="tape-invite" id="launchReplay" type="button">
          <span class="tape-invite-kicker">While you wait</span>
          <span class="tape-invite-title">Play the ${escapeHtml(formatDate(card.tapeDate) || "last")} card back</span>
          <span class="tape-invite-sub">Every price and signal, exactly as the board saw it</span>
        </button>`
      : "";

    const stats = card.mode === "next"
      ? ""
      : `<div class="stage-stats">
          <span><strong>${formatInteger(card.fights)}</strong>fights</span>
          <span><strong>${formatInteger(card.markets)}</strong>phrase markets</span>
          <span><strong class="${best !== null && best > 0 ? "hot" : ""}">${best === null ? "--" : formatPlainPercent(best, true)}</strong>best edge</span>
        </div>`;

    holder.innerHTML = `
      <section class="stage${tonight ? " is-tonight" : ""}${isReplay ? " is-replay" : ""}">
        <div class="stage-light" aria-hidden="true"></div>
        ${octagonSvg()}
        <div class="stage-body">
          <p class="stage-kicker">
            ${modeBadge}
            ${tonight ? '<span class="onair">On air</span>' : ""}
            <span>${escapeHtml(formatDate(card.date) || "date TBD")}</span>
            ${where ? `<span class="dot">·</span><span>${escapeHtml(where)}</span>` : ""}
          </p>
          <h2 class="stage-title">${escapeHtml(card.title)}</h2>
          <div class="stage-meta">
            ${card.mode === "next" ? `<div class="clock" id="stageClock" data-date="${escapeHtml(card.date || "")}"></div>` : ""}
            ${stats}
            ${tapeInvite}
            ${rightRail}
          </div>
        </div>
      </section>`;
    if (card.mode === "next") startClock();
    const launch = document.getElementById("launchReplay");
    if (launch) launch.addEventListener("click", () => { enterReplay(0); renderAll(); });
    const exit = document.getElementById("exitReplay");
    if (exit) exit.addEventListener("click", () => { exitReplay(); renderAll(); });
  }

  let clockTimer = 0;
  function startClock() {
    const el = document.getElementById("stageClock");
    if (!el) return;
    const date = el.dataset.date;
    if (!date) { el.innerHTML = ""; return; }
    const target = new Date(`${date}T22:00:00`).getTime();
    const paint = () => {
      const node = document.getElementById("stageClock");
      if (!node) { window.clearInterval(clockTimer); return; }
      const ms = target - Date.now();
      if (ms <= 0) { node.innerHTML = '<span class="clock-live">Card in progress</span>'; return; }
      const d = Math.floor(ms / 86400000);
      const h = Math.floor((ms % 86400000) / 3600000);
      const m = Math.floor((ms % 3600000) / 60000);
      const s = Math.floor((ms % 60000) / 1000);
      const unit = (value, label) =>
        `<span class="unit"><b>${String(value).padStart(2, "0")}</b><i>${label}</i></span>`;
      node.innerHTML = (d > 0 ? unit(d, "days") : "") + unit(h, "hrs") + unit(m, "min") + unit(s, "sec");
    };
    paint();
    window.clearInterval(clockTimer);
    clockTimer = window.setInterval(paint, 1000);
  }

  /* ---------- the ticker ----------
     A live card reprices constantly; the strip makes that visible. */
  function renderTicker() {
    const holder = document.getElementById("ticker");
    if (!holder) return;
    const rows = boardRows()
      .map(deriveRow)
      .filter((row) => parseNumber(row.edge) !== null)
      .sort((a, b) => (parseNumber(b.edge) || 0) - (parseNumber(a.edge) || 0))
      .slice(0, 18);
    const emptyRail = document.getElementById("tickerRail");
    if (rows.length < 4) {
      if (emptyRail) emptyRail.innerHTML = "";
      holder.hidden = true;
      return;
    }
    holder.hidden = false;
    const item = (row) => {
      const edge = parseNumber(row.edge);
      const tone = edge > 0 ? "up" : edge < 0 ? "down" : "";
      return `<span class="tick-item">
        <b>${escapeHtml(String(row.phrase || "").split(/\s*\/\s*/)[0])}</b>
        <i>${escapeHtml(lastName(row.fighter_1))}–${escapeHtml(lastName(row.fighter_2))}</i>
        <em class="${tone}">${formatPlainPercent(edge, true)}</em>
      </span>`;
    };
    const strip = rows.map(item).join("");
    const rail = document.getElementById("tickerRail") || holder;
    rail.innerHTML = `<div class="ticker-run">${strip}${strip}</div>`;
    applyTickerPause();
  }

  const TICKER_PAUSE_KEY = "ufc_ticker_paused";

  function tickerPaused() {
    try { return localStorage.getItem(TICKER_PAUSE_KEY) === "1"; } catch (e) { return false; }
  }

  function applyTickerPause() {
    const holder = document.getElementById("ticker");
    const button = document.getElementById("tickerPause");
    const paused = tickerPaused();
    if (holder) holder.classList.toggle("is-paused", paused);
    if (button) {
      button.setAttribute("aria-pressed", paused ? "true" : "false");
      button.setAttribute("aria-label", paused ? "Start the moving ticker" : "Pause the moving ticker");
    }
  }

  function bindTickerPause() {
    const button = document.getElementById("tickerPause");
    if (!button || button.dataset.bound) return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => {
      try { localStorage.setItem(TICKER_PAUSE_KEY, tickerPaused() ? "0" : "1"); } catch (e) { /* private mode */ }
      applyTickerPause();
    });
  }

  function lastName(name) {
    const parts = String(name || "").trim().split(/\s+/);
    return parts[parts.length - 1] || "";
  }

  /* ---------- the board ----------
     Every fight on the card as its own lit tile, then the whole card as a
     grid: fights down, phrases across, colour by how big our disagreement is. */
  function renderCardBoard() {
    const holder = document.getElementById("cardBoard");
    if (!holder) return;
    const card = getSelectedCard() || getCards()[0];
    const rows = boardRows().map(deriveRow);
    if (!card || !rows.length) { holder.innerHTML = ""; holder.hidden = true; return; }
    holder.hidden = false;

    const fights = (card.fights || []).filter((f) => f.fighter_1 && f.fighter_2);
    const tiles = fights.map((fight) => {
      const accent = accentFor(fight.event_ticker);
      const fightRows = rows.filter((row) => row.event_ticker === fight.event_ticker);
      const best = fightRows.reduce((max, row) => {
        const edge = parseNumber(row.edge);
        return edge !== null && edge > max ? edge : max;
      }, -Infinity);
      const watch = fightRows.filter((row) => row.watch).length;
      const top = fightRows.slice().sort((a, b) => (parseNumber(b.edge) || 0) - (parseNumber(a.edge) || 0))[0];
      return `<button class="tile" type="button" data-nav-fight="${escapeHtml(fight.event_ticker)}" style="--accent:${accent}">
        <span class="tile-bar" aria-hidden="true"></span>
        <span class="tile-head">
          <span class="tile-count">${formatInteger(fightRows.length)} markets</span>
          ${watch ? `<span class="tile-watch">${formatInteger(watch)} watch</span>` : ""}
        </span>
        <span class="tile-names">
          <span class="tile-name red">${escapeHtml(fight.fighter_1)}</span>
          <span class="tile-v">v</span>
          <span class="tile-name blue">${escapeHtml(fight.fighter_2)}</span>
        </span>
        <span class="tile-foot">
          <span class="tile-edge ${best > 0 ? "hot" : ""}">${best === -Infinity ? "--" : formatPlainPercent(best, true)}<i>best edge</i></span>
          ${top ? `<span class="tile-top">${escapeHtml(String(top.phrase || "").split(/\s*\/\s*/)[0])}</span>` : ""}
        </span>
      </button>`;
    }).join("");

    holder.innerHTML = `
      <section class="board-block">
        <p class="block-title">The card</p>
        <div class="tiles">${tiles}</div>
      </section>
      ${heatGrid(fights, rows)}`;

    if (!prefersReducedMotion()) {
      holder.querySelectorAll(".tile").forEach((tile, index) => {
        tile.classList.add("deal-in");
        tile.style.animationDelay = `${Math.min(index, 10) * 60}ms`;
      });
      holder.querySelectorAll(".heat .cell").forEach((cell, index) => {
        cell.classList.add("deal-in");
        cell.style.animationDelay = `${Math.min(index, 40) * 12}ms`;
      });
    }
    holder.querySelectorAll("[data-nav-fight]").forEach((el) => {
      el.addEventListener("click", () => {
        state.selectedEvent = el.dataset.navFight;
        state.signalUserSet = false;
        renderAll();
        const target = document.querySelector(".content");
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function heatGrid(fights, rows) {
    if (fights.length < 2) return "";
    const phrases = [];
    rows.forEach((row) => {
      const head = String(row.phrase || "").split(/\s*\/\s*/)[0];
      if (head && !phrases.includes(head)) phrases.push(head);
    });
    if (phrases.length < 3) return "";
    const byKey = new Map();
    rows.forEach((row) => {
      const head = String(row.phrase || "").split(/\s*\/\s*/)[0];
      byKey.set(`${row.event_ticker}|${head}`, row);
    });
    const maxEdge = rows.reduce((max, row) => Math.max(max, Math.abs(parseNumber(row.edge) || 0)), 0.01);

    const head = `<tr><th class="corner-cell"></th>${phrases
      .map((p) => `<th><span>${escapeHtml(p)}</span></th>`).join("")}</tr>`;
    const body = fights.map((fight) => {
      const cells = phrases.map((phrase) => {
        const row = byKey.get(`${fight.event_ticker}|${phrase}`);
        if (!row) return '<td class="cell empty-cell"></td>';
        const edge = parseNumber(row.edge);
        if (edge === null) return '<td class="cell empty-cell"></td>';
        const strength = Math.min(1, Math.abs(edge) / maxEdge);
        const tone = edge > 0 ? "up" : "down";
        // Dark ink only once the fill is bright enough to carry it.
        const bright = strength > 0.55 ? " on-bright" : "";
        const label = `${row.phrase} · ${fight.matchup} · ${formatPlainPercent(edge, true)} edge`;
        return `<td class="cell ${tone}${bright}${row.watch ? " is-watch" : ""}" style="--s:${strength.toFixed(3)}"
          data-heat="${escapeHtml(row.ticker || "")}" data-fight="${escapeHtml(fight.event_ticker)}"
          title="${escapeHtml(label)}"><span>${formatPlainPercent(edge, true)}</span></td>`;
      }).join("");
      return `<tr><th class="row-head" style="--accent:${accentFor(fight.event_ticker)}">
        <span>${escapeHtml(lastName(fight.fighter_1))} <i>v</i> ${escapeHtml(lastName(fight.fighter_2))}</span>
      </th>${cells}</tr>`;
    }).join("");

    return `<section class="board-block">
      <p class="block-title">Our disagreement with the market <span class="block-note">green = we say more likely · red = less</span></p>
      <div class="heat-wrap"><table class="heat">${head}${body}</table></div>
    </section>`;
  }

  function autoPickSignal() {
    if (state.signalUserSet) return;
    const rows = boardRows();
    if (rows.some((row) => row.watch)) state.signal = "watch";
    else if (rows.some((row) => parseNumber(row.edge) > 0)) state.signal = "active";
    else state.signal = "all";
  }

  function renderTabs() {
    els.tabBar.querySelectorAll(".tab").forEach((tab) => {
      const name = tab.dataset.tab;
      const active = name === "replay"
        ? state.mode === "replay" && state.tab === "markets"
        : name === state.tab && !(name === "markets" && state.mode === "replay");
      tab.classList.toggle("is-active", active);
    });
    const switched = state.paintedTab !== state.tab;
    Object.entries(els.pages).forEach(([name, page]) => {
      page.hidden = name !== state.tab;
      if (name === state.tab && switched) {
        page.classList.remove("is-entering");
        void page.offsetWidth;
        page.classList.add("is-entering");
      }
    });
    state.paintedTab = state.tab;
    if (els.signalFilter) {
      els.signalFilter.querySelectorAll(".segment").forEach((seg) => {
        seg.classList.toggle("is-active", seg.dataset.signal === state.signal);
      });
    }
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
    if (window.STATIC_SITE) return false;
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

  /* Cheap identity for a payload: the snapshot stamp plus the numbers that
     actually drive the board. */
  function dataFingerprint() {
    const summary = data.summary || {};
    const rows = getRows();
    let acc = `${summary.kalshi_snapshot_timestamp || ""}|${rows.length}|`;
    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i];
      acc += `${row.ticker || ""}:${row.yes_bid}:${row.yes_ask}:${row.model_probability}:${row.watch ? 1 : 0};`;
    }
    acc += `|${(data.tracking_positions || []).length}`;
    return acc;
  }

  function scheduleAutoUpdate() {
    let seconds = Number((data.summary || {}).kalshi_poll_seconds || 0);
    if (window.STATIC_SITE) seconds = Math.max(seconds, 60);
    if (seconds <= 0) return;
    if (!isServerMode() && !window.STATIC_SITE) return;
    window.setInterval(async () => {
      if (state.refreshing || state.loadingData) return;
      try {
        await loadFreshData();
        // Between price changes the payload is identical. Rebuilding the page
        // anyway would flash every card, drop hover and lose the user's place,
        // so only the age readout is repainted until something actually moves.
        const stamp = dataFingerprint();
        if (stamp === state.dataStamp) { renderTopline(); return; }
        state.dataStamp = stamp;
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
    const TAB_ROUTES = { markets: "/desk", paper: "/ledger", model: "/lab" };
    els.tabBar.addEventListener("click", (event) => {
      const tab = event.target.closest("[data-tab]");
      if (!tab) return;
      if (tab.dataset.tab === "replay") {
        if (state.mode !== "replay") enterReplay(replay.frame || 0);
        routeTo(`/replay/${replay.frame}`);
        renderAll();
        return;
      }
      if (tab.dataset.tab === "markets" && state.mode === "replay") exitReplay();
      routeTo(TAB_ROUTES[tab.dataset.tab] || "/desk");
    });
    if (els.portfolioChip) {
      els.portfolioChip.addEventListener("click", () => {
        routeTo("/ledger");
        state.tab = "paper";
        renderTabs();
      });
    }
    if (els.signalFilter) {
      els.signalFilter.addEventListener("click", (event) => {
        const seg = event.target.closest("[data-signal]");
        if (!seg) return;
        state.signal = seg.dataset.signal;
        state.signalUserSet = true;
        renderTabs();
        renderTable();
      });
    }
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
    const cardToday = getCards().some((card) => card.event_date === todayLocal());
    const freshEnough = ts && (Date.now() - new Date(ts).getTime()) < 3 * 60 * 1000;
    const livePill = cardToday && freshEnough ? '<span class="live-pill">LIVE</span> · ' : "";
    els.status.innerHTML = `${livePill}${stale ? '<span class="stale">Stale</span> · ' : ""}updated ${escapeHtml(when)} · read-only${polling}`;
    const pulse = document.getElementById("updatePulse");
    if (pulse && state.lastQuoteMoves != null) {
      pulse.textContent = state.lastQuoteMoves
        ? `${state.lastQuoteMoves} quote${state.lastQuoteMoves === 1 ? "" : "s"} moved`
        : "";
    }
    if (els.footerStamp) {
      els.footerStamp.textContent = ts ? `Data updated ${formatTimestamp(ts)}` : "";
    }
    renderPortfolioChip();
  }

  function renderPortfolioChip() {
    if (!els.portfolioChip) return;
    const positions = data.tracking_positions || [];
    if (!positions.length) {
      els.portfolioChip.hidden = true;
      if (els.paperBadge) els.paperBadge.hidden = true;
      return;
    }
    const settled = positions.filter((row) => row.outcome === "yes" || row.outcome === "no");
    const open = positions.length - settled.length;
    const pnl = settled.reduce((sum, row) => sum + settledPnl(row), 0);
    const pnlBit = settled.length
      ? ` · P/L <span class="${toneClass(pnl)}">${formatMoney(pnl)}</span>`
      : "";
    els.portfolioChip.hidden = false;
    els.portfolioChip.innerHTML = `${formatInteger(positions.length)} paper position${plural(positions.length)} · ${formatInteger(open)} open${pnlBit}`;
    if (els.paperBadge) {
      els.paperBadge.hidden = false;
      els.paperBadge.textContent = formatInteger(positions.length);
    }
  }

  function settledPnl(row) {
    const entry = parseNumber(row.paper_price);
    const side = String(row.paper_side || row.side || "").toLowerCase();
    if (entry === null || !side || (row.outcome !== "yes" && row.outcome !== "no")) return 0;
    return side === row.outcome ? 1 - entry : -entry;
  }

  /* ---------- signal alerts ---------- */

  const LAST_SEEN_KEY = "ufc_seen_watch_tickers";

  /* Which watch signals are new is per-market, not per-poll: every row carries
     the same snapshot stamp, so remember the tickers already shown instead. */
  function seenTickers() {
    try {
      const raw = localStorage.getItem(LAST_SEEN_KEY);
      if (!raw) return new Set();
      const parsed = JSON.parse(raw);
      return new Set(Array.isArray(parsed) ? parsed : []);
    } catch (e) {
      return new Set();
    }
  }

  function markSeen() {
    const tickers = getRows().filter((row) => row.watch).map((row) => String(row.ticker || ""));
    if (!tickers.length) return;
    const merged = new Set([...state.seenAtLoad || [], ...tickers]);
    try {
      localStorage.setItem(LAST_SEEN_KEY, JSON.stringify([...merged].slice(-400)));
    } catch (e) { /* private mode */ }
  }

  function newWatchRows() {
    if (state.seenAtLoad === undefined) state.seenAtLoad = seenTickers();
    const seen = state.seenAtLoad;
    return getRows().filter((row) => row.watch && !seen.has(String(row.ticker || "")));
  }

  function renderSignalFeed() {
    const holder = document.getElementById("signalFeed");
    if (!holder) return;
    const fresh = newWatchRows();
    if (!fresh.length) { holder.innerHTML = ""; holder.hidden = true; return; }
    holder.hidden = false;
    const items = fresh.slice(0, 6).map((row) => {
      const side = String(row.side || "").toUpperCase();
      const matchup = row.fighter_1 && row.fighter_2 ? `${row.fighter_1} vs ${row.fighter_2}` : row.event_title || "";
      return `<button class="signal-item" type="button" data-signal-fight="${escapeHtml(row.event_ticker || "")}">
        <span class="signal-new">NEW</span>
        <strong>${escapeHtml(String(row.phrase || ""))}</strong>
        <span class="signal-side">${escapeHtml(side)}</span>
        <span class="signal-fight">${escapeHtml(matchup)}</span>
        <span class="signal-edge">${formatPlainPercent(row.edge, true)} edge</span>
      </button>`;
    }).join("");
    holder.innerHTML = `<div class="signal-feed-head">New signals since your last visit</div>${items}`;
    holder.querySelectorAll("[data-signal-fight]").forEach((button) => {
      button.addEventListener("click", () => openFight(button.dataset.signalFight));
    });
  }

  /* ---------- sidebar nav ---------- */

  function renderNav() {
    const cards = getCards();
    if (!cards.length) {
      const upcoming = data.upcoming_events || [];
      if (!upcoming.length) {
        els.cardNav.innerHTML = '<div class="nav-empty">No Kalshi UFC mention markets are open right now. This page keeps checking on its own.</div>';
        return;
      }
      els.cardNav.innerHTML = upcoming.slice(0, 8).map((event, index) => `
        <div class="nav-card schedule ${index === 0 ? "is-next" : ""}">
          <span class="nav-date">${escapeHtml(formatDate(event.date))}${tonightBadge(event.date)}${index === 0 ? ' <span class="next-chip">Next</span>' : ""}</span>
          <h2>${escapeHtml(event.name)}</h2>
          <span class="nav-sub">${escapeHtml([event.venue, event.location].filter(Boolean).join(" · "))}</span>
        </div>`).join("");
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
          <span class="nav-date">${escapeHtml(formatDate(card.event_date) || "Date TBD")}${tonightBadge(card.event_date)}</span>
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
        <strong>${fight.fighter_1 && fight.fighter_2 ? cornerKey(fight.fighter_1, fight.fighter_2) : escapeHtml(fight.matchup || "TBD fight")}</strong>
        <span class="nav-tag ${watch ? "watch" : ""}">${escapeHtml(tag)}</span>
      </button>`);
    });
    return `<div class="nav-fights">${items.join("")}</div>`;
  }

  /* ---------- fight header ---------- */

  function renderFightHeader() {
    const card = getSelectedCard();
    const fight = getSelectedFight();

    // In replay, the stage already owns the context. Repeating the future
    // event here would glue tomorrow's fighters onto last month's prices.
    if (state.mode === "replay") {
      const rows = boardRows();
      const watch = rows.filter((row) => deriveRow(row).watch).length;
      els.fightHeader.innerHTML = `
        <p class="block-title">Every market on the tape
          <span class="block-note">${formatInteger(rows.length)} phrase markets · ${watch
            ? `${formatInteger(watch)} watch signals at this point of the night`
            : "no watch signals at this point of the night"}</span>
        </p>`;
      return;
    }

    if (!card) {
      const next = (data.upcoming_events || [])[0];
      if (next) {
        const hero = next.fighter_1 && next.fighter_2
          ? tapeHtml(next.fighter_1, next.fighter_2, { large: isMarquee(next.fighter_1, next.fighter_2), bout: "NEXT EVENT" })
          : `<h2 class="matchup-hero solo fit-name">${escapeHtml(next.name)}</h2>`;
        const eventDate = new Date(`${next.date}T00:00:00`);
        const volume = eventDate.getFullYear() - 2019;
        const dayOfYear = Math.ceil((eventDate - new Date(eventDate.getFullYear(), 0, 0)) / 86400000);
        const city = String(next.location || "").split(",")[0].toUpperCase();
        const numeral = (String(next.name).match(/UFC\s+(\d+)/) || [])[1] || "";
        const ms = new Date(`${next.date}T22:00:00`).getTime() - Date.now();
        const days = Math.max(0, Math.floor(ms / 86400000));
        const hours = Math.max(0, Math.floor((ms % 86400000) / 3600000));
        els.fightHeader.innerHTML = `
          <div class="countdown-hero">
            ${numeral ? `<span class="ghost-numeral" aria-hidden="true">${escapeHtml(numeral)}</span>` : ""}
            <p class="folio">UFC MENTION MARKETS · VOL. ${volume} · NO. ${dayOfYear}${city ? ` · ${escapeHtml(city)}` : ""}</p>
            ${hero}
            <div class="countdown" role="timer" aria-label="Time until the next event">
              <span class="cd-group"><strong>${String(days).padStart(2, "0")}</strong><span>DAYS</span></span>
              <span class="cd-colon">:</span>
              <span class="cd-group"><strong>${String(hours).padStart(2, "0")}</strong><span>HRS</span></span>
            </div>
            <p class="fight-sub">${escapeHtml([next.name, next.venue, next.location].filter(Boolean).join(" · "))} · Mention markets tend to open closer to fight night. This page checks on its own.</p>
          </div>`;
        return;
      }
      els.fightHeader.innerHTML = "<h2>No cards yet</h2><p class=\"fight-sub\">Kalshi's UFC mention markets show up here on their own once they open.</p>";
      return;
    }

    if (fight) {
      const tbd = fight.odds_status === "tbd";
      const watch = Number(fight.watch_count || 0);
      const bits = tbd
        ? ["Kalshi lists this fight but has not posted mention odds yet."]
        : [
          `${formatInteger(fight.priced_count)} phrase markets with live prices`,
          `${formatInteger(fight.model_ready_count)} with a fight-level model number`,
          watch ? `<span class="watch-note">${formatInteger(watch)} watch row${plural(watch)}</span>` : "no watch rows right now",
        ];
      const hero = fight.fighter_1 && fight.fighter_2
        ? tapeHtml(fight.fighter_1, fight.fighter_2, { large: isMarquee(fight.fighter_1, fight.fighter_2) })
        : `<h2 class="matchup-hero solo">${escapeHtml(fight.matchup || "TBD fight")}</h2>`;
      els.fightHeader.innerHTML = `
        <p class="crumb">${escapeHtml(card.card_title || "UFC card")} · ${escapeHtml(formatDate(fight.event_date) || "date TBD")}${tonightBadge(fight.event_date)} · <a class="fight-link" href="#fight/${encodeURIComponent(fight.event_ticker)}">Fight page &rarr;</a></p>
        ${hero}
        <p class="fight-sub">${bits.join(" · ")}</p>`;
      return;
    }

    // The stage above already names the card; this section is the board itself.
    const watch = Number(card.watch_count || 0);
    els.fightHeader.innerHTML = `
      <p class="block-title">Every market on the card
        <span class="block-note">${formatInteger(card.phrase_count)} phrase markets · ${watch
          ? `<span class="watch-note">${formatInteger(watch)} watch row${plural(watch)}</span>`
          : "no watch rows right now"}</span>
      </p>`;
  }

  function isMarquee(f1, f2) {
    const a = identityFor(f1);
    const b = identityFor(f2);
    return ((a && a.marquee_score) || 0) + ((b && b.marquee_score) || 0) >= 40;
  }

  function countdownText(dateStr) {
    if (!dateStr) return "";
    const target = new Date(`${dateStr}T22:00:00`);
    const ms = target.getTime() - Date.now();
    if (Number.isNaN(ms)) return "";
    if (ms <= 0) return "today";
    const days = Math.floor(ms / 86400000);
    const hours = Math.floor((ms % 86400000) / 3600000);
    if (days > 0) return `in ${days}d ${hours}h`;
    return `in ${hours}h`;
  }

  function todayLocal() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  function tonightBadge(dateStr) {
    return dateStr && dateStr === todayLocal() ? ' <span class="tonight">Tonight</span>' : "";
  }

  /* ---------- fighter identity: engraved guilloche seals ----------
     Every fighter is issued a deterministic banknote-style seal generated
     from their real fight data. No photos, no initials, no randomness:
     the same fighter renders the same seal forever. */

  function identityFor(name) {
    const fighters = data.fighters || {};
    const key = String(name || "").trim().toLowerCase();
    if (!key) return null;
    if (fighters[key]) return fighters[key];
    // last-name fallback (upcoming events only list surnames); must be unique
    const matches = Object.values(fighters).filter((f) => {
      const parts = String(f.name || "").toLowerCase().split(/\s+/);
      return parts.length > 1 && parts.slice(1).join(" ").endsWith(key);
    });
    return matches.length === 1 ? matches[0] : null;
  }

  /* ---------- fighter identity ----------
     No generated emblem: a mark that cannot be read at 20px is decoration.
     Identity is the corner (the sport's own code) plus the fighter's real
     numbers, which is what anyone actually reads a fighter by. */

  function cornerKey(f1, f2) {
    if (!f1 || !f2) return `<span class="corner red">${escapeHtml(f1 || f2 || "--")}</span>`;
    return `<span class="corner red">${escapeHtml(f1)}</span>`
      + '<span class="vs">v</span>'
      + `<span class="corner blue">${escapeHtml(f2)}</span>`;
  }

  function tapeStats(identity) {
    if (!identity) return "";
    const rows = [];
    if (identity.record) rows.push(["Record", identity.record]);
    if (identity.stance) rows.push(["Stance", identity.stance]);
    if (identity.reach_cms) rows.push(["Reach", `${Math.round(identity.reach_cms / 2.54)}"`]);
    if (identity.n_fights) rows.push(["Bouts in our data", String(identity.n_fights)]);
    return rows.map(([label, value]) =>
      `<span class="tape-stat"><span class="tape-stat-label">${escapeHtml(label)}</span>`
      + `<span class="leader"></span><span class="tape-stat-value">${escapeHtml(value)}</span></span>`
    ).join("");
  }

  function tapeSide(name, corner) {
    const identity = identityFor(name);
    const tags = ((identity || {}).style_tags || [])
      .map((tag) => `<span class="style-tag">${escapeHtml(tag)}</span>`).join("");
    return `<div class="tape-side ${corner}">
      <span class="tape-corner">${corner === "red" ? "Red corner" : "Blue corner"}</span>
      <span class="tape-name fit-name">${escapeHtml(name)}</span>
      ${identity && identity.nickname ? `<span class="tape-nick">"${escapeHtml(identity.nickname)}"</span>` : ""}
      ${tags ? `<span class="tape-tags">${tags}</span>` : ""}
      <span class="tape-statrows">${tapeStats(identity)}</span>
    </div>`;
  }

  function tapeHtml(f1, f2, options = {}) {
    const marquee = options.large ? " is-marquee" : "";
    const slug = options.bout ? `<span class="tape-slug">${escapeHtml(options.bout)}</span>` : "";
    return `<div class="tape${marquee}">
      ${slug}
      ${tapeSide(f1, "red")}
      <span class="tape-vs">v</span>
      ${tapeSide(f2, "blue")}
    </div>`;
  }

  /* fit-to-measure: solve each name's size so it fills its column like set type */
  const fitCache = new Map();

  function fitNames(root) {
    (root || document).querySelectorAll(".fit-name").forEach((el) => {
      const parent = el.parentElement;
      if (!parent) return;
      const available = parent.clientWidth;
      if (available < 40) return;
      const text = el.textContent || "";
      const cacheKey = `${text}|${available}`;
      if (fitCache.has(cacheKey)) {
        el.style.fontSize = fitCache.get(cacheKey);
        return;
      }
      el.style.fontSize = "";
      const base = parseFloat(getComputedStyle(el).fontSize) || 40;
      const width = el.scrollWidth || 1;
      const solved = Math.max(20, Math.min(base * (available / width) * 0.98, base * 1.35));
      const px = `${solved.toFixed(1)}px`;
      el.style.fontSize = px;
      fitCache.set(cacheKey, px);
    });
  }

  /* ---------- market table ---------- */

  function activeColumns() {
    const cols = [
      { key: "call", label: "Call", type: "signal" },
      { key: "phrase", label: "Phrase", type: "phrase" },
      { key: "model_probability", label: "The book", type: "lane", className: "lane-col" },
      { key: "yes_ask", label: "YES", type: "price", className: "num optional price-col" },
      { key: "no_ask", label: "NO", type: "price", className: "num optional price-col" },
      { key: "side", label: "Side", type: "side", className: "optional" },
      { key: "edge", label: "Edge", type: "pct", className: "num", badge: true, signed: true },
    ];
    if (!state.selectedEvent) {
      cols.splice(2, 0, { key: "matchup", label: "Fight", type: "fight" });
    }
    return cols;
  }

  /* ---------- the lane ----------
     Every market drawn on one shared logit axis. Prices here live at 3-12c and
     88-97c, where a linear 0-100 bar shows nothing; logit spreads those ends
     out. The gap between bid and ask is dead air: the market has no opinion,
     and our number is the only thing planted in it. */

  const LOGIT_SPAN = 9.19024;   // logit(0.99) - logit(0.01)
  const LOGIT_MIN = -4.59512;   // logit(0.01)

  function laneX(p) {
    const value = Math.min(0.99, Math.max(0.01, Number(p)));
    return ((Math.log(value / (1 - value)) - LOGIT_MIN) / LOGIT_SPAN) * 100;
  }

  const LANE_TICKS = [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99];

  /* Where this price came from. The market's ask is the solid line, our number
     the dotted one, so a row shows at a glance whether the two have been
     converging or pulling apart since we started watching. */
  function sparkline(row) {
    let track = (data.price_tracks || {})[String(row.ticker || "")];
    // While a tape is playing, the line draws itself frame by frame instead of
    // sitting there finished, so the row shows the move as it happened.
    if (!track && replayTape()) {
      const market = replayMarket(String(row.ticker || ""));
      if (market) {
        const upto = Math.min(replay.frame, market.ask.length - 1);
        track = [];
        for (let i = 0; i <= upto; i += 1) {
          if (market.ask[i] === null || market.ask[i] === undefined) continue;
          track.push([market.ask[i], market.model[i]]);
        }
      }
    }
    if (!track || track.length < 3) return '<span class="spark is-thin" aria-hidden="true"></span>';
    const asks = track.map((point) => point[0]).filter((v) => v !== null);
    const models = track.map((point) => point[1]).filter((v) => v !== null && v !== undefined);
    const all = asks.concat(models);
    const low = Math.min.apply(null, all);
    const high = Math.max.apply(null, all);
    const span = (high - low) || 0.02;
    const W = 116;
    const H = 30;
    const x = (i) => (i / (track.length - 1)) * W;
    const y = (v) => H - 3 - ((v - low) / span) * (H - 6);
    const path = (pick) => {
      const points = [];
      track.forEach((point, i) => {
        const value = pick(point);
        if (value === null || value === undefined) return;
        points.push(`${x(i).toFixed(1)},${y(value).toFixed(1)}`);
      });
      return points.length > 1 ? `M ${points.join(" L ")}` : "";
    };
    const askPath = path((point) => point[0]);
    const modelPath = path((point) => point[1]);
    const lastAsk = asks[asks.length - 1];
    const firstAsk = asks[0];
    const drift = lastAsk > firstAsk ? "up" : lastAsk < firstAsk ? "down" : "flat";
    // Area fill under the ask line plus an end dot: readable at a glance,
    // and the drift class colors the whole mark.
    const lastPoint = askPath ? askPath.split(" L ").pop() : "";
    const [endX, endY] = lastPoint ? lastPoint.replace("M ", "").split(",") : [0, 0];
    const area = askPath ? `${askPath} L ${W},${H} L 0,${H} Z` : "";
    const gid = `sg${String(row.ticker || "").replace(/[^A-Za-z0-9]/g, "").slice(-8)}`;
    return `<span class="spark ${drift}" role="img" aria-label="Price history, ${formatPlainPercent(firstAsk)} to ${formatPlainPercent(lastAsk)}">
      <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" preserveAspectRatio="none" focusable="false">
        <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="currentColor" stop-opacity="0.28"/>
          <stop offset="1" stop-color="currentColor" stop-opacity="0"/>
        </linearGradient></defs>
        ${area ? `<path class="spark-area" fill="url(#${gid})" stroke="none" d="${area}"/>` : ""}
        ${modelPath ? `<path class="spark-model" d="${modelPath}"/>` : ""}
        <path class="spark-ask" d="${askPath}"/>
        ${lastPoint ? `<circle class="spark-dot" cx="${endX}" cy="${endY}" r="2.4"/>` : ""}
      </svg>
    </span>`;
  }

  function laneCell(row) {
    const model = parseNumber(row.model_probability);
    if (model === null) return '<span class="muted">no model</span>';
    const bid = parseNumber(row.yes_bid);
    const ask = parseNumber(row.yes_ask);
    const base = parseNumber(row.league_rate);
    const hurdle = parseNumber(row.hurdle);
    const side = String(row.side || "").toLowerCase();

    const ticks = LANE_TICKS.map((t) =>
      `<i class="tick${t === 0.5 ? " spine" : ""}" style="left:${laneX(t).toFixed(2)}%"></i>`).join("");

    let book = "";
    if (bid !== null && ask !== null && ask > bid) {
      const x1 = laneX(bid);
      const x2 = laneX(ask);
      book = `<i class="dead" style="left:${x1.toFixed(2)}%;width:${Math.max(0, x2 - x1).toFixed(2)}%"></i>`
        + `<i class="quote bid" style="left:${x1.toFixed(2)}%"></i>`
        + `<i class="quote ask" style="left:${x2.toFixed(2)}%"></i>`;
    }
    const baseTick = base !== null
      ? `<i class="base" style="left:${laneX(base).toFixed(2)}%" title="Base rate ${formatPlainPercent(base)}"></i>` : "";
    const hurdleTick = hurdle !== null && side && ask !== null
      ? `<i class="hurdle" style="left:${laneX(side === "no" ? Math.max(0.01, 1 - (parseNumber(row.no_ask) || 0) + hurdle) : Math.min(0.99, ask + hurdle)).toFixed(2)}%"></i>`
      : "";
    const mark = `<b class="mark${row.watch ? " is-watch" : ""}" style="left:${laneX(model).toFixed(2)}%"></b>`;

    // The YES and NO columns already carry the quote, so the lane shows only
    // our number and lets the columns do their job.
    const spread = "";
    return `<span class="lane-cell">${sparkline(row)}
      <span class="lane" role="img" aria-label="${escapeHtml(laneLabel(row, model, bid, ask))}">
        <i class="bed"></i>${ticks}${book}${baseTick}${hurdleTick}${mark}
      </span>
      <span class="lane-read"><b>${formatPlainPercent(model)}</b>${spread}</span>
    </span>`;
  }

  function laneLabel(row, model, bid, ask) {
    const bits = [`our number ${formatPlainPercent(model)}`];
    if (bid !== null && ask !== null) bits.push(`market ${formatPlainPercent(bid)} bid, ${formatPlainPercent(ask)} ask`);
    const edge = parseNumber(row.edge);
    if (edge !== null) bits.push(`${formatPlainPercent(edge, true)} edge`);
    return bits.join("; ");
  }

  function renderTable() {
    const marketSection = document.querySelector("#page-markets .content .toolbar");
    const tableWrap = document.querySelector("#page-markets .content .table-wrap");
    // The board only shows the mode's own rows. In NEXT mode there is no
    // board: the stage owns the screen and offers the tape instead.
    const sourceRows = boardRows();
    const idle = !sourceRows.length;
    if (marketSection) marketSection.hidden = idle;
    if (tableWrap) tableWrap.hidden = idle;
    if (idle) {
      els.tableMeta.textContent = "";
      els.tableBody.innerHTML = "";
      rowNodes.clear();
      state.boardPainted = false;
      return;
    }
    const columns = activeColumns();
    let rows = sourceRows.map(deriveRow);
    rows = applyFilters(rows);
    rows = applySort(rows);
    const scope = state.signal === "watch" ? "watch row" : state.signal === "active" ? "active market" : "market";
    els.tableMeta.textContent = `${formatInteger(rows.length)} ${scope}${plural(rows.length)} · click a row for the math`;
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
      return "Kalshi has not posted a YES/NO buy price yet, so there is nothing to compare against.";
    }
    if (row.probability_source !== "fight_context_model") {
      return "This row has no fight-level model number, only a rough history average, so it cannot be a watch.";
    }

    const model = formatPlainPercent(row.model_probability);
    const side = String(row.side || "").toUpperCase();
    const sidePrice = formatPlainPercent(row.side_price);
    const edge = formatPlainPercent(row.edge, true);
    const hurdle = formatPlainPercent(row.hurdle);
    const cap = formatPlainPercent(row.edge_cap);
    const thin = row.data_risk ? " Fighter history is thin here, so we raised the bar. It cleared anyway, but trust it less." : "";

    if (row.watch) {
      if (parseNumber(row.side_price) === null) {
        return `Our model thinks YES is ${model} and the book has not printed a quote at this point of the night yet. The edge reads ${edge} against the last known level.${thin}`;
      }
      const capBit = parseNumber(row.edge_cap) !== null ? ` and the cap is ${cap}` : "";
      return `Our model thinks YES is ${model}. Buying ${side} costs ${sidePrice}, so ${side} has ${edge} of edge. The entry bar is ${hurdle}${capBit}, so this clears and becomes WATCH ${side}.${thin}`;
    }
    if (row.block_reason === "big_gap") {
      return `Our model thinks YES is ${model}, a ${edge} disagreement with the market. On settled cards, most gaps over ${cap} came from the model, so we flag this row instead of trading it.`;
    }
    if (row.block_reason === "low_trust") {
      return `Our model thinks YES is ${model} and ${side} has ${edge} of edge, but ${row.trust_note || "this phrase group has not shown real skill on old fights"}.`;
    }
    if (parseNumber(row.edge) <= 0) {
      return `Our model thinks YES is ${model}. Neither side is cheap compared to that, so there is nothing to do here.`;
    }
    return `Our model thinks YES is ${model}. ${side} at ${sidePrice} has ${edge} of edge. That is positive but under the ${hurdle} entry bar${row.data_risk ? " (raised because fighter history is thin)" : ""}, so it is only a lean.`;
  }

  function matchesSignal(row) {
    if (state.signal === "all") return true;
    if (state.signal === "watch") return Boolean(row.watch);
    // "active": anything with a live positive-edge story worth a look
    return Boolean(row.watch) || row.block_reason === "big_gap" || parseNumber(row.edge) > 0;
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
      if (!matchesSignal(row)) return false;
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
    els.tableHead.innerHTML = `<tr>${columns.map((column) => {
      const sorted = state.sortKey === column.key;
      const ariaSort = sorted ? (state.sortDir === "asc" ? "ascending" : "descending") : "none";
      // The lane's axis is printed once, here, instead of on every row.
      const scale = column.type === "lane"
        ? `<span class="lane-scale" aria-hidden="true">${[0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.95]
          .map((t) => `<i style="left:${laneX(t).toFixed(2)}%">${Math.round(t * 100)}</i>`).join("")}</span>`
        : "";
      return `<th data-key="${escapeHtml(column.key)}" class="${column.className || ""}" aria-sort="${ariaSort}" scope="col">`
        + `<button type="button" class="th-sort">${escapeHtml(column.label)}<span class="sort-caret" aria-hidden="true">${sorted ? (state.sortDir === "asc" ? "▲" : "▼") : ""}</span></button>${scale}</th>`;
    }).join("")}</tr>`;
    els.tableHead.querySelectorAll("th").forEach((th) => {
      const button = th.querySelector(".th-sort");
      if (!button) return;
      button.addEventListener("click", () => {
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

  /* ---------- the board ----------
     Rows are keyed by ticker and mutated in place. Rebuilding the tbody on
     every 30s poll threw away focus, scroll position and any open row, and it
     made every price look like it had moved when the sort merely reordered.
     Measured on real snapshots, the default sort moves a row on 20% of polls
     at the median and 73% at p90, so position is not identity here. */

  const rowNodes = new Map();

  function rowClassFor(row, open) {
    return [
      row.watch ? "is-watch" : (row.call === "NO PRICES" || row.call === "NO MODEL") ? "is-quiet" : "",
      "is-expandable",
      open ? "is-open" : "",
    ].filter(Boolean).join(" ");
  }

  function buildRow(columns, row) {
    const tr = document.createElement("tr");
    tr.dataset.expand = String(row.ticker || "");
    tr.tabIndex = 0;
    tr.setAttribute("role", "button");
    columns.forEach((column) => {
      const td = document.createElement("td");
      td.className = column.className || "";
      td.dataset.col = column.key;
      tr.appendChild(td);
    });
    return tr;
  }

  function paintRow(tr, columns, row, open, animate) {
    tr.className = rowClassFor(row, open);
    tr.setAttribute("aria-expanded", open ? "true" : "false");
    tr.setAttribute("aria-label", `${row.phrase || "market"}, ${row.fighter_1 || ""} versus ${row.fighter_2 || ""}. Opens the working behind this number.`);
    columns.forEach((column, index) => {
      const td = tr.children[index];
      if (!td) return;
      const html = formatCell(row[column.key], column, row);
      if (column.type === "price") {
        paintPrice(td, html, row, column, animate);
        return;
      }
      if (td.dataset.html !== html) {
        td.dataset.html = html;
        td.innerHTML = html;
      }
    });
  }

  /* The flap fires only where a number actually moved. Prices change on about
     10% of ticks; the model number and the call almost never do, so boarding
     those would be a slot machine that reports nothing. */
  function paintPrice(td, html, row, column, animate) {
    const previous = td.dataset.value;
    const value = String(row[column.key] === null || row[column.key] === undefined ? "" : row[column.key]);
    if (td.dataset.html !== html) {
      td.dataset.html = html;
      td.innerHTML = html;
    }
    td.dataset.value = value;
    if (state.suppressFlap || !animate || previous === undefined || previous === value || !value || !previous) return;
    state.quoteMoves = (state.quoteMoves || 0) + 1;
    const rising = parseNumber(value) > parseNumber(previous);
    td.classList.remove("flap-up", "flap-down");
    void td.offsetWidth;
    td.classList.add(rising ? "flap-up" : "flap-down");
    window.setTimeout(() => td.classList.remove("flap-up", "flap-down"), 700);
  }

  function renderBody(columns, rows) {
    const body = els.tableBody;
    if (!rows.length) {
      rowNodes.clear();
      const fight = getSelectedFight();
      const message = fight && fight.odds_status === "tbd"
        ? "Kalshi lists this fight. The mention odds are not posted yet, and this fills in on its own."
        : "No markets match those filters.";
      body.innerHTML = `<tr><td class="empty" colspan="${columns.length}">${escapeHtml(message)}</td></tr>`;
      return;
    }
    if (body.querySelector("td.empty")) { body.innerHTML = ""; rowNodes.clear(); }

    const columnsChanged = state.paintedColumns !== columns.map((c) => c.key).join(",");
    if (columnsChanged) { body.innerHTML = ""; rowNodes.clear(); }
    state.paintedColumns = columns.map((c) => c.key).join(",");

    state.quoteMoves = 0;
    let dealt = 0;
    const seen = new Set();
    let cursor = null;
    rows.forEach((row) => {
      const key = String(row.ticker || "");
      seen.add(key);
      const open = key && state.expanded.has(key);
      let tr = rowNodes.get(key);
      const fresh = !tr;
      if (fresh) {
        tr = buildRow(columns, row);
        rowNodes.set(key, tr);
        if (!state.boardPainted && dealt < 14 && !prefersReducedMotion()) {
          tr.classList.add("deal-in");
          tr.style.animationDelay = `${dealt * 28}ms`;
          dealt += 1;
        }
      }
      paintRow(tr, columns, row, open, !fresh && state.boardPainted);

      const expected = cursor ? cursor.nextSibling : body.firstChild;
      if (expected !== tr) body.insertBefore(tr, expected);
      cursor = tr;

      // the audit panel lives in its own row, right beneath its market
      const detailId = `detail-${key}`;
      let detail = document.getElementById(detailId);
      if (open) {
        if (!detail) {
          detail = document.createElement("tr");
          detail.id = detailId;
          detail.className = "detail-row";
          detail.innerHTML = `<td colspan="${columns.length}"></td>`;
        }
        const cell = detail.firstChild;
        const html = auditDetail(row);
        if (cell.dataset.html !== html) { cell.dataset.html = html; cell.innerHTML = html; }
        if (cursor.nextSibling !== detail) body.insertBefore(detail, cursor.nextSibling);
        cursor = detail;
      } else if (detail) {
        detail.remove();
      }
    });

    rowNodes.forEach((tr, key) => {
      if (seen.has(key)) return;
      const detail = document.getElementById(`detail-${key}`);
      if (detail) detail.remove();
      tr.remove();
      rowNodes.delete(key);
    });

    mountAuditCharts(body);
    state.boardPainted = true;
    state.lastQuoteMoves = state.quoteMoves;
    bindRowHandlers();
  }

  function bindRowHandlers() {
    if (state.rowsBound) return;
    state.rowsBound = true;
    const toggle = (tr) => {
      const key = tr.dataset.expand;
      if (!key) return;
      if (state.expanded.has(key)) state.expanded.delete(key);
      else state.expanded.add(key);
      renderTable();
      const next = els.tableBody.querySelector(`tr[data-expand="${CSS.escape(key)}"]`);
      if (next) next.focus();
    };
    els.tableBody.addEventListener("click", (event) => {
      const tr = event.target.closest("tr[data-expand]");
      if (tr) toggle(tr);
    });
    els.tableBody.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const tr = event.target.closest("tr[data-expand]");
      if (!tr) return;
      event.preventDefault();
      toggle(tr);
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
      lines.push(["Number source", "Fallback only: fighter history average. No fight-specific model number, so this row cannot be a watch."]);
    }
    if (row.context_note) lines.push(["Model note", String(row.context_note)]);

    const what = [row.phrase, row.forms && row.forms !== row.phrase ? `counts any of: ${row.forms}` : ""].filter(Boolean).join(" · ");
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
      lines.push(["Phrase trust", `Low. ${row.trust_note || "This phrase group has not shown real skill in the old-fight prediction test."} It can lean, but it cannot be a watch.`]);
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
          ? ` Edge must also stay at or under the ${formatPlainPercent(row.edge_cap)} cap. On settled cards, most bigger gaps came from the model.`
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
      <div class="audit-chart" data-chart-ticker="${escapeHtml(String(row.ticker || ""))}"></div>
      <p class="audit-title">Inside this number</p>
      ${lines.map(([label, text]) => `<div class="audit-line"><span>${escapeHtml(label)}</span><p>${escapeHtml(text)}</p></div>`).join("")}
    </div>`;
  }

  /* The expanded row gets the full price chart: the whole night of quotes
     against the model line, not just the 92px sketch in the table. */
  function chartTrackFor(ticker) {
    const stored = (data.price_tracks || {})[ticker];
    if (stored && stored.length >= 3) {
      return { pairs: stored.map((point) => [point[0], point[1]]), stamps: null, bid: null };
    }
    const market = replayMarket(ticker);
    if (!market) return null;
    const upto = replayTape() ? Math.min(replay.frame, market.ask.length - 1) : market.ask.length - 1;
    const pairs = [];
    const bid = [];
    const stamps = [];
    const tape = replayTape();
    for (let i = 0; i <= upto; i += 1) {
      pairs.push([market.ask[i], market.model[i]]);
      bid.push(market.bid ? market.bid[i] : null);
      stamps.push(tape && tape.stamps ? tape.stamps[i] : null);
    }
    return pairs.length >= 3 ? { pairs, bid, stamps } : null;
  }

  const auditChartsDrawn = new Set();

  function mountAuditCharts(root) {
    (root || document).querySelectorAll(".audit-chart").forEach((holder) => {
      if (holder.dataset.mounted) return;
      const ticker = holder.dataset.chartTicker || "";
      const track = chartTrackFor(ticker);
      if (!track) { holder.remove(); return; }
      holder.dataset.mounted = "1";
      mountPriceChart(holder, track.pairs, {
        bid: track.bid || undefined,
        stamps: track.stamps || undefined,
        label: `Price history for ${ticker}`,
        // the draw-in plays once per market, not on every replay frame
        animate: !auditChartsDrawn.has(ticker),
      });
      auditChartsDrawn.add(ticker);
    });
  }

  /* ---------- cell formatting ---------- */

  function formatCell(value, column, row) {
    if (column.badge) {
      const number = parseNumber(value);
      if (number === null) return '<span class="muted">--</span>';
      const tone = number > 0 ? "good" : number < 0 ? "bad" : "";
      return pill(formatPercent(value, column), tone);
    }
    if (column.type === "pct" || column.type === "price") return formatPercent(value, column);
    if (column.type === "lane") return laneCell(row);
    if (column.type === "phrase") return cueBox(value, row);
    if (column.type === "signal") {
      const call = String(value || "");
      let chips = "";
      if (row.watch && state.seenAtLoad && !state.seenAtLoad.has(String(row.ticker || ""))) {
        chips += ' <span class="chip-new">NEW</span>';
      }
      // One caveat mark, not a stack of boxes: the detail is in the log.
      const showChips = call.startsWith("WATCH") || call.startsWith("LEAN");
      if (showChips && row.status !== "error" && !missingPrices(row)) {
        const notes = [];
        if (row.data_risk) notes.push("thin fighter history");
        if (row.trust_ok === false) notes.push("phrase has not shown skill in the prediction test");
        if (notes.length) {
          chips += ` <span class="caveat" title="${escapeHtml(notes.join("; "))}" aria-label="${escapeHtml(notes.join("; "))}">!</span>`;
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
    return `<div class="fight-cell">${cornerKey(row.fighter_1, row.fighter_2)}<span class="fight-date">${escapeHtml(formatDate(row.event_date) || "")}</span></div>`;
  }


  function pill(value, tone) {
    if (value === null || value === undefined || value === "") return '<span class="muted">--</span>';
    return `<span class="pill ${tone || ""}">${escapeHtml(String(value))}</span>`;
  }

  /* A phrase is a line of speech, so it is set as a burned-in caption. The
     market resolves on the exact word plus its plural and possessive, and the
     extra forms are worth showing: they are what actually counts as a hit. */
  function cueBox(value, row) {
    const text = String(value || "").trim();
    if (!text) return '<span class="muted">--</span>';
    const forms = String((row && row.forms) || "")
      .split(/[|,]/).map((f) => f.trim()).filter(Boolean);
    // Caption the head word; the plural and possessive forms also settle the
    // market, so count them rather than stacking the box three lines deep.
    const head = forms[0] || text.split(/\s*\/\s*/)[0] || text;
    const extra = forms.length > 1
      ? `<span class="cue-forms" title="${escapeHtml(forms.join(", "))}">+${forms.length - 1}</span>`
      : "";
    return `<span class="cue">${escapeHtml(head)}</span>${extra}`;
  }

  /* ---------- fight page ---------- */

  function findLiveFight(eventTicker) {
    for (const card of getCards()) {
      const fight = (card.fights || []).find((f) => f.event_ticker === eventTicker);
      if (fight) return { fight, card };
    }
    return null;
  }

  function historyStrip(name) {
    const identity = identityFor(name);
    if (!identity) return "";
    const rates = identity.rates || {};
    const families = [
      ["submission", "Submission"],
      ["knockout_family", "Knockout words"],
      ["decision_family", "Decision words"],
      ["choke", "Choke"],
    ];
    const bars = families.map(([key, label]) => {
      const rate = parseNumber(rates[key]);
      if (rate === null) return "";
      return `<div class="bar-row">
        <div class="bar-label"><span>${escapeHtml(label)}</span><strong>${formatPlainPercent(rate)}</strong></div>
        <div class="bar-track"><span class="bar-fill" style="width:${Math.max(2, rate * 100)}%"></span></div>
      </div>`;
    }).filter(Boolean).join("");
    const meta = [
      identity.n_fights ? `${formatInteger(identity.n_fights)} fights in our transcript data` : "",
      identity.last_event_date ? `last ${formatDate(identity.last_event_date)}` : "",
    ].filter(Boolean).join(" · ");
    return `<article class="health-block fighter-history">
      <p class="health-kicker">${escapeHtml(identity.name)}${identity.nickname ? ` “${escapeHtml(identity.nickname)}”` : ""}</p>
      ${meta ? `<p class="health-note">${escapeHtml(meta)}</p>` : ""}
      <div class="bar-chart">${bars || '<p class="health-note">No transcript history for this fighter yet.</p>'}</div>
      <p class="health-note quiet">Share of this fighter's past fights where commentary used each word family.</p>
    </article>`;
  }

  function fightMarketTable(rows) {
    if (!rows.length) {
      return '<div class="panel"><p class="empty-block">No open mention markets for this fight right now.</p></div>';
    }
    const columns = activeColumns().filter((column) => column.key !== "matchup");
    const head = `<tr>${columns.map((c) => `<th class="${c.className || ""}">${escapeHtml(c.label)}</th>`).join("")}</tr>`;
    const body = rows.map((row) => {
      const key = String(row.ticker || "");
      const open = key && state.expanded.has(key);
      const cells = columns.map((c) => `<td class="${c.className || ""}">${formatCell(row[c.key], c, row)}</td>`).join("");
      const detail = open ? `<tr class="detail-row"><td colspan="${columns.length}">${auditDetail(row)}</td></tr>` : "";
      return `<tr class="${row.watch ? "is-watch" : ""} is-expandable ${open ? "is-open" : ""}" data-fp-expand="${escapeHtml(key)}">${cells}</tr>${detail}`;
    }).join("");
    return `<div class="panel"><div class="table-wrap"><table>
      <thead>${head}</thead><tbody>${body}</tbody>
    </table></div></div>`;
  }

  function fightPositionsTable(positions) {
    if (!positions.length) return "";
    const rows = positions.map((row) => {
      const side = String(row.paper_side || row.side || "").toLowerCase();
      const entry = parseNumber(row.paper_price);
      const settled = row.outcome === "yes" || row.outcome === "no";
      let result;
      if (settled) {
        const pnl = settledPnl(row);
        result = pill(`${side === row.outcome ? "WIN" : "LOSS"} ${formatMoney(pnl)}`, pnl > 0 ? "good" : "bad");
      } else if (row.resolution_status === "pending") {
        result = pill("PENDING", "quiet-warn");
      } else {
        result = pill("OPEN");
      }
      return `<tr>
        <td class="num muted">${escapeHtml(formatShortStamp(row.entered_at || row.tracked_at))}</td>
        <td>${pill(row.phrase || "")}</td>
        <td>${sidePill(side)}</td>
        <td class="num">${formatPlainPercent(entry)}</td>
        <td>${result}</td>
      </tr>`;
    }).join("");
    return `<h3 class="fight-section-title">Paper trades on this fight</h3>
      <div class="panel"><div class="table-wrap"><table class="tracking-table">
      <thead><tr><th>Entered</th><th>Phrase</th><th>Side</th><th class="num">Entry</th><th>Result</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div></div>`;
  }

  function renderFightPage() {
    if (!els.fightPage) return;
    if (state.tab !== "fight" || !state.fightRoute) {
      els.fightPage.innerHTML = "";
      return;
    }
    const ticker = state.fightRoute;
    const live = findLiveFight(ticker);
    const liveRows = getRows().filter((row) => row.event_ticker === ticker).map(deriveRow);
    const positions = (data.tracking_positions || []).filter((p) => p.event_ticker === ticker);
    const source = live || (positions.length ? { fight: positions[0], card: null } : null);

    if (!source) {
      els.fightPage.innerHTML = `
        <p><a class="back-link" href="#" data-fight-back>&larr; Back to markets</a></p>
        <h2>Fight not found</h2>
        <p class="fight-sub">This fight is not in the current data. It may have settled long ago or not opened yet.</p>`;
      bindFightPage();
      return;
    }

    const f1 = source.fight.fighter_1 || "";
    const f2 = source.fight.fighter_2 || "";
    const title = live ? (live.card || {}).card_title : positions[0] && positions[0].card;
    const date = live ? live.fight.event_date : "";
    const watch = liveRows.filter((row) => row.watch).length;
    const settledCount = positions.filter((p) => p.outcome === "yes" || p.outcome === "no").length;
    const subBits = [
      escapeHtml(cardLabel(title) || title || ""),
      date ? `${formatDate(date)}${tonightBadge(date)}` : "",
      liveRows.length ? `${formatInteger(liveRows.length)} phrase market${plural(liveRows.length)}` : "",
      watch ? `<span class="watch-note">${formatInteger(watch)} watch</span>` : "",
      positions.length ? `${formatInteger(positions.length)} paper trade${plural(positions.length)}${settledCount ? ` (${formatInteger(settledCount)} settled)` : ""}` : "",
    ].filter(Boolean).join(" · ");

    const hero = f1 && f2
      ? tapeHtml(f1, f2, { large: isMarquee(f1, f2) })
      : `<h2 class="matchup-hero solo">${escapeHtml(source.fight.matchup || source.fight.event_title || "Fight")}</h2>`;

    const strips = [historyStrip(f1), historyStrip(f2)].filter(Boolean).join("");

    els.fightPage.innerHTML = `
      <p><a class="back-link" href="#" data-fight-back>&larr; Back to markets</a></p>
      ${hero}
      <p class="fight-sub">${subBits}</p>
      ${liveRows.length ? '<h3 class="fight-section-title">Mention markets</h3>' : ""}
      ${fightMarketTable(liveRows)}
      ${strips ? `<h3 class="fight-section-title">Word history for both fighters</h3><div class="health-grid two">${strips}</div>` : ""}
      ${fightPositionsTable(positions)}`;
    bindFightPage();
  }

  function bindFightPage() {
    els.fightPage.querySelectorAll("[data-fight-back]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        state.fightRoute = "";
        history.replaceState(null, "", window.location.pathname + window.location.search);
        state.tab = "markets";
        renderAll();
      });
    });
    els.fightPage.querySelectorAll("tr[data-fp-expand]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const key = tr.dataset.fpExpand;
        if (!key) return;
        if (state.expanded.has(key)) state.expanded.delete(key);
        else state.expanded.add(key);
        renderFightPage();
      });
    });
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
    const ruleReplay = parseNumber(pl.current_rule_trades) !== null
      ? ` · today's rule on the same data: <span class="${toneClass(pl.current_rule_pnl)}">${formatMoney(pl.current_rule_pnl)}</span> on ${formatInteger(pl.current_rule_trades)}`
      : "";
    const plBit = pl.available
      ? `Money test: <span class="${toneClass(pl.official_pnl)}">${formatMoney(pl.official_pnl)}</span> on ${formatInteger(pl.official_trades)} old-rule trades${settledThrough ? ` (through ${settledThrough})` : ""}${ruleReplay}. ${enough ? "enough sample to review" : "still too small to trust"}`
      : "Money test: no settled markets yet";
    els.healthSummary.innerHTML = `Prediction test: ${formatInteger(prediction.groups_beating_base)} of ${formatInteger(prediction.measured_groups)} phrase groups pass · ${plBit}`;

    // The entry rule bars a group when it fails the baseline or scores under
    // 0.55 AUC — not simply because it sits at the bottom of the table.
    const barred = groups
      .filter((g) => !(g.beats_base && (parseNumber(g.auc) || 0) >= 0.55))
      .map((g) => g.phrase);
    const strongBit = (prediction.strongest || []).length
      ? `<p class="health-note">Strongest: ${escapeHtml((prediction.strongest || []).join(", "))}.${barred.length
        ? ` We bar these from watch calls (they fail the baseline or score under 0.55): ${escapeHtml(barred.join(", "))}. They can lean, but not watch.`
        : ""}</p>`
      : "";
    const weakest = prediction.weakest_phrase
      ? `<p class="health-note">Bottom of the table: <strong>${escapeHtml(prediction.weakest_phrase)}</strong> (${formatSignedDecimal(prediction.weakest_improvement)} vs baseline${parseNumber(prediction.weakest_improvement) <= 0 ? ", fails it" : ""}).</p>`
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
      ? `<p class="health-note">We tightened the entry rule after this card (edge cap + phrase trust). Replaying the same snapshots, today's rule takes ${formatInteger(pl.current_rule_trades)} trades, ${formatInteger(pl.current_rule_wins)} wins, <span class="${toneClass(pl.current_rule_pnl)}">${formatMoney(pl.current_rule_pnl)}</span>. That number is in-sample, so only the next cards can confirm it.</p>`
      : "";
    const plBlock = pl.available
      ? `
        <p class="health-big ${toneClass(pl.official_pnl)}">${formatMoney(pl.official_pnl)}<span>watch-rule paper P/L: ${formatInteger(officialTrades)} trades, ${formatInteger(pl.official_wins)} wins, $${formatDecimal2(pl.official_staked)} staked</span></p>
        <p class="health-note">Looser leans (positive edge, below the bar): ${formatInteger(pl.lean_trades)} trades, ${formatInteger(pl.lean_wins)} wins, <span class="${toneClass(pl.lean_pnl)}">${formatMoney(pl.lean_pnl)}</span>.</p>
        ${ruleBit}
        <p class="health-note">These numbers come from cards that already happened${settledThrough ? ` (latest: ${settledThrough})` : ""}: we replayed ${formatInteger(pl.markets_with_results)} settled markets from recorded live snapshots against final Kalshi results. Upcoming cards settle in on their own.</p>
        <p class="health-note">${officialTrades >= needed
          ? `Past the ${formatInteger(needed)}-trade review bar, on ${formatInteger(officialTrades)} settled trades. Trades inside one card move together, so cards are the real sample: ${formatInteger(pl.resolved_card_count || 0)} so far, and results swing hard from card to card.`
          : `${formatInteger(officialTrades)} of the ${formatInteger(needed)} settled trades needed before this means anything.`}</p>`
      : '<p class="health-note">No settled markets replayed yet. This fills in by itself after a tracked card finishes.</p>';

    // Our numbers vs what happened Settled markets, scored against the last
    // prediction the board actually showed before each card.
    const cal = health.calibration || {};
    let calBlock = "";
    if (cal.available) {
      const ece = parseNumber(cal.ece);
      const marketEce = parseNumber(cal.market_ece);
      const grade = ece === null ? "" : ece < 0.05 ? "good" : ece < 0.10 ? "" : "bad";
      const h2h = cal.head_to_head || {};
      const modelWins = parseNumber(h2h.model_log_loss) !== null
        && parseNumber(h2h.market_log_loss) !== null
        && h2h.model_log_loss < h2h.market_log_loss;
      const bins = (cal.bins || []).filter((b) => b.count >= 5);
      const worst = bins.slice().sort((a, b) =>
        Math.abs(b.actual_rate - b.mean_prediction) - Math.abs(a.actual_rate - a.mean_prediction))[0];
      const rows = bins.map((bin) => {
        const said = parseNumber(bin.mean_prediction);
        const happened = parseNumber(bin.actual_rate);
        const off = happened - said;
        const width = Math.min(100, Math.abs(off) * 260);
        return `<div class="cal-row">
          <span class="cal-band">${formatPlainPercent(bin.low)}–${formatPlainPercent(bin.high)}</span>
          <span class="cal-n">${formatInteger(bin.count)}</span>
          <span class="cal-track"><i class="${off >= 0 ? "over" : "under"}" style="width:${width.toFixed(1)}%"></i></span>
          <span class="cal-said">${formatPlainPercent(said)}</span>
          <span class="cal-happened ${Math.abs(off) > 0.1 ? (off > 0 ? "up" : "down") : ""}">${formatPlainPercent(happened)}</span>
        </div>`;
      }).join("");
      calBlock = `
        <article class="health-block is-wide">
          <p class="health-kicker">Our numbers vs what happened</p>
          <p class="health-big ${grade}">${formatDecimal3(ece)}<span>average gap between what we said and what happened, over ${formatInteger(cal.markets)} settled markets${marketEce !== null ? ` · the market itself scored ${formatDecimal3(marketEce)}` : ""}</span></p>
          <div class="ce-reliability-holder" id="reliabilityChart"></div>
          ${h2h.markets ? `<div class="h2h">
            <p class="h2h-title">Against the market, on the same pre-fight prices</p>
            <div class="h2h-rows">
              <div class="h2h-row ${modelWins ? "wins" : ""}"><span>Our number</span><b>${formatDecimal3(h2h.model_log_loss)}</b><i>AUC ${formatDecimal3(h2h.model_auc)}</i></div>
              <div class="h2h-row ${modelWins ? "" : "wins"}"><span>The market</span><b>${formatDecimal3(h2h.market_log_loss)}</b><i>AUC ${formatDecimal3(h2h.market_auc)}</i></div>
              <div class="h2h-row quiet"><span>Guessing the average</span><b>${formatDecimal3(h2h.base_log_loss)}</b><i>AUC 0.500</i></div>
            </div>
            <p class="health-note">Lower is better. We beat the market on ${formatInteger(h2h.cards_model_won)} of ${formatInteger(h2h.cards)} cards. AUC is ranking skill: the chance a market that happened was priced above one that did not.</p>
          </div>` : ""}
          ${worst ? `<p class="health-note">${Math.abs(worst.actual_rate - worst.mean_prediction) > 0.1
            ? `Worst band: at ${formatPlainPercent(worst.mean_prediction)} the board was ${worst.actual_rate > worst.mean_prediction ? "too low" : "too high"}; those markets landed ${formatPlainPercent(worst.actual_rate)}.`
            : "No band is off by more than 10 points."}</p>` : ""}
        </article>`;
    }

    // Coverage: a blank card means Kalshi ran no markets, or we were down.
    // Never let those two look the same.
    const cov = health.coverage || {};
    let covBlock = "";
    if (cov.available) {
      const missed = cov.cards_missed || 0;
      const rows = (cov.cards || []).map((card) => {
        const label = card.state === "recorded" ? "recorded"
          : card.state === "missed" ? "not recorded" : "no markets offered";
        return `<div class="cov-row ${card.state}">
          <span>${escapeHtml(formatDate(card.date) || card.date)}</span>
          <b>${label}</b>
          <i>${card.markets ? `${formatInteger(card.markets)} markets · ${formatInteger(card.snapshots)} snapshots` : "&mdash;"}</i>
        </div>`;
      }).join("");
      covBlock = `
        <article class="health-block">
          <p class="health-kicker">Recording coverage</p>
          <p class="health-big ${missed ? "bad" : "good"}">${formatInteger(cov.cards_recorded)}<span>of ${formatInteger(cov.cards_with_markets)} cards Kalshi ran since ${escapeHtml(formatDate(cov.recording_since) || cov.recording_since)}${missed ? ` · ${formatInteger(missed)} not recorded` : " · none missed"}</span></p>
          <div class="cov-table">${rows}</div>
          <p class="health-note">We check this against Kalshi's own event list. Kalshi does not open mention markets for every UFC card, so a card with none is not a gap in our recording.</p>
        </article>`;
    }

    const gate = health.v2_gate || {};
    let gateBit = "";
    if (gate.available) {
      const chosen = String(gate.chosen_variant || "v1");
      const means = gate.variant_means || {};
      const LABELS = {
        "v1": "Proven model",
        "v2": "Event-tier feature",
        "v1+calib": "Global recalibration",
        "v2+calib": "Event tier + recalibration",
        "v1+group": "Per-phrase correction",
        "v2+group": "Event tier + per-phrase",
      };
      const scored = Object.entries(means)
        .filter(([, value]) => parseNumber(value) !== null)
        .sort((a, b) => a[1] - b[1]);
      const best = scored.length ? scored[0][1] : null;
      const board = scored.map(([name, value]) => {
        const won = name === chosen;
        const delta = best !== null && value !== best ? `+${(value - best).toFixed(4)}` : "best";
        return `<div class="gate-row${won ? " is-chosen" : ""}">
          <span class="gate-name">${escapeHtml(LABELS[name] || name)}</span>
          <span class="gate-score">${value.toFixed(4)}</span>
          <span class="gate-delta">${escapeHtml(delta)}</span>
          ${won ? '<span class="gate-flag">live</span>' : ""}
        </div>`;
      }).join("");
      const cards = (gate.holdout_cards || []).length;
      gateBit = `
        <p class="health-note">We score each candidate on ${cards ? `${formatInteger(cards)} card${plural(cards)} it has ` : "cards it has "}not seen, fitting any correction on earlier cards. Lower is better, and we ship a candidate only if it wins.</p>
        <div class="gate-board">${board}</div>
        <p class="health-note quiet">${chosen === "v1"
          ? "Nothing has beaten the proven model, so it stays."
          : `Running <strong>${escapeHtml(LABELS[chosen] || chosen)}</strong>${gate.group_bias_groups ? ` across ${formatInteger(gate.group_bias_groups)} phrase groups` : ""}.`}</p>`;
    }
    const wf = health.walkforward || {};
    let wfBit = "";
    if (wf.available) {
      const chosen = parseNumber(wf.chosen_weight);
      const better = parseNumber(wf.chosen_log_loss) !== null && parseNumber(wf.baseline_log_loss) !== null
        && wf.chosen_log_loss < wf.baseline_log_loss;
      wfBit = chosen > 0
        ? `<p class="health-note">Weekly retrain: the model now trains on ${formatInteger(wf.labels_count)} settled-card results (weight ${chosen}). On held-out cards this scored ${formatDecimal3(wf.chosen_log_loss)} log loss vs ${formatDecimal3(wf.baseline_log_loss)} without them${better ? ", an improvement" : ""}.</p>`
        : `<p class="health-note">Weekly retrain: we front-tested ${formatInteger(wf.labels_count)} settled-card results, but plain transcripts still scored better on held-out cards, so we leave them out for now. This recheck runs after every card.</p>`;
    }
    els.healthGrid.innerHTML = `
      <article class="health-block">
        <p class="health-kicker">Prediction test (old fights)</p>
        <p class="health-big">${formatInteger(prediction.groups_beating_base)}<span> of ${formatInteger(prediction.measured_groups)} phrase groups beat the simple average</span></p>
        <p class="health-note">We scored ${formatInteger(prediction.prediction_rows)} old fight predictions across ${formatInteger(prediction.folds)} time-ordered folds. This measures guessing quality, not profit.</p>
        ${strongBit}
        ${wfBit}
        ${gateBit}
      </article>
      <article class="health-block">
        <p class="health-kicker">By phrase group (higher is better)</p>
        <div class="bar-chart">${groupBars}</div>
      </article>
      <article class="health-block">
        <p class="health-kicker">Money test</p>
        <p class="health-warn">${enough ? "Enough sample to review" : "Still too small to trust"}</p>
        ${plBlock}
      </article>
      ${covBlock}
      ${calBlock}`;
    const reliabilityHolder = document.getElementById("reliabilityChart");
    if (reliabilityHolder) mountReliabilityChart(reliabilityHolder, cal);
  }

  /* ---------- paper tracking ---------- */

  function renderTracking() {
    const cards = data.tracking_cards || [];
    const positions = data.tracking_positions || [];

    if (!cards.length) {
      els.trackingSummary.textContent = "Nothing tracked yet. The tracker logs new watch rows here on its own.";
      els.trackingCards.innerHTML = "";
      if (els.paperStats) els.paperStats.innerHTML = "";
      els.trackingBody.innerHTML = '<tr><td class="tracking-empty" colspan="8">The tracker has logged no paper entries yet. It adds one pretend contract the first time a market becomes a watch.</td></tr>';
      return;
    }

    const summary = data.summary || {};
    els.trackingSummary.innerHTML = [
      `${formatInteger(summary.tracking_card_count)} card${plural(summary.tracking_card_count)}`,
      `${formatInteger(summary.tracking_official_trade_count)} paper trades`,
      `${formatInteger(summary.tracking_pending_count)} pending`,
      `P/L <span class="${toneClass(summary.tracking_official_pnl)}">${formatMoney(summary.tracking_official_pnl)}</span>`,
    ].join(" · ");

    if (els.paperStats) {
      const settled = positions.filter((row) => row.outcome === "yes" || row.outcome === "no");
      const wins = settled.filter((row) => String(row.paper_side || row.side || "").toLowerCase() === row.outcome).length;
      const realized = settled.reduce((sum, row) => sum + settledPnl(row), 0);
      const open = positions.length - settled.length;
      const winRate = settled.length ? `${Math.round(wins / settled.length * 100)}%` : "--";
      els.paperStats.innerHTML = `
        <div class="stat-tile"><strong class="${toneClass(realized)}">${formatMoney(realized)}</strong><span>tracker P/L · realized</span></div>
        <div class="stat-tile"><strong>${winRate}</strong><span>tracker win rate</span></div>
        <div class="stat-tile"><strong>${formatInteger(settled.length)}</strong><span>settled</span></div>
        <div class="stat-tile"><strong>${formatInteger(open)}</strong><span>open</span></div>`;
    }

    // Two ledgers, deliberately: say so rather than let the totals look wrong.
    const ledger = document.getElementById("ledgerNote");
    if (ledger) {
      const pl = (data.model_health || {}).pl || {};
      ledger.textContent = pl.available
        ? `Tracker: one pretend contract the first time a market became a watch, including entries made under the older rule. The chart below and the Model page replay today's rule over recorded snapshots instead (${formatInteger(pl.official_trades)} trades, ${formatMoney(pl.official_pnl)}), so the two totals differ on purpose.`
        : "Tracker: one pretend contract the first time a market became a watch.";
    }

    els.trackingCards.innerHTML = cards.map((card) => {
      const officialPnl = parseNumber(card.official_pnl);
      const leanPnl = parseNumber(card.lean_pnl);
      return `<article class="tracking-card">
        <p class="tracking-date">${escapeHtml(formatDate(card.settled_at ? String(card.settled_at).slice(0, 10) : "") || "in progress")}</p>
        <h3>${escapeHtml(cardLabel(card.card) || card.label || card.card)}</h3>
        <div class="tracking-card-stats">
          <span><strong>${formatInteger(card.official_trades)}</strong> trades</span>
          <span><strong>${formatInteger(card.leans)}</strong> leans</span>
          <span><strong>${formatInteger(card.pending)}</strong> pending</span>
          <span class="${pnlClass(officialPnl)}"><strong>${formatMoney(officialPnl)}</strong> trade P/L</span>
          <span class="${pnlClass(leanPnl)}"><strong>${formatMoney(leanPnl)}</strong> lean P/L</span>
        </div>
      </article>`;
    }).join("");

    const liveByTicker = new Map(getRows().map((row) => [row.ticker, row]));
    const shown = positions
      .slice()
      .sort((a, b) => String(b.entered_at || b.tracked_at || "").localeCompare(String(a.entered_at || a.tracked_at || "")));
    if (!shown.length) {
      els.trackingBody.innerHTML = '<tr><td class="tracking-empty" colspan="8">No paper entries logged yet.</td></tr>';
      return;
    }
    els.trackingBody.innerHTML = shown.map((row) => {
      const side = String(row.paper_side || row.side || "").toLowerCase();
      const entry = parseNumber(row.paper_price);
      const settled = row.outcome === "yes" || row.outcome === "no";
      const live = liveByTicker.get(row.ticker);
      const now = !settled && live ? parseNumber(side === "yes" ? live.yes_bid : live.no_bid) : null;
      const move = now !== null && entry !== null ? now - entry : null;
      let result;
      if (settled) {
        const pnl = settledPnl(row);
        result = pill(`${side === row.outcome ? "WIN" : "LOSS"} ${formatMoney(pnl)}`, pnl > 0 ? "good" : "bad");
      } else if (row.resolution_status === "pending") {
        result = pill("PENDING", "quiet-warn");
      } else {
        result = pill("OPEN");
      }
      return `<tr>
        <td class="num muted">${escapeHtml(formatShortStamp(row.entered_at || row.tracked_at))}</td>
        <td><div class="fight-cell stacked"><a class="fight-link" href="#fight/${encodeURIComponent(row.event_ticker || "")}">${cornerKey(row.fighter_1, row.fighter_2)}</a><span class="fight-date">${escapeHtml(cardLabel(row.card))}</span></div></td>
        <td>${pill(row.phrase || "")}</td>
        <td>${sidePill(side)}</td>
        <td class="num">${formatPlainPercent(entry)}</td>
        <td class="num">${now === null ? '<span class="muted">--</span>' : formatPlainPercent(now)}</td>
        <td class="num">${move === null ? '<span class="muted">--</span>' : `<span class="${toneClass(move)}">${formatPlainPercent(move, true)}</span>`}</td>
        <td>${result}</td>
      </tr>`;
    }).join("");
  }

  /* ---------- performance charts ---------- */

  function equityChartSvg(equity) {
    if (equity.length < 2) return "";
    const width = 620;
    const height = 170;
    const pad = { top: 18, right: 76, bottom: 26, left: 14 };
    const values = equity.map((e) => e.cumulative_pnl);
    const min = Math.min(0, ...values);
    const max = Math.max(0, ...values);
    const span = (max - min) || 1;
    const x = (i) => pad.left + (i / (equity.length - 1)) * (width - pad.left - pad.right);
    const y = (v) => pad.top + (1 - (v - min) / span) * (height - pad.top - pad.bottom);

    let path = `M ${x(0)} ${y(0)}`;
    equity.forEach((point, i) => {
      path += ` L ${x(i)} ${y(equity[Math.max(0, i - 1)].cumulative_pnl)} L ${x(i)} ${y(point.cumulative_pnl)}`;
    });

    const dots = equity.map((point, i) => {
      const tone = point.cumulative_pnl >= 0 ? "var(--pos)" : "var(--neg)";
      return `<circle cx="${x(i)}" cy="${y(point.cumulative_pnl)}" r="3.5" fill="${tone}">
        <title>${escapeHtml(formatDate(point.date))}: card ${escapeHtml(formatMoney(point.card_pnl))}, total ${escapeHtml(formatMoney(point.cumulative_pnl))}</title>
      </circle>`;
    }).join("");

    const last = equity[equity.length - 1];
    const lastTone = last.cumulative_pnl >= 0 ? "var(--pos)" : "var(--neg)";
    const zeroY = y(0);
    const firstLabel = formatDate(equity[0].date);
    const lastLabel = formatDate(last.date);

    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Cumulative paper profit across settled cards">
      <line x1="${pad.left}" y1="${zeroY}" x2="${width - pad.right}" y2="${zeroY}" stroke="var(--rule)" stroke-width="1" stroke-dasharray="1 3"/>
      <path d="${path}" fill="none" stroke="var(--muted)" stroke-width="2" stroke-linejoin="round"/>
      ${dots}
      <text x="${x(equity.length - 1) + 10}" y="${y(last.cumulative_pnl) + 4}" fill="${lastTone}" font-size="14" font-weight="650" font-family="var(--mono)">${escapeHtml(formatMoney(last.cumulative_pnl))}</text>
      <text x="${pad.left}" y="${height - 8}" fill="var(--faint)" font-size="10.5" font-family="var(--mono)">${escapeHtml(firstLabel)}</text>
      <text x="${width - pad.right}" y="${height - 8}" fill="var(--faint)" font-size="10.5" font-family="var(--mono)" text-anchor="end">${escapeHtml(lastLabel)}</text>
    </svg>`;
  }

  function renderPerformance() {
    const holder = document.getElementById("performanceCharts");
    if (!holder) return;
    const perf = data.performance || {};
    const equity = perf.equity || [];
    const phrases = perf.by_phrase || [];
    if (!equity.length && !phrases.length) { holder.innerHTML = ""; return; }

    const chart = equityChartSvg(equity);
    const equityBlock = chart
      ? `<article class="health-block perf-block">
          <p class="health-kicker">Paper P/L by settled card</p>
          ${chart}
          <p class="health-note quiet">Cumulative watch-rule paper profit, one step per settled event date. Hover a point for that card.</p>
        </article>`
      : "";

    const maxAbs = Math.max(...phrases.map((p) => Math.abs(p.pnl)), 0.0001);
    // Sorted by P/L descending, so a plain head-slice would hide every loser.
    // Keep the best and worst ends: those are the two a reader needs.
    const shownPhrases = phrases.length > 12
      ? phrases.slice(0, 8).concat(phrases.slice(-4))
      : phrases;
    const phraseRows = shownPhrases.map((p) => {
      const width = Math.max(2, Math.abs(p.pnl) / maxAbs * 100);
      const rate = p.trades ? Math.round(p.wins / p.trades * 100) : 0;
      return `<div class="bar-row" title="${escapeHtml(p.phrase)}: ${formatInteger(p.trades)} trades, ${rate}% wins, ${escapeHtml(formatMoney(p.pnl))}">
        <div class="bar-label"><span>${escapeHtml(p.phrase)} · ${formatInteger(p.trades)}</span><strong class="${toneClass(p.pnl)}">${escapeHtml(formatMoney(p.pnl))} · ${rate}%</strong></div>
        <div class="bar-track"><span class="bar-fill ${p.pnl >= 0 ? "good" : "bad"}" style="width:${width}%"></span></div>
      </div>`;
    }).join("");
    const phraseBlock = phrases.length
      ? `<article class="health-block perf-block">
          <p class="health-kicker">P/L by phrase (settled trades · win rate)</p>
          <div id="phraseBars"></div>
        </article>`
      : "";

    holder.innerHTML = equityBlock + phraseBlock;
    const phraseHolder = document.getElementById("phraseBars");
    // The engine draws every phrase on one shared zero axis; pass the full
    // list, not the head-and-tail slice the old bars needed.
    if (phraseHolder) mountDivergingBars(phraseHolder, phrases);
  }

  /* Paper cards are stored as folder slugs ("ufc_card_2026-07-18"). Show the
     card's real name when the schedule knows it, else a plain date. */
  function cardLabel(slug) {
    const text = String(slug || "").trim();
    if (!text) return "";
    const date = (text.match(/(\d{4}-\d{2}-\d{2})/) || [])[1];
    if (!date) return text;
    const named = (data.upcoming_events || []).find((event) => event.date === date);
    if (named && named.name) return named.name;
    const card = getCards().find((item) => item.event_date === date);
    if (card && card.card_title && !/^UFC card/.test(card.card_title)) return card.card_title;
    return formatDate(date) || date;
  }

  function formatShortStamp(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
    return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
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

  function formatDecimal3(value) {
    const number = parseNumber(value);
    return number === null ? "--" : number.toFixed(3);
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
    // The published site can only be as fresh as its publish cadence, so
    // judging it by the local 30s poll would flag it stale forever.
    if (window.STATIC_SITE) return ageSeconds > 25 * 60;
    // A card-day cycle prices dozens of books and can run past a minute, so
    // judge against several cycles rather than crying stale between refreshes.
    const limit = expected > 0 ? Math.max(300, expected * 6) : 1800;
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

/* ================= chart engine: price time series =================
   mountPriceChart(container, pairs, opts)
     container : block element the chart fills (width measured at mount)
     pairs     : array of [ask, model] floats in 0..1 (null = no print)
     opts      : {
       bid: number[]        optional, same length as pairs, draws the spread band
       stamps: string[]     optional ISO timestamps for clock labels + tooltip
       label: string        accessible label for the figure
       askName: string      legend copy override (default MARKET ASK)
       modelName: string    legend copy override (default MODEL)
       animate: boolean     false skips the one-shot draw-in (used on resize)
     }
   This block also defines the shared ce* helpers used by the reliability
   diagram and the diverging bars, so it must sit above them in app.js.
   Depends on escapeHtml() from app.js. All colors come from CSS tokens. */

  let ceUid = 0;

  function ceReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function ceNum(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function ceCents(value) {
    return value === null ? "--" : `${Math.round(value * 100)}¢`;
  }

  function ceSignedCents(value) {
    if (value === null) return "--";
    const cents = Math.round(value * 100);
    return `${cents > 0 ? "+" : ""}${cents}¢`;
  }

  function ceMoney(value) {
    const number = ceNum(value);
    if (number === null) return "$0.00";
    const sign = number > 0 ? "+" : number < 0 ? "-" : "";
    return `${sign}$${Math.abs(number).toFixed(2)}`;
  }

  function ceClock(stamp) {
    if (!stamp) return "";
    const date = new Date(stamp);
    if (Number.isNaN(date.getTime())) return String(stamp);
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  /* One-shot draw-in. Solid paths tagged data-draw sweep in via dasharray.
     Dashed or filled layers tagged data-draw-fade fade in with a stagger
     driven by the .ce-pre class so each lands on its own CSS opacity.
     Inline styles are cleaned afterwards: nothing keeps animating. */
  function ceAnimateIn(svg) {
    if (ceReducedMotion()) return;
    svg.querySelectorAll("[data-draw]").forEach((path) => {
      if (!path.getAttribute("d")) return;
      const length = path.getTotalLength ? path.getTotalLength() : 0;
      if (!length) return;
      path.style.strokeDasharray = String(length);
      path.style.strokeDashoffset = String(length);
      path.getBoundingClientRect();
      path.style.transition = "stroke-dashoffset 450ms cubic-bezier(0.22, 1, 0.36, 1)";
      path.style.strokeDashoffset = "0";
      window.setTimeout(() => {
        path.style.strokeDasharray = "";
        path.style.strokeDashoffset = "";
        path.style.transition = "";
      }, 600);
    });
    const fades = svg.querySelectorAll("[data-draw-fade]");
    if (fades.length) {
      svg.classList.add("ce-pre");
      fades.forEach((node, index) => { node.style.transitionDelay = `${120 + index * 60}ms`; });
      svg.getBoundingClientRect();
      svg.classList.remove("ce-pre");
      window.setTimeout(() => { fades.forEach((node) => { node.style.transitionDelay = ""; }); }, 1400);
    }
  }

  function mountPriceChart(container, pairs, opts = {}) {
    if (container.__ceRO) { container.__ceRO.disconnect(); container.__ceRO = null; }

    const bids = Array.isArray(opts.bid) ? opts.bid : null;
    const stamps = Array.isArray(opts.stamps) ? opts.stamps : null;
    let points = (pairs || []).map((pair, i) => ({
      ask: ceNum(pair && pair[0]),
      model: ceNum(pair && pair[1]),
      bid: bids ? ceNum(bids[i]) : null,
      stamp: stamps ? stamps[i] : null,
    }));
    // Cap the DOM cost: 480 kept points is denser than any screen can show.
    if (points.length > 480) {
      const step = points.length / 480;
      const kept = [];
      for (let k = 0; k < 480; k += 1) kept.push(points[Math.floor(k * step)]);
      kept[kept.length - 1] = points[points.length - 1];
      points = kept;
    }
    const n = points.length;
    const alive = points.some((p) => p.ask !== null || p.model !== null);
    if (!alive) {
      container.innerHTML = `<div class="ce-empty">
        <span class="ce-empty-mark">--¢</span>
        <strong>No price history</strong>
        <span>Points land here the next time this market prints.</span>
      </div>`;
      return;
    }

    const uid = ++ceUid;
    const width = Math.max(320, Math.round(container.getBoundingClientRect().width) || 960);
    const height = Math.max(150, Math.round(width * 5 / 16));
    const pad = { top: 14, right: 78, bottom: 26, left: 48 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;
    const floorY = pad.top + plotH;

    const vals = [];
    points.forEach((p) => {
      if (p.ask !== null) vals.push(p.ask);
      if (p.bid !== null) vals.push(p.bid);
      if (p.model !== null) vals.push(p.model);
    });
    let lo = Math.min(...vals);
    let hi = Math.max(...vals);
    const breathe = Math.max(0.03, (hi - lo) * 0.12);
    lo = Math.max(0, lo - breathe);
    hi = Math.min(1, hi + breathe);
    if (hi - lo < 0.06) {
      const mid = (hi + lo) / 2;
      lo = Math.max(0, mid - 0.04);
      hi = Math.min(1, mid + 0.04);
    }

    const x = (i) => (n === 1 ? pad.left + plotW / 2 : pad.left + (i / (n - 1)) * plotW);
    const y = (v) => pad.top + (1 - (v - lo) / (hi - lo)) * plotH;

    // Pen-up line building: null values break the stroke instead of lying
    // across the gap with an interpolated segment.
    const linePath = (key) => {
      let d = "";
      let pen = false;
      for (let i = 0; i < n; i += 1) {
        const v = points[i][key];
        if (v === null) { pen = false; continue; }
        d += `${pen ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)} `;
        pen = true;
      }
      return d.trim();
    };

    const runsOf = (test) => {
      const runs = [];
      let run = [];
      for (let i = 0; i < n; i += 1) {
        if (test(points[i])) run.push(i);
        else if (run.length) { runs.push(run); run = []; }
      }
      if (run.length) runs.push(run);
      return runs;
    };

    const areaPath = runsOf((p) => p.ask !== null).filter((r) => r.length > 1).map((run) => {
      const top = run.map((i) => `${x(i).toFixed(1)} ${y(points[i].ask).toFixed(1)}`).join(" L");
      return `M${x(run[0]).toFixed(1)} ${floorY} L${top} L${x(run[run.length - 1]).toFixed(1)} ${floorY} Z`;
    }).join(" ");

    const bandPath = runsOf((p) => p.ask !== null && p.bid !== null).filter((r) => r.length > 1).map((run) => {
      const fwd = run.map((i) => `${x(i).toFixed(1)} ${y(points[i].ask).toFixed(1)}`).join(" L");
      const back = run.slice().reverse().map((i) => `${x(i).toFixed(1)} ${y(points[i].bid).toFixed(1)}`).join(" L");
      return `M${fwd} L${back} Z`;
    }).join(" ");

    // A point with null neighbors draws no stroke, so give it a dot.
    const lonely = (key) => points.map((p, i) => {
      if (p[key] === null) return "";
      const before = i > 0 ? points[i - 1][key] : null;
      const after = i < n - 1 ? points[i + 1][key] : null;
      if (before !== null || after !== null) return "";
      return `<circle cx="${x(i).toFixed(1)}" cy="${y(p[key]).toFixed(1)}" r="3" fill="${key === "ask" ? "var(--acid)" : "var(--ink)"}"/>`;
    }).join("");

    const ticks = [0, 1, 2, 3].map((step) => {
      const v = lo + ((hi - lo) * step) / 3;
      const ty = y(v);
      return `<line x1="${pad.left}" y1="${ty.toFixed(1)}" x2="${width - pad.right}" y2="${ty.toFixed(1)}" class="ce-grid"/>
        <text x="${pad.left - 8}" y="${(ty + 3.5).toFixed(1)}" class="ce-tick" text-anchor="end">${Math.round(v * 100)}¢</text>`;
    }).join("");

    let lastAskIndex = -1;
    for (let i = n - 1; i >= 0; i -= 1) { if (points[i].ask !== null) { lastAskIndex = i; break; } }
    let flag = "";
    if (lastAskIndex >= 0) {
      const fy = y(points[lastAskIndex].ask);
      const flagY = Math.max(pad.top + 12, Math.min(floorY - 12, fy));
      flag = `<g data-draw-fade>
        <line x1="${x(lastAskIndex).toFixed(1)}" y1="${fy.toFixed(1)}" x2="${width - pad.right + 6}" y2="${flagY.toFixed(1)}" class="ce-leader"/>
        <g class="ce-flag">
          <rect x="${width - pad.right + 6}" y="${(flagY - 12).toFixed(1)}" width="60" height="24"/>
          <text x="${width - pad.right + 36}" y="${(flagY + 4.5).toFixed(1)}" text-anchor="middle">${ceCents(points[lastAskIndex].ask)}</text>
        </g>
      </g>`;
    }

    const firstStamp = points[0].stamp ? ceClock(points[0].stamp) : "";
    const lastStamp = points[n - 1].stamp ? ceClock(points[n - 1].stamp) : "";

    container.classList.add("ce-host");
    container.innerHTML = `
      <figure class="ce-wrap" tabindex="0" role="group"
        aria-label="${escapeHtml(opts.label || "Price history: market ask against model probability. Arrow keys step the crosshair.")}">
        <svg viewBox="0 0 ${width} ${height}" class="ce-svg" aria-hidden="true">
          <defs>
            <linearGradient id="ceFill${uid}" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stop-color="var(--acid)" stop-opacity="0.22"/>
              <stop offset="1" stop-color="var(--acid)" stop-opacity="0"/>
            </linearGradient>
          </defs>
          ${ticks}
          ${bandPath ? `<path d="${bandPath}" class="ce-band" data-draw-fade/>` : ""}
          ${areaPath ? `<path d="${areaPath}" fill="url(#ceFill${uid})" class="ce-area" data-draw-fade/>` : ""}
          <path d="${linePath("model")}" class="ce-line ce-line-model" data-draw-fade/>
          <path d="${linePath("ask")}" class="ce-line ce-line-ask" data-draw/>
          ${lonely("model")}${lonely("ask")}
          ${flag}
          <g class="ce-cross" data-cross opacity="0">
            <line y1="${pad.top}" y2="${floorY}" class="ce-cross-line"/>
            <circle r="4.5" class="ce-dot-model"/>
            <circle r="4.5" class="ce-dot-ask"/>
          </g>
          ${firstStamp ? `<text x="${pad.left}" y="${height - 7}" class="ce-tick">${escapeHtml(firstStamp)}</text>` : ""}
          ${lastStamp ? `<text x="${width - pad.right}" y="${height - 7}" class="ce-tick" text-anchor="end">${escapeHtml(lastStamp)}</text>` : ""}
        </svg>
        <div class="ce-tip" hidden></div>
        <figcaption class="ce-legend">
          <span><i class="ce-key ce-key-ask"></i>${escapeHtml(opts.askName || "Market ask")}</span>
          <span><i class="ce-key ce-key-model"></i>${escapeHtml(opts.modelName || "Model")}</span>
          ${bandPath ? '<span><i class="ce-key ce-key-band"></i>Bid/ask spread</span>' : ""}
        </figcaption>
      </figure>`;

    const wrap = container.querySelector(".ce-wrap");
    const svg = container.querySelector(".ce-svg");
    const cross = container.querySelector("[data-cross]");
    const crossLine = cross.querySelector("line");
    const dotAsk = cross.querySelector(".ce-dot-ask");
    const dotModel = cross.querySelector(".ce-dot-model");
    const tip = container.querySelector(".ce-tip");
    let cursor = -1;

    const showIndex = (index) => {
      cursor = index;
      const p = points[index];
      const cx = x(index);
      cross.setAttribute("opacity", "1");
      crossLine.setAttribute("x1", cx);
      crossLine.setAttribute("x2", cx);
      if (p.ask !== null) {
        dotAsk.setAttribute("cx", cx);
        dotAsk.setAttribute("cy", y(p.ask));
        dotAsk.setAttribute("opacity", "1");
      } else dotAsk.setAttribute("opacity", "0");
      if (p.model !== null) {
        dotModel.setAttribute("cx", cx);
        dotModel.setAttribute("cy", y(p.model));
        dotModel.setAttribute("opacity", "1");
      } else dotModel.setAttribute("opacity", "0");
      const edge = p.ask !== null && p.model !== null ? p.model - p.ask : null;
      tip.innerHTML = `
        <strong>${escapeHtml(p.stamp ? ceClock(p.stamp) : `PT ${index + 1}/${n}`)}</strong>
        <span>ASK <b>${ceCents(p.ask)}</b></span>
        ${p.bid !== null ? `<span>BID <b>${ceCents(p.bid)}</b></span>` : ""}
        <span>MODEL <b>${ceCents(p.model)}</b></span>
        ${edge !== null ? `<span>EDGE <b class="${edge >= 0 ? "ce-up" : "ce-down"}">${ceSignedCents(edge)}</b></span>` : ""}`;
      tip.hidden = false;
      tip.style.left = `${(cx / width) * 100}%`;
      tip.classList.toggle("ce-tip-flip", cx > width * 0.6);
    };

    const hideCross = () => {
      cursor = -1;
      cross.setAttribute("opacity", "0");
      tip.hidden = true;
    };

    // One delegated pointer handler per chart. clientX is rescaled into
    // viewBox space so the map survives any responsive resize of the SVG.
    svg.addEventListener("pointermove", (event) => {
      const rect = svg.getBoundingClientRect();
      if (!rect.width) return;
      const px = ((event.clientX - rect.left) / rect.width) * width;
      const frac = plotW > 0 ? (px - pad.left) / plotW : 0;
      showIndex(Math.max(0, Math.min(n - 1, Math.round(frac * (n - 1)))));
    });
    svg.addEventListener("pointerleave", hideCross);
    wrap.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        const step = event.key === "ArrowLeft" ? -1 : 1;
        showIndex(Math.max(0, Math.min(n - 1, (cursor < 0 ? n - 1 : cursor) + step)));
      } else if (event.key === "Escape") {
        hideCross();
      }
    });
    wrap.addEventListener("blur", hideCross);

    if (opts.animate !== false) ceAnimateIn(svg);

    // Re-render (without replaying the entrance) when the container width
    // actually changes; small jitters are ignored.
    if (window.ResizeObserver) {
      let lastWidth = width;
      let timer = 0;
      const observer = new ResizeObserver(() => {
        const w = Math.round(container.getBoundingClientRect().width);
        if (!w || Math.abs(w - lastWidth) < 12) return;
        lastWidth = w;
        window.clearTimeout(timer);
        timer = window.setTimeout(() => {
          mountPriceChart(container, pairs, Object.assign({}, opts, { animate: false }));
        }, 120);
      });
      observer.observe(container);
      container.__ceRO = observer;
    }
  }
/* ================= chart engine: reliability diagram =================
   mountReliabilityChart(container, calibration)
     calibration : data.model_health.calibration
       { bins: [{ low, high, count, mean_prediction, actual_rate }],
         ece, market_ece, markets }  (extras optional)
   Square plot, diagonal = perfect calibration, one dot per non-empty bin,
   dot area scaled by bin count, stem shows the miss distance to the
   diagonal. Dots within 5 cents of the line read as gain, misses as loss,
   so color is never the only channel: the stem length carries it too.
   Hovering a dot rewrites the readout strip below (delegated handler);
   native <title> is the fallback. Needs the ce* helpers from the price
   chart block above it. */

  function mountReliabilityChart(container, calibration) {
    const source = calibration || {};
    const bins = (source.bins || []).filter((bin) => (ceNum(bin.count) || 0) > 0);
    if (!bins.length) {
      container.innerHTML = `<div class="ce-empty">
        <span class="ce-empty-mark">0/0</span>
        <strong>No calibration data</strong>
        <span>Bins appear after the first settled card.</span>
      </div>`;
      return;
    }

    const width = Math.max(280, Math.round(container.getBoundingClientRect().width) || 420);
    const size = Math.min(width, 460);
    const pad = { top: 14, right: 16, bottom: 42, left: 46 };
    const plot = size - pad.left - pad.right;
    const height = pad.top + plot + pad.bottom;
    const x = (v) => pad.left + v * plot;
    const y = (v) => pad.top + (1 - v) * plot;
    const clamp01 = (v) => Math.max(0, Math.min(1, v));
    const maxCount = Math.max(...bins.map((bin) => bin.count));

    const grid = [0.25, 0.5, 0.75].map((v) => `
      <line x1="${x(v).toFixed(1)}" y1="${y(0).toFixed(1)}" x2="${x(v).toFixed(1)}" y2="${y(1).toFixed(1)}" class="ce-grid"/>
      <line x1="${x(0).toFixed(1)}" y1="${y(v).toFixed(1)}" x2="${x(1).toFixed(1)}" y2="${y(v).toFixed(1)}" class="ce-grid"/>`).join("");

    const axisTicks = [0, 0.5, 1].map((v) => `
      <text x="${x(v).toFixed(1)}" y="${(y(0) + 16).toFixed(1)}" class="ce-tick" text-anchor="middle">${Math.round(v * 100)}</text>
      <text x="${pad.left - 8}" y="${(y(v) + 3.5).toFixed(1)}" class="ce-tick" text-anchor="end">${Math.round(v * 100)}</text>`).join("");

    const dots = bins.map((bin, i) => {
      const px = x(clamp01(bin.mean_prediction));
      const py = y(clamp01(bin.actual_rate));
      const diagY = y(clamp01(bin.mean_prediction));
      const gap = bin.actual_rate - bin.mean_prediction;
      const r = 5 + Math.sqrt(bin.count / maxCount) * 11;
      const tone = Math.abs(gap) <= 0.05 ? "ce-cal-good" : "ce-cal-off";
      return `<g data-draw-fade>
        <line x1="${px.toFixed(1)}" y1="${py.toFixed(1)}" x2="${px.toFixed(1)}" y2="${diagY.toFixed(1)}" class="ce-cal-stem"/>
        <circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="${r.toFixed(1)}" class="ce-cal-dot ${tone}" data-cal="${i}">
          <title>${Math.round(bin.low * 100)}-${Math.round(bin.high * 100)}¢ bin: model ${ceCents(bin.mean_prediction)}, actual ${ceCents(bin.actual_rate)}, n=${bin.count}</title>
        </circle>
      </g>`;
    }).join("");

    const ece = ceNum(source.ece);
    const marketEce = ceNum(source.market_ece);
    const markets = ceNum(source.markets);
    const baseReadout = [
      ece !== null ? `MODEL ECE ${(ece * 100).toFixed(1)}` : "",
      marketEce !== null ? `MARKET ECE ${(marketEce * 100).toFixed(1)}` : "",
      markets !== null ? `${markets} MARKETS SCORED` : "",
      "DOT SIZE = BIN COUNT",
    ].filter(Boolean).join(" · ");

    container.classList.add("ce-host");
    container.innerHTML = `
      <figure class="ce-wrap" tabindex="0" role="group"
        aria-label="Reliability diagram. Model predicted probability on the horizontal axis, realized rate on the vertical axis. Dots on the diagonal are perfectly calibrated. Dot size shows how many markets fell in each bin.">
        <svg viewBox="0 0 ${size} ${height}" class="ce-svg ce-svg-cal" aria-hidden="true">
          ${grid}
          <rect x="${pad.left}" y="${pad.top}" width="${plot}" height="${plot}" class="ce-frame"/>
          <line x1="${x(0).toFixed(1)}" y1="${y(0).toFixed(1)}" x2="${x(1).toFixed(1)}" y2="${y(1).toFixed(1)}" class="ce-diag" data-draw-fade/>
          ${dots}
          ${axisTicks}
          <text x="${x(0.5).toFixed(1)}" y="${height - 8}" class="ce-axis" text-anchor="middle">MODEL SAID (¢)</text>
          <text x="12" y="${y(0.5).toFixed(1)}" class="ce-axis" text-anchor="middle" transform="rotate(-90 12 ${y(0.5).toFixed(1)})">IT HAPPENED (%)</text>
        </svg>
        <figcaption class="ce-readout" data-readout>${baseReadout}</figcaption>
      </figure>`;

    const svg = container.querySelector(".ce-svg");
    const readout = container.querySelector("[data-readout]");
    const rest = readout.innerHTML;
    svg.addEventListener("pointerover", (event) => {
      const target = event.target.closest ? event.target.closest("[data-cal]") : null;
      if (!target) return;
      const bin = bins[Number(target.dataset.cal)];
      if (!bin) return;
      const gap = bin.actual_rate - bin.mean_prediction;
      readout.innerHTML = `<b>${Math.round(bin.low * 100)}-${Math.round(bin.high * 100)}¢ BIN</b>` +
        ` · N=${bin.count}` +
        ` · MODEL ${ceCents(bin.mean_prediction)}` +
        ` · ACTUAL ${ceCents(bin.actual_rate)}` +
        ` · GAP <b class="${Math.abs(gap) <= 0.05 ? "ce-up" : "ce-down"}">${ceSignedCents(gap)}</b>`;
    });
    svg.addEventListener("pointerout", (event) => {
      if (event.target.closest && event.target.closest("[data-cal]")) readout.innerHTML = rest;
    });

    ceAnimateIn(svg);
  }
/* ================= chart engine: diverging phrase bars =================
   mountDivergingBars(container, rows)
     rows : data.performance.by_phrase, [{ phrase, trades, wins, pnl }],
            already sorted by P/L descending upstream.
   Horizontal bars diverge from a shared zero axis. The axis sits where the
   data puts it (maxNeg / span) so both sides use the same dollars-per-pixel
   scale: no side is visually inflated. Values and win rates are always
   visible in fixed columns, per the skill's bar guidance. Bars animate
   width once on mount via a class flip; reduced motion renders instantly.
   Needs the ce* helpers from the price chart block above it, plus
   escapeHtml() from app.js. */

  function mountDivergingBars(container, rows) {
    const items = (rows || []).filter((row) => ceNum(row.pnl) !== null);
    if (!items.length) {
      container.innerHTML = `<div class="ce-empty">
        <span class="ce-empty-mark">$0.00</span>
        <strong>No settled trades</strong>
        <span>Phrase P/L shows up after the first card settles.</span>
      </div>`;
      return;
    }

    const maxPos = Math.max(0, ...items.map((row) => ceNum(row.pnl)));
    const maxNeg = Math.max(0, ...items.map((row) => -ceNum(row.pnl)));
    const span = (maxPos + maxNeg) || 1;
    const zero = maxNeg / span;
    const reduce = ceReducedMotion();

    const bars = items.map((row, i) => {
      const pnl = ceNum(row.pnl) || 0;
      const trades = ceNum(row.trades) || 0;
      const wins = ceNum(row.wins) || 0;
      const widthPct = Math.max(0.6, (Math.abs(pnl) / span) * 100);
      const pos = pnl >= 0;
      const rate = trades ? Math.round((wins / trades) * 100) : 0;
      const anchor = pos ? "left:var(--dv-zero)" : "right:calc(100% - var(--dv-zero))";
      return `<div class="dv-row" title="${escapeHtml(row.phrase)}: ${trades} trades, ${rate}% wins, ${escapeHtml(ceMoney(pnl))}">
        <span class="dv-phrase">${escapeHtml(row.phrase)}</span>
        <span class="dv-track">
          <i class="dv-zero"></i>
          <i class="dv-bar ${pos ? "dv-pos" : "dv-neg"}" style="${anchor};--dv-w:${widthPct.toFixed(2)}%;transition-delay:${reduce ? 0 : i * 35}ms"></i>
        </span>
        <span class="dv-val ${pos ? "ce-up" : "ce-down"}">${escapeHtml(ceMoney(pnl))}</span>
        <span class="dv-meta">${trades} TR · ${rate}%</span>
      </div>`;
    }).join("");

    const scale = `<div class="dv-row dv-scale-row" aria-hidden="true">
      <span class="dv-lead"></span>
      <span class="dv-track dv-scale">
        ${maxNeg > 0 ? `<span class="dv-scale-min">-$${maxNeg.toFixed(2)}</span>` : ""}
        <span class="dv-scale-zero">$0</span>
        ${maxPos > 0 ? `<span class="dv-scale-max">+$${maxPos.toFixed(2)}</span>` : ""}
      </span>
      <span></span>
      <span></span>
    </div>`;

    container.classList.add("ce-host");
    container.innerHTML = `<div class="dv-chart" style="--dv-zero:${(zero * 100).toFixed(2)}%"
      role="group" aria-label="Paper profit and loss by phrase. Bars right of the zero axis are profitable, bars left of it are losses. Exact values are printed beside each bar.">
      ${bars}
      ${scale}
    </div>`;

    const chart = container.querySelector(".dv-chart");
    if (reduce) {
      chart.classList.add("dv-in");
    } else {
      // Double rAF: first frame paints the zero-width bars, second flips
      // the class so every bar transitions from a committed initial state.
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => chart.classList.add("dv-in"));
      });
    }
  }

  init();
})();
