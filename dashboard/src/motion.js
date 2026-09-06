/* Motion: the few primitives every section shares.
   Numbers count up, sections reveal on scroll, fills animate once.
   Everything checks prefers-reduced-motion and degrades to a plain set. */
window.MM = window.MM || {};

MM.motion = (function () {
  const media = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  const reduced = () => Boolean(media && media.matches);

  const easeOutExpo = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
  const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

  /* Tween a number into an element's text. Returns a cancel function. */
  function countUp(el, to, options) {
    const opts = Object.assign({ from: 0, duration: 900, delay: 0, format: (v) => String(Math.round(v)), ease: easeOutExpo }, options || {});
    if (!el) return () => {};
    if (reduced() || !Number.isFinite(to)) {
      el.textContent = opts.format(Number.isFinite(to) ? to : 0);
      return () => {};
    }
    let raf = 0;
    let start = 0;
    const from = Number.isFinite(opts.from) ? opts.from : 0;
    const step = (now) => {
      if (!start) start = now;
      const t = Math.min(1, (now - start) / opts.duration);
      el.textContent = opts.format(from + (to - from) * opts.ease(t));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    const timer = setTimeout(() => { raf = requestAnimationFrame(step); }, opts.delay);
    return () => { clearTimeout(timer); cancelAnimationFrame(raf); };
  }

  /* Reveal-on-scroll. Elements with [data-reveal] get .is-in when they enter
     the viewport; siblings inside a [data-reveal-group] stagger by index. */
  let observer = null;
  function reveal(root) {
    const scope = root || document;
    const nodes = Array.from(scope.querySelectorAll("[data-reveal]:not(.is-in)"));
    if (!nodes.length) return;
    scope.querySelectorAll("[data-reveal-group]").forEach((group) => {
      Array.from(group.querySelectorAll("[data-reveal]")).forEach((n, i) => n.style.setProperty("--i", String(Math.min(i, 24))));
    });
    if (reduced() || !("IntersectionObserver" in window)) {
      nodes.forEach((n) => n.classList.add("is-in"));
      return;
    }
    if (!observer) {
      observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            observer.unobserve(entry.target);
          }
        });
      }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    }
    nodes.forEach((n) => observer.observe(n));
  }

  /* Two frames later: lets the browser paint an initial state first, so a
     transition from it actually runs. */
  function afterPaint(fn) {
    requestAnimationFrame(() => requestAnimationFrame(fn));
  }

  /* Flash a value change: adds .is-up or .is-down for a beat. */
  function pulse(el, direction) {
    if (!el || reduced()) return;
    el.classList.remove("is-up", "is-down");
    void el.offsetWidth;
    el.classList.add(direction > 0 ? "is-up" : "is-down");
  }

  return { reduced, easeOutExpo, easeOutCubic, countUp, reveal, afterPaint, pulse };
})();
