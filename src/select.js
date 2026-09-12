/* Selectors over the payload, and the formatters every section shares.
   Nothing here touches the DOM. */
window.MM = window.MM || {};

MM.fmt = (function () {
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);

  function money(v, opts) {
    const o = Object.assign({ sign: false, digits: 2 }, opts || {});
    if (!isNum(v)) return "";
    const abs = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: o.digits, maximumFractionDigits: o.digits });
    if (v < 0) return "−$" + abs;
    return (o.sign && v > 0 ? "+" : "") + "$" + abs;
  }
  function pct(v, opts) {
    const o = Object.assign({ sign: false, digits: 1 }, opts || {});
    if (!isNum(v)) return "";
    const s = (Math.abs(v) * 100).toFixed(o.digits) + "%";
    if (v < 0) return "−" + s;
    return (o.sign && v > 0 ? "+" : "") + s;
  }
  const prob = (p) => (isNum(p) ? Math.round(p * 100) + "%" : "");
  const cents = (p) => (isNum(p) ? Math.round(p * 100) + "¢" : "");
  const points = (d) => (isNum(d) ? (d > 0 ? "+" : d < 0 ? "−" : "") + Math.abs(Math.round(d * 100)) + " pts" : "");
  const num3 = (v) => (isNum(v) ? v.toFixed(3) : "");

  function parse(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  /* "2026-07-18" -> "Jul 18"; with year -> "Jul 18, 2026" */
  function dateShort(ymd, withYear) {
    if (!ymd) return "";
    const [y, m, d] = String(ymd).slice(0, 10).split("-").map(Number);
    if (!y || !m || !d) return "";
    return MONTHS[m - 1] + " " + d + (withYear ? ", " + y : "");
  }
  function weekday(ymd) {
    const d = parse(ymd + "T12:00:00Z");
    return d ? d.toLocaleDateString("en-US", { weekday: "long", timeZone: "UTC" }) : "";
  }
  /* A timestamp on the tape: "Jul 17, 8:14 PM" */
  function stamp(iso, opts) {
    const d = parse(iso);
    if (!d) return "";
    const o = Object.assign({ time: true }, opts || {});
    const date = MONTHS[d.getMonth()] + " " + d.getDate();
    if (!o.time) return date;
    return date + ", " + d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  }
  const plural = (n, one, many) => n + " " + (n === 1 ? one : many || one + "s");
  /* "Dricus Du Plessis" -> "Du Plessis"; "Islam Makhachev" -> "Makhachev". */
  const PARTICLES = new Set(["du", "de", "da", "dos", "das", "del", "della", "di", "van", "von", "der", "den", "la", "le", "al", "el", "bin", "ibn", "st.", "st", "mc", "mac", "o'"]);
  const lastName = (name) => {
    const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "";
    if (parts.length >= 2 && PARTICLES.has(parts[parts.length - 2].toLowerCase())) return parts.slice(-2).join(" ");
    return parts[parts.length - 1];
  };

  return { money, pct, prob, cents, points, num3, dateShort, weekday, stamp, plural, lastName, isNum };
})();

