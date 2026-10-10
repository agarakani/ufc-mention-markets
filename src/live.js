/* Current cards and quotes. The collector records trades; the page never does. */
window.MM = window.MM || {};

MM.live = (function () {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const number = value => typeof value === 'number' && Number.isFinite(value);
  const probability = value => number(value) && value >= 0 && value <= 1;
  const cents = value => probability(value) ? `${Math.round(value * 100)}¢` : 'No quote';
  const percent = value => probability(value) ? `${Math.round(value * 100)}%` : 'No estimate';
  const money = value => number(value) ? `${value < 0 ? '-' : value > 0 ? '+' : ''}$${Math.abs(value).toFixed(2)}` : 'Pending';
  const stamp = value => Date.parse(value || '');
  const fresh = (value, now) => Number.isFinite(stamp(value)) && now - stamp(value) >= -60000 && now - stamp(value) <= 120000;
  const isoDay = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '');
  const shortDate = value => isoDay(value) ? new Date(value + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) : 'Date TBD';
  const dayDate = value => isoDay(value) ? new Date(value + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' }) : 'Date TBD';
  const longDate = value => isoDay(value) ? new Date(value + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC' }) : 'Date TBD';
  const weekday = value => isoDay(value) ? new Date(value + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'long', timeZone: 'UTC' }) : '';
  // Calendar days from the viewer's local date to the card date.
  const daysUntil = (value, now) => {
    if (!isoDay(value)) return null;
    const today = new Date(now);
    const from = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
    return Math.round((Date.parse(value + 'T00:00:00Z') - from) / 86400000);
  };
  const localStamp = value => Number.isFinite(stamp(value)) ? new Date(value).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '';
  const url = value => { try { const u = new URL(value); return u.protocol === 'https:' ? u.href : ''; } catch (_) { return ''; } };
  const list = value => Array.isArray(value) ? value : [];
  function officialUrl(value, media = false) {
    try {
      const parsed = new URL(value);
      return parsed.protocol === 'https:' && ['ufc.com', 'www.ufc.com'].includes(parsed.hostname) && !parsed.username && !parsed.password && !parsed.port && parsed.pathname.startsWith(media ? '/images/' : '/event/') ? parsed.href : '';
    } catch (_) { return ''; }
  }

  function poster(card, failedImages) {
    const title = String(card.card_title || 'UFC card');
    const number = title.match(/\bUFC\s+(\d{2,4})\b/i)?.[1] || '';
    const kind = number ? 'numbered' : /\bUFC\s+Fight\s+Night\b/i.test(title) ? 'fight-night' : 'event';
    const p = officialUrl(card.presentation?.source_url) ? card.presentation : {};
    const headliners = list(p.headliners).length === 2 && p.headliners.every(fighter => fighter && typeof fighter.name === 'string' && fighter.name.trim()) ? p.headliners : [];
    const championship = p.is_title_bout === true && typeof p.bout_label === 'string' && /\btitle\b/i.test(p.bout_label) && headliners.length === 2;
    const palette = ['ice', 'copper', 'crimson', 'ink'];
    const hash = Array.from(String(card.card_id || card.event_date || title)).reduce((value, char) => (value * 31 + char.charCodeAt(0)) >>> 0, 0);
    const tone = championship ? 'amber' : palette[hash % palette.length];
    const portraits = headliners.map(fighter => ({ url: officialUrl(fighter.image_url, true), alt: fighter.image_alt || fighter.name }));
    const artwork = officialUrl(p.artwork?.url, true);
    const useArtwork = artwork && !failedImages.has(artwork);
    const pair = !useArtwork && portraits.length === 2 && portraits.every(image => image.url && !failedImages.has(image.url));
    const images = useArtwork ? [{ url: artwork, alt: p.artwork.alt || title }] : pair ? portraits : [];
    const rematch = headliners.length === 2 ? title.match(/\bvs\.?\s+.+?\s+([2-9])$/i)?.[1] || '' : '';
    return { title, number: number || (kind === 'fight-night' ? 'FN' : 'UFC'), kind, tone, championship, label: number ? `UFC ${number}` : kind === 'fight-night' ? 'UFC Fight Night' : 'UFC', headliners, rematch, bout: championship ? p.bout_label : '', images, pair };
  }

  function currentCards(data, now) {
    const today = new Date(now).toISOString().slice(0, 10);
    const cards = list(data.kalshi_cards).map(card => ({ ...card, fights: list(card.fights) }));
    for (const event of list(data.upcoming_events)) {
      if (!event.date || !event.name) continue;
      const card = cards.find(item => item.event_date === event.date);
      if (card) {
        card.source_url = card.source_url || event.source_url;
        card.entry_deadline = card.entry_deadline || event.entry_deadline;
        card.venue = card.venue || event.venue;
        card.location = card.location || event.location;
        card.presentation = card.presentation || event.presentation;
      } else cards.push({ card_id: `schedule-${event.date}`, card_title: event.name, event_date: event.date, fights: [], source_url: event.source_url, venue: event.venue, location: event.location, entry_deadline: event.entry_deadline, presentation: event.presentation });
    }
    return cards.filter(card => card.event_date >= today || stamp(card.entry_deadline) + 12 * 3600000 > now)
      .sort((a, b) => String(a.event_date).localeCompare(String(b.event_date)));
  }

  function marketView(row, card, data, now, failed) {
    const model = row.probability_source === 'fight_context_model' && probability(row.model_probability) ? row.model_probability : null;
    const sides = [];
    if (model !== null && probability(row.yes_ask)) sides.push({ side: 'YES', price: row.yes_ask, edge: model - row.yes_ask });
    if (model !== null && probability(row.no_ask)) sides.push({ side: 'NO', price: row.no_ask, edge: 1 - model - row.no_ask });
    sides.sort((a, b) => b.edge - a.edge);
    const best = sides[0] || { side: '', edge: null };
    const stale = failed || !fresh(row.quote_timestamp || row.snapshot_timestamp, now);
    const closed = !['active', 'open'].includes(row.market_status);
    const deadline = stamp(card.entry_deadline);
    const preFight = Number.isFinite(deadline) && deadline > now;
    const live = data.live_status || {};
    const collector = live.paper_enabled === true && fresh(live.collector_checked_at || live.checked_at, now) && live.source !== 'cloud' && !live.error;
    const entry = list(data.tracking_positions).find(p => p.ticker === row.ticker && p.paper_action === 'trade');
    let call = 'No entry';
    if (entry) call = 'Paper entry recorded';
    else if (stale) call = 'Old quote';
    else if (closed) call = 'Market closed';
    else if (model === null) call = 'No fight estimate';
    else if (!preFight) call = Number.isFinite(deadline) ? 'Entries closed' : 'Start time unverified';
    else if (row.paper_eligible === false) call = 'Entry blocked';
    else if (!collector) call = 'Collector not confirmed';
    else if (row.watch === true && best.side && best.edge > 0) call = 'Meets entry rule';
    return { ...best, model, stale, call, entry };
  }

  function mount(container, options) {
    const opts = { now: () => Date.now(), autoStart: true, ...options };
    const local = location.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
    let runtime = local ? { source: 'local', paper_enabled: false, checked_at: '', error: 'Local collector not checked yet' } : null;
    let data = window.UFC_MENTION_DASHBOARD_DATA || {};
    let busy = false, failed = false, disposed = false, timer = null;
    const selected = new Map();
    const opened = new Map();
    const expandedWords = new Set();
    const scrollOffsets = new Map();
    const failedImages = new Set();

    function withRuntime(snapshot) {
      return runtime ? { ...snapshot, live_status: { ...snapshot.live_status, ...runtime, collector_checked_at: runtime.checked_at } } : snapshot;
    }
    data = withRuntime(data);

    function rowsHtml(card, fight) {
      const rows = list(data.kalshi).filter(row => row.event_ticker === fight.event_ticker);
      if (!rows.length) return '<p class="live-empty">No mention prices are available for this fight yet.</p>';
      return `<div class="live-market-wrap"><table class="live-markets"><caption class="visually-hidden">Mention buy prices for ${esc(fight.matchup)}</caption>
        <thead><tr><th scope="col">Phrase</th><th scope="col">Our YES chance</th><th scope="col">Buy YES</th><th scope="col">Buy NO</th><th scope="col">Model side</th><th scope="col">Edge</th><th scope="col">Paper call</th></tr></thead>
        <tbody>${rows.map(row => {
          const view = marketView(row, card, data, opts.now(), failed);
          const reason = view.model === null ? 'A fight-specific estimate is not available.' : `Our model gives YES a ${percent(view.model)} chance and NO a ${percent(1 - view.model)} chance.${view.side ? ` The larger price gap is ${view.side} at ${cents(view.price)}.` : ''}${number(row.hurdle) ? ` The entry rule requires more than ${(row.hurdle * 100).toFixed(1)} points of edge.` : ''}`;
          const checked = row.quote_timestamp || row.snapshot_timestamp;
          const when = Number.isFinite(stamp(checked)) ? new Date(checked).toLocaleString() : 'Unknown';
          const auditId = `live-audit-${encodeURIComponent(row.ticker)}`;
          const expanded = expandedWords.has(row.ticker);
          return `<tr class="${view.stale ? 'quote-stale' : ''}"><td><button type="button" class="phrase-rule" data-word="${esc(row.ticker)}" aria-expanded="${expanded}" aria-controls="${esc(auditId)}">${esc(row.phrase || 'Unnamed phrase')}</button></td>
            <td class="live-price">${percent(view.model)}</td><td class="live-price">${cents(row.yes_ask)}</td><td class="live-price">${cents(row.no_ask)}</td><td class="live-side">${view.side || 'None'}</td>
            <td class="live-edge ${number(view.edge) && view.edge > 0 && !view.stale ? 'up' : ''}">${number(view.edge) ? `${view.edge > 0 ? '+' : ''}${(view.edge * 100).toFixed(1)} pts` : 'Unavailable'}</td><td class="live-call">${view.call}</td></tr>
            <tr class="live-audit-row" id="${esc(auditId)}" ${expanded ? '' : 'hidden'}><td colspan="7"><div class="live-audit"><p>${esc(reason)}</p>${row.data_risk ? '<p>Limited fighter history. A higher entry bar applies.</p>' : ''}${row.paper_block_reason || row.block_reason ? `<p>Entry check: ${esc(String(row.paper_block_reason || row.block_reason).replace(/_/g, ' '))}.</p>` : ''}${row.rules_primary ? `<p>${esc(row.rules_primary)}</p>` : ''}<p>Quote checked: ${esc(when)}.</p></div></td></tr>`;
        }).join('')}</tbody></table></div><p class="live-note">YES and NO are the buy prices in cents. A price gap is a model estimate, not proof of a profitable trade. Click a phrase for the calculation and rules.</p>`;
    }

    function scheduleLine(cards) {
      if (!cards.length) return 'No cards are on the schedule in this snapshot.';
      const first = cards[0];
      const last = cards[cards.length - 1];
      const days = daysUntil(first.event_date, opts.now());
      const when = days === null ? 'not dated yet' : days < 0 ? 'under way' : days === 0 ? 'tonight' : days === 1 ? 'tomorrow' : `${weekday(first.event_date)}, in ${days} days`;
      const span = cards.length > 1 ? ` ${cards.length} cards are scheduled through ${shortDate(last.event_date)}.` : '';
      return `The next card is ${when}.${span}`;
    }

    function factsHtml(card) {
      // UFC lists "Los Angeles, CA United States"; the country adds nothing for a US venue.
      const place = [card.venue, String(card.location || '').replace(/,?\s*United States$/i, '').trim()].filter(Boolean).join(', ');
      const facts = [
        ['Date', longDate(card.event_date)],
        ['Where', place],
        ['Entries close', localStamp(card.entry_deadline)],
      ].filter(([, value]) => value && value !== 'Date TBD');
      return `<div class="event-detail">${facts.length ? `<dl class="event-facts">${facts.map(([term, value]) => `<div><dt>${esc(term)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>` : ''}<p class="live-empty">No mention markets are in the latest Kalshi check. Fights and phrases will appear here when they are listed.</p></div>`;
    }

    function ctaLabel(open, fightCount) {
      return open ? 'Close card' : fightCount > 0 ? 'Explore card' : 'Card details';
    }

    function cardHtml(card, index) {
      const id = String(card.card_id || card.event_date);
      const fights = list(card.fights).filter(f => f.event_ticker);
      const chosen = fights.find(f => f.event_ticker === selected.get(id)) || fights[0];
      if (chosen) selected.set(id, chosen.event_ticker);
      const count = list(data.kalshi).filter(row => fights.some(f => f.event_ticker === row.event_ticker)).length;
      const source = url(card.source_url);
      const status = count ? `${fights.length} ${fights.length === 1 ? 'fight' : 'fights'} · ${count} phrases` : 'Mention markets not listed';
      const art = poster(card, failedImages);
      const isOpen = opened.has(id) ? opened.get(id) : index === 0 && count > 0;
      const names = art.headliners.map((fighter, side) => {
        const name = fighter.name.trim();
        const words = name.split(/\s+/);
        const surnameAt = Math.max(0, words.length - (/^(?:Jr\.?|Sr\.?|II|III|IV)$/i.test(words.at(-1)) ? 2 : 1));
        const headline = typeof fighter.display_name === 'string' && fighter.display_name.trim() || words.slice(surnameAt).join(' ');
        const given = name === headline ? '' : name.endsWith(` ${headline}`) ? name.slice(0, -headline.length).trim() : name;
        return `<span class="event-fighter">${given ? `<span class="event-fighter-given">${esc(given)} </span>` : ''}${esc(headline)}${side && art.rematch ? ` ${art.rematch}` : ''}</span>`;
      }).join('<span class="event-versus" aria-label="versus">vs</span>');
      const fallbackTitle = /\bTBD\b/i.test(art.title) ? 'Main event to be announced' : art.title;
      return `<details class="event-card" data-card="${esc(id)}" data-kind="${art.kind}" data-tone="${art.tone}" data-featured="${index === 0}" data-art="${art.images.length > 0}" data-championship="${art.championship}" data-fights="${fights.length}" ${isOpen ? 'open' : ''}>
        <summary class="event-poster" aria-label="${esc(art.title)}, ${shortDate(card.event_date)}. ${status}.">
          ${art.images.length ? `<span class="event-poster-art ${art.pair ? 'event-portraits' : ''}" aria-hidden="true">${art.images.map((image, side) => `<img ${art.pair ? `class="event-portrait ${side ? 'fighter-right' : 'fighter-left'}"` : ''} src="${esc(image.url)}" alt="${esc(image.alt)}" loading="${index === 0 ? 'eager' : 'lazy'}" decoding="async" ${index === 0 && side === 0 ? 'fetchpriority="high"' : ''}>`).join('')}</span>` : ''}
          <span class="event-poster-number" aria-hidden="true">${art.number}</span>
          <div class="event-poster-copy"><div class="event-poster-topline"><span class="event-card-kicker">${art.label}</span><span class="event-card-date"><time datetime="${esc(card.event_date)}">${dayDate(card.event_date)}</time></span></div>
            ${art.bout ? `<span class="event-title-bout">${esc(art.bout)}</span>` : ''}<h2 class="event-card-title">${names || esc(fallbackTitle)}</h2>${card.venue ? `<span class="event-card-venue">${esc(card.venue)}</span>` : ''}</div>
          <div class="event-poster-foot"><span class="event-card-meta">${status}</span><span class="event-card-cta"><span class="event-card-cta-label">${ctaLabel(isOpen, fights.length)}</span><span aria-hidden="true">↓</span></span></div>
        </summary>
        <div class="event-fights">${(fights.length && card.venue) || source ? `<p class="event-location">${esc(fights.length ? (card.venue || '') : '')}${source ? ` <a href="${esc(source)}" target="_blank" rel="noopener noreferrer">Official card page ↗</a>` : ''}${art.images.length ? '<span class="event-photo-credit">Images from UFC</span>' : ''}</p>` : ''}
        ${fights.length ? `<div class="fight-switch" role="group" aria-label="Choose a fight">${fights.map(fight => `<button type="button" class="fight-tab" data-card="${esc(id)}" data-fight="${esc(fight.event_ticker)}" aria-pressed="${fight === chosen}">${esc(fight.matchup || [fight.fighter_1, fight.fighter_2].filter(Boolean).join(' vs ') || 'Fight details pending')}</button>`).join('')}</div>${rowsHtml(card, chosen)}` : factsHtml(card)}
        </div></details>`;
    }

    function paperHtml(cards) {
      const tickers = new Set(cards.flatMap(card => list(card.fights).map(f => f.event_ticker)));
      const positions = list(data.tracking_positions).filter(p => p.paper_action === 'trade' && tickers.has(p.event_ticker));
      const live = data.live_status || {};
      const ready = !failed && !live.error && live.paper_enabled === true && live.source !== 'cloud' && fresh(live.collector_checked_at || live.checked_at, opts.now());
      const label = ready ? 'Paper collector on' : 'Paper collector not confirmed';
      const tradeable = cards.some(card => list(card.fights).some(f => f.event_ticker));
      if (!positions.length && !tradeable) {
        return `<section class="paper-live is-quiet" aria-labelledby="paperLiveTitle"><h2 id="paperLiveTitle" class="visually-hidden">Paper trading</h2><p>${label}. Paper entries start when Kalshi lists a mention market. No real orders are placed.</p></section>`;
      }
      return `<section class="paper-live" aria-labelledby="paperLiveTitle"><div><h2 id="paperLiveTitle">Paper trading</h2><p>${label}. ${ready ? 'Entries are recorded automatically when a fresh quote clears the rule before card start.' : 'New entries are not confirmed while the collector is unavailable or its status is old.'} No real orders are placed.</p></div>
        ${positions.length ? `<div class="live-market-wrap"><table class="live-markets"><caption class="visually-hidden">Paper entries for current cards</caption><thead><tr><th>Fight / phrase</th><th>Side</th><th>Entry</th><th>Contracts</th><th>Result</th><th>Paper P/L</th></tr></thead><tbody>${positions.map(p => `<tr><td>${esc(p.matchup || p.event_title)}<br><strong>${esc(p.phrase)}</strong></td><td>${esc(String(p.paper_side || '').toUpperCase())}</td><td>${cents(p.paper_price)}</td><td>${number(p.paper_contracts) ? p.paper_contracts : 'Not recorded'}</td><td>${['yes', 'no'].includes(p.outcome) ? `Resolved ${esc(p.outcome.toUpperCase())}` : p.resolution_status === 'pending' ? 'Awaiting settlement' : 'Open'}</td><td>${money(p.paper_pnl)}</td></tr>`).join('')}</tbody></table></div>` : '<p class="live-empty">No paper entries for the upcoming cards yet.</p>'}
        <p class="live-note">Paper entries use saved buy quotes. Actual fills are not guaranteed. Historical testing is kept separately below.</p></section>`;
    }

    function render() {
      if (disposed) return;
      const active = container.contains(document.activeElement) ? document.activeElement : null;
      const focus = active ? { id: active.id, fight: active.dataset.fight, card: active.dataset.card, summaryCard: active.matches('.event-card > summary') ? active.parentElement.dataset.card : null, word: active.closest('.phrase-rule')?.dataset.word, link: active.matches('a') ? active.href : null, linkCard: active.closest('.event-card')?.dataset.card } : null;
      const scrollKey = element => {
        const card = element.closest('.event-card');
        return card ? `${card.dataset.card}/${card.querySelector('[data-fight][aria-pressed="true"]')?.dataset.fight}` : 'paper';
      };
      container.querySelectorAll('.live-market-wrap').forEach(el => scrollOffsets.set(scrollKey(el), el.scrollLeft));
      container.querySelectorAll('.event-card').forEach(el => opened.set(el.dataset.card, el.open));
      const cards = currentCards(data, opts.now());
      const live = data.live_status || {};
      const checked = live.checked_at || data.kalshi_meta?.snapshot_timestamp || data.summary?.kalshi_snapshot_timestamp;
      const recent = fresh(checked, opts.now());
      const checkedText = Number.isFinite(stamp(checked)) ? `Checked ${new Date(checked).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}` : 'Waiting for first check';
      const state = failed || live.error ? 'error' : recent ? 'ready' : 'stale';
      container.setAttribute('aria-busy', String(busy));
      container.innerHTML = `<header class="live-head"><div class="live-head-copy"><h1 class="live-title" id="liveTitle">Upcoming cards</h1><p class="live-sub">${esc(scheduleLine(cards))}</p></div><div class="live-tools"><p class="live-status" data-state="${state}" role="status">${busy ? 'Checking for updates...' : failed ? 'Update failed. Showing the last snapshot.' : live.error ? 'Collector check failed. Showing saved data.' : `${checkedText}${recent ? '' : ' · update overdue'}`}</p><button class="live-refresh" id="liveRefresh" type="button" aria-disabled="${busy}">Check for updates</button></div></header>
        <div class="live-cards">${cards.map(cardHtml).join('') || '<div class="live-empty"><h2>Checking the schedule.</h2><p>No upcoming cards are available in this snapshot. The page checks for a fresh one automatically.</p></div>'}</div>${paperHtml(cards)}`;
      if (focus) {
        const target = focus.id ? document.getElementById(focus.id) : focus.summaryCard ? Array.from(container.querySelectorAll('.event-card')).find(el => el.dataset.card === focus.summaryCard)?.querySelector('summary') : focus.word ? Array.from(container.querySelectorAll('.phrase-rule')).find(el => el.dataset.word === focus.word) : focus.link ? Array.from(container.querySelectorAll('.event-location a')).find(el => el.href === focus.link && el.closest('.event-card').dataset.card === focus.linkCard) : Array.from(container.querySelectorAll('[data-fight]')).find(el => el.dataset.fight === focus.fight && el.dataset.card === focus.card);
        target?.focus({ preventScroll: true });
      }
      container.querySelectorAll('.live-market-wrap').forEach(el => { el.scrollLeft = scrollOffsets.get(scrollKey(el)) || 0; });
    }

    function update(next) {
      if (!next || typeof next !== 'object' || Array.isArray(next)) throw new Error('Invalid snapshot');
      data = withRuntime(next);
      window.UFC_MENTION_DASHBOARD_DATA = data;
      failed = false;
      render();
      opts.onData?.(data);
    }

    async function runtimeRequest(path) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 30000);
      try {
        const response = await fetch(path, { cache: 'no-store', signal: controller.signal });
        const result = await response.json();
        if (!response.ok || result?.ok !== true) throw new Error('Local collector unavailable');
        return result;
      } finally { clearTimeout(timeout); }
    }

    async function loadSnapshot() {
      if (location.protocol === 'file:') {
        return new Promise((resolve, reject) => {
          const script = document.createElement('script');
          const timeout = setTimeout(() => { script.remove(); reject(new Error('Snapshot timed out')); }, 15000);
          script.src = `data.js?v=${Date.now()}`;
          script.onload = () => { clearTimeout(timeout); script.remove(); resolve(window.UFC_MENTION_DASHBOARD_DATA); };
          script.onerror = () => { clearTimeout(timeout); script.remove(); reject(new Error('Snapshot unavailable')); };
          document.body.appendChild(script);
        });
      }
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await fetch(`data.js?v=${Date.now()}`, { cache: 'no-store', signal: controller.signal });
        if (!response.ok) throw new Error('Snapshot unavailable');
        const text = (await response.text()).trim();
        const prefix = 'window.UFC_MENTION_DASHBOARD_DATA = ';
        if (!text.startsWith(prefix)) throw new Error('Invalid snapshot');
        return JSON.parse(text.slice(prefix.length).replace(/;\s*$/, ''));
      } finally { clearTimeout(timeout); }
    }

    async function refresh(force = true) {
      if (busy || disposed) return;
      busy = true;
      render();
      try {
        if (local && force) await runtimeRequest('/api/refresh');
        const next = await loadSnapshot();
        if (local) {
          try {
            const status = (await runtimeRequest('/api/status')).live_status;
            if (!status || typeof status.paper_enabled !== 'boolean' || typeof status.checked_at !== 'string' || !['ready', 'refreshing'].includes(status.state)) throw new Error('Invalid local status');
            runtime = { ...status, source: 'local' };
          } catch (_) { runtime = { source: 'local', paper_enabled: false, checked_at: '', error: 'Local collector unavailable' }; }
        }
        if (!disposed) update(next);
      }
      catch (_) {
        if (local) runtime = { source: 'local', paper_enabled: false, checked_at: '', error: 'Local collector unavailable' };
        if (!disposed) update(data);
        failed = true;
      }
      finally { busy = false; render(); }
    }

    function click(event) {
      if (event.target.closest('#liveRefresh')) { refresh(); return; }
      const phrase = event.target.closest('.phrase-rule');
      if (phrase) {
        const word = phrase.dataset.word;
        if (expandedWords.has(word)) expandedWords.delete(word); else expandedWords.add(word);
        render();
        return;
      }
      const button = event.target.closest('[data-fight]');
      if (button) { selected.set(button.dataset.card, button.dataset.fight); render(); }
    }
    function imageError(event) {
      if (!event.target.matches?.('.event-poster-art img')) return;
      failedImages.add(event.target.src);
      render();
    }
    function toggleCard(event) {
      if (!event.target.matches?.('.event-card')) return;
      opened.set(event.target.dataset.card, event.target.open);
      event.target.querySelector('.event-card-cta-label').textContent = ctaLabel(event.target.open, Number(event.target.dataset.fights) || 0);
    }
    container.addEventListener('click', click);
    container.addEventListener('error', imageError, true);
    container.addEventListener('toggle', toggleCard, true);
    render();
    if (opts.autoStart) {
      if (local) refresh(false);
      timer = setInterval(() => refresh(false), 30000);
    }
    return { update, refresh, destroy() { disposed = true; clearInterval(timer); container.removeEventListener('click', click); container.removeEventListener('error', imageError, true); container.removeEventListener('toggle', toggleCard, true); } };
  }

  return { mount, currentCards, marketView };
})();
