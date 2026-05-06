/* Agentic Reach — Components JS
 * Exposes window.AR with: initModal(idOrEl), initBookingModal(opts), buildKnowledgeGraph(svgEl, opts).
 */
(function () {
  const AR = {};

  /* ── Modal ─────────────────────────────────────────────────────────── */
  AR.initModal = function (modalEl, { onSubmit } = {}) {
    if (typeof modalEl === 'string') modalEl = document.getElementById(modalEl);
    if (!modalEl) return null;
    let lastFocus = null;

    function open(e) {
      if (e && e.preventDefault) e.preventDefault();
      lastFocus = document.activeElement;
      modalEl.hidden = false;
      requestAnimationFrame(() => modalEl.classList.add('open'));
      document.body.classList.add('ar-modal-open');
      const first = modalEl.querySelector('input, textarea, select, button');
      if (first) setTimeout(() => first.focus(), 200);
    }
    function close() {
      modalEl.classList.remove('open');
      document.body.classList.remove('ar-modal-open');
      setTimeout(() => { modalEl.hidden = true; }, 220);
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    document.querySelectorAll(`[data-open-modal="${modalEl.id}"]`).forEach((el) => {
      el.addEventListener('click', open);
    });
    modalEl.querySelectorAll('[data-close-modal]').forEach((el) => {
      el.addEventListener('click', close);
    });
    modalEl.addEventListener('click', (e) => { if (e.target === modalEl) close(); });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !modalEl.hidden) close();
    });

    const form = modalEl.querySelector('form');
    if (form && onSubmit) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        const data = Object.fromEntries(fd.entries());
        onSubmit(data, { close, form });
      });
    }
    return { open, close };
  };

  /* ── Knowledge graph (animated background visual) ──────────────────── */
  AR.buildKnowledgeGraph = function (svg, { nodes = 24, seed = 7 } = {}) {
    if (!svg) return;
    const W = 560, H = 560, ns = 'http://www.w3.org/2000/svg';
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');

    const rng = ((s) => () => (s = (s * 9301 + 49297) % 233280) / 233280)(seed);
    const pts = [];
    for (let i = 0; i < nodes; i++) {
      const ang = (i / nodes) * Math.PI * 2 + rng() * 0.4;
      const ring = i % 4;
      const r = 70 + ring * 70 + rng() * 30;
      pts.push({ x: W/2 + Math.cos(ang) * r, y: H/2 + Math.sin(ang) * r, ring });
    }
    pts[0] = { x: W/2, y: H/2, ring: -1, anchor: true };

    const edges = [];
    for (let i = 1; i < nodes; i++) {
      const a = pts[i];
      const cs = pts.map((b, j) => ({ j, d: (a.x - b.x) ** 2 + (a.y - b.y) ** 2 }))
                   .filter(c => c.j !== i)
                   .sort((x, y) => x.d - y.d).slice(0, 3);
      edges.push({ a: i, b: cs[0].j });
      if (rng() > 0.55) edges.push({ a: i, b: cs[1].j });
    }

    edges.forEach((e) => {
      const a = pts[e.a], b = pts[e.b];
      const ln = document.createElementNS(ns, 'line');
      ln.setAttribute('x1', a.x); ln.setAttribute('y1', a.y);
      ln.setAttribute('x2', b.x); ln.setAttribute('y2', b.y);
      ln.setAttribute('stroke', 'rgba(61,43,92,0.30)');
      ln.setAttribute('stroke-width', '1');
      svg.appendChild(ln);
    });
    pts.forEach((p, i) => {
      const c = document.createElementNS(ns, 'circle');
      c.setAttribute('cx', p.x); c.setAttribute('cy', p.y);
      const isAccent = i === 0;
      const isCoral = i % 7 === 3;
      const isYellow = i % 11 === 5;
      c.setAttribute('r', isAccent ? 6 : 3.4);
      c.setAttribute('fill',
        isAccent ? '#FF7A6B' : isCoral ? '#FF7A6B' : isYellow ? '#F4C84A' : '#3D2B5C');
      svg.appendChild(c);
    });
  };

  window.AR = AR;
})();