MM.select = (function () {
  const data = () => window.UFC_MENTION_DASHBOARD_DATA || {};
  let cache = null;

  function marquee(name) {
    const f = (data().fighters || {})[String(name || "").toLowerCase()];
    return f && MM.fmt.isNum(f.marquee_score) ? f.marquee_score : 0;
  }

  function buildNights() {
    const tapes = Array.isArray(data().tapes) ? data().tapes : [];
    const equity = Array.isArray((data().performance || {}).equity) ? data().performance.equity : [];
    const pnlByDate = {};
    equity.forEach((e) => { pnlByDate[e.date] = e.card_pnl; });
    // Trade tallies come from the ledger, the same rows the book and the
    // record use, so every count on the page agrees.
    const ledger = Array.isArray(data().trades) ? data().trades : [];
    const nights = tapes.map((tape) => {
      const nightTrades = ledger.filter((t) => t.event_date === tape.event_date);
      const byFight = new Map();
      (tape.markets || []).forEach((m) => {
        const key = m.event_ticker;
        if (!byFight.has(key)) {
          byFight.set(key, { event_ticker: key, fighter_1: m.fighter_1, fighter_2: m.fighter_2, markets: [], marquee: marquee(m.fighter_1) + marquee(m.fighter_2) });
        }
        byFight.get(key).markets.push(m);
      });
      const fights = Array.from(byFight.values()).sort((a, b) => b.marquee - a.marquee || a.event_ticker.localeCompare(b.event_ticker));
      fights.forEach((f) => {
        f.said = f.markets.filter((m) => m.result === "yes").length;
        const fightTrades = nightTrades.filter((t) => t.event_ticker === f.event_ticker);
        f.trades = fightTrades.length;
        f.pnl = fightTrades.reduce((s, t) => s + (MM.fmt.isNum(t.pnl) ? t.pnl : 0), 0);
      });
      const main = fights[0];
      const trades = nightTrades;
      const wins = trades.filter((t) => t.won).length;
      const staked = trades.reduce((s, t) => s + (MM.fmt.isNum(t.price) ? t.price : 0), 0);
      const pnl = MM.fmt.isNum(pnlByDate[tape.event_date]) ? pnlByDate[tape.event_date] : trades.reduce((s, t) => s + (MM.fmt.isNum(t.pnl) ? t.pnl : 0), 0);
      return {
        card: tape.card,
        date: tape.event_date,
        label: MM.fmt.dateShort(tape.event_date),
        title: main ? MM.fmt.lastName(main.fighter_1) + " vs " + MM.fmt.lastName(main.fighter_2) : tape.card,
        main,
        fights,
        markets: tape.markets || [],
        stamps: tape.stamps || [],
        frames: tape.frames || (tape.stamps || []).length,
        said: tape.said || 0,
        settled: tape.settled || 0,
        trades: trades.length,
        wins,
        staked,
        pnl,
      };
    });
    nights.sort((a, b) => a.date.localeCompare(b.date));
    return nights;
  }

  function nights() {
    if (!cache) cache = buildNights();
    return cache;
  }
  const night = (card) => nights().find((n) => n.card === card) || null;
  const latestNight = () => { const n = nights(); return n.length ? n[n.length - 1] : null; };

  function market(ticker) {
    for (const n of nights()) {
      for (const f of n.fights) {
        const m = f.markets.find((x) => x.ticker === ticker);
        if (m) return { night: n, fight: f, market: m };
      }
    }
    return null;
  }

  /* Every market on every night, flat, for search and prev/next. */
  function allMarkets() {
    const out = [];
    nights().forEach((n) => n.fights.forEach((f) => f.markets.forEach((m) => out.push({ night: n, fight: f, market: m }))));
    return out;
  }

  function book() {
    const pl = (data().model_health || {}).pl || {};
    const perf = data().performance || {};
    const ns = nights();
    const trades = ns.reduce((s, n) => s + n.trades, 0);
    const wins = ns.reduce((s, n) => s + n.wins, 0);
    const staked = MM.fmt.isNum(pl.official_staked) ? pl.official_staked : ns.reduce((s, n) => s + n.staked, 0);
    const pnl = MM.fmt.isNum(pl.official_pnl) ? pl.official_pnl : ns.reduce((s, n) => s + n.pnl, 0);
    return {
      pnl,
      staked,
      ret: staked > 0 ? pnl / staked : null,
      trades: MM.fmt.isNum(pl.official_trades) ? pl.official_trades : trades,
      wins: MM.fmt.isNum(pl.official_wins) ? pl.official_wins : wins,
      equity: Array.isArray(perf.equity) ? perf.equity : [],
      byPhrase: Array.isArray(perf.by_phrase) ? perf.by_phrase : [],
      entryRule: pl.entry_rule || "",
      note: pl.note || "",
      latestSettled: pl.latest_settled_event_date || "",
    };
  }

  function model() {
    const h = data().model_health || {};
    const cal = h.calibration || {};
    const gate = h.v2_gate || {};
    return {
      calibration: cal,
      headToHead: cal.head_to_head || {},
      groups: Array.isArray(h.groups) ? h.groups.slice().sort((a, b) => (b.auc || 0) - (a.auc || 0)) : [],
      gate,
      walkforward: h.walkforward || {},
      prediction: h.prediction || {},
      coverage: h.coverage || {},
      transcripts: MM.fmt.isNum((data().kalshi_audit_summary || {}).valid_fights) ? data().kalshi_audit_summary.valid_fights : null,
    };
  }

  const trades = () => (Array.isArray(data().trades) ? data().trades : []);
  const build = () => data().build || {};
  const generatedAt = () => data().generated_at || "";

  return { data, nights, night, latestNight, market, allMarkets, book, model, trades, build, generatedAt };
})();
