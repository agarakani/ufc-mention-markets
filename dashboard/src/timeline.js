/* The scrub strip: the recorded week for one night, frame by frame.
   Drag or arrow through it and the board re-prices underneath. */
window.MM = window.MM || {};

MM.timeline = (function () {
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);

  function activity(night) {
    const n = night.frames;
    const out = new Array(n).fill(0);
    for (let i = 1; i < n; i++) {
      let sum = 0, count = 0;
      night.markets.forEach((m) => {
        const a = m.ask[i], b = m.ask[i - 1];
        if (isNum(a) && isNum(b)) { sum += Math.abs(a - b); count++; }
      });
      out[i] = count ? sum / count : 0;
    }
    const max = Math.max(1e-9, ...out);
    // square root so a single settlement spike does not flatten the rest of the week
    return out.map((v) => Math.sqrt(v / max));
  }

  function mount(container, night, options) {
    const opts = Object.assign({ frame: night.frames - 1, onFrame: () => {} }, options || {});
    const n = night.frames;
    let frame = Math.max(0, Math.min(n - 1, opts.frame));
    const act = activity(night);
    const fightDay = night.date;

    container.innerHTML = "";
    const root = document.createElement("div");
    root.className = "scrub";
    root.innerHTML = `
      <div class="scrub-ends">
        <span class="scrub-end">${MM.fmt.stamp(night.stamps[0], { time: false })}</span>
        <span class="scrub-hint">Drag through the week. The board re-prices under you.</span>
        <span class="scrub-end">${MM.fmt.stamp(night.stamps[n - 1], { time: false })}</span>
      </div>
      <div class="scrub-track" role="slider" tabindex="0" aria-label="Time through the recorded week" aria-valuemin="0" aria-valuemax="${n - 1}" aria-valuenow="${frame}">
        <div class="scrub-night"></div>
        <div class="scrub-bars"></div>
        <div class="scrub-progress"></div>
        <div class="scrub-handle"><span class="scrub-label"></span></div>
      </div>`;
    container.appendChild(root);

    const track = root.querySelector(".scrub-track");
    const barsEl = root.querySelector(".scrub-bars");
    const nightEl = root.querySelector(".scrub-night");
    const progress = root.querySelector(".scrub-progress");
    const handle = root.querySelector(".scrub-handle");
    const label = root.querySelector(".scrub-label");

    act.forEach((v, i) => {
      const b = document.createElement("i");
      b.style.setProperty("--h", (0.12 + 0.88 * v).toFixed(3));
      b.style.setProperty("--i", String(i));
      barsEl.appendChild(b);
    });

    // The band keys each stamp by the same local calendar day the label
    // shows, so the broadcast and settlement frames sit inside it.
    const pad2 = (v) => String(v).padStart(2, "0");
    const localDay = (s) => {
      const d = new Date(s);
      return Number.isNaN(d.getTime()) ? "" : d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
    };
    const first = night.stamps.findIndex((s) => localDay(s) === fightDay);
    let last = -1;
    night.stamps.forEach((s, i) => { if (localDay(s) === fightDay) last = i; });
    if (first >= 0 && last >= first) {
      // A one-frame night (recording stopped on fight day) still gets a
      // visible band, kept inside the track.
      const start = last === first && first > 0 ? first - 1 : first;
      nightEl.style.left = ((start / (n - 1)) * 100).toFixed(2) + "%";
      nightEl.style.width = (Math.max(1, last - start) / (n - 1) * 100).toFixed(2) + "%";
      nightEl.title = "Fight night";
    } else {
      nightEl.hidden = true;
    }

    function paint() {
      const pct = (frame / (n - 1)) * 100;
      progress.style.width = pct.toFixed(3) + "%";
      handle.style.left = pct.toFixed(3) + "%";
      label.textContent = MM.fmt.stamp(night.stamps[frame]);
      handle.classList.toggle("is-left", pct < 12);
      handle.classList.toggle("is-right", pct > 88);
      track.setAttribute("aria-valuenow", String(frame));
      track.setAttribute("aria-valuetext", label.textContent);
    }

    let raf = 0;
    function setFrame(next, silent) {
      const clamped = Math.max(0, Math.min(n - 1, Math.round(next)));
      if (clamped === frame) return;
      frame = clamped;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => { paint(); if (!silent) opts.onFrame(frame); });
    }

    function frameFromX(clientX) {
      const rect = track.getBoundingClientRect();
      const t = (clientX - rect.left) / Math.max(1, rect.width);
      return Math.max(0, Math.min(1, t)) * (n - 1);
    }

    let dragging = false;
    const onDown = (ev) => {
      dragging = true;
      track.setPointerCapture(ev.pointerId);
      root.classList.add("is-dragging");
      setFrame(frameFromX(ev.clientX));
      track.focus({ preventScroll: true });
    };
    const onMove = (ev) => { if (dragging) setFrame(frameFromX(ev.clientX)); };
    const onUp = (ev) => {
      dragging = false;
      root.classList.remove("is-dragging");
      try { track.releasePointerCapture(ev.pointerId); } catch (e) { /* already released */ }
    };
    const onKey = (ev) => {
      const big = Math.max(1, Math.round(n / 12));
      if (ev.key === "ArrowLeft") { ev.preventDefault(); setFrame(frame - (ev.shiftKey ? big : 1)); }
      else if (ev.key === "ArrowRight") { ev.preventDefault(); setFrame(frame + (ev.shiftKey ? big : 1)); }
      else if (ev.key === "Home") { ev.preventDefault(); setFrame(0); }
      else if (ev.key === "End") { ev.preventDefault(); setFrame(n - 1); }
    };
    track.addEventListener("pointerdown", onDown);
    track.addEventListener("pointermove", onMove);
    track.addEventListener("pointerup", onUp);
    track.addEventListener("pointercancel", onUp);
    track.addEventListener("keydown", onKey);

    paint();
    return {
      setFrame: (i) => setFrame(i, true),
      frame: () => frame,
      destroy() {
        cancelAnimationFrame(raf);
        track.removeEventListener("pointerdown", onDown);
        track.removeEventListener("pointermove", onMove);
        track.removeEventListener("pointerup", onUp);
        track.removeEventListener("pointercancel", onUp);
        track.removeEventListener("keydown", onKey);
        container.innerHTML = "";
      },
    };
  }

  return { mount, activity };
})();
