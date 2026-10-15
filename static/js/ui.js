/* Civic Sync - shared UI behaviour. Pure progressive enhancement: pages work without it. */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- toasts ---------- */
  function toast(message, type = 'info', ms = 4500) {
    let box = $('#ui-toasts');
    if (!box) { box = document.createElement('div'); box.id = 'ui-toasts'; document.body.appendChild(box); }
    const icon = { success: 'fa-circle-check', error: 'fa-circle-exclamation', info: 'fa-circle-info' }[type] || 'fa-circle-info';
    const t = document.createElement('div');
    t.className = 'ui-toast ' + type;
    t.style.setProperty('--t', ms + 'ms');
    t.setAttribute('role', 'status');
    const i = document.createElement('i'); i.className = 'fa-solid ' + icon;
    const s = document.createElement('span'); s.textContent = message;   // textContent: never HTML
    t.append(i, s);
    box.appendChild(t);
    const close = () => { t.classList.add('out'); setTimeout(() => t.remove(), 350); };
    t.addEventListener('click', close);
    setTimeout(close, ms);
  }
  window.CivicUI = { toast };

  // ?success= / ?error= from redirects (login/register show their own alerts)
  if (!document.body.hasAttribute('data-no-toast')) {
    const q = new URLSearchParams(location.search);
    const ok = q.get('success'), bad = q.get('error');
    if (ok || bad) {
      toast(ok || bad, ok ? 'success' : 'error');
      q.delete('success'); q.delete('error');
      history.replaceState(null, '', location.pathname + (q.toString() ? '?' + q : '') + location.hash);
    }
  }

  /* ---------- scroll progress ---------- */
  const bar = document.createElement('div'); bar.id = 'ui-progress'; document.body.appendChild(bar);
  const onScroll = () => {
    const h = document.documentElement;
    const max = h.scrollHeight - h.clientHeight;
    bar.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + '%';
  };
  addEventListener('scroll', onScroll, { passive: true }); onScroll();

  /* ---------- staggered reveal ---------- */
  const revealSel = '.stat-card,.kpi-card,.action-card,.complaint-card,.feature,.card,.role-card,.map-section,.chart-card,tbody tr,.step-node';
  if (!reduce && 'IntersectionObserver' in window) {
    const seen = new Map();
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        const el = e.target; io.unobserve(el);
        const n = seen.get(el.parentElement) || 0; seen.set(el.parentElement, n + 1);
        const delay = Math.min(n, 8) * 70;
        el.style.transitionDelay = delay + 'ms';
        requestAnimationFrame(() => el.classList.add('ui-in'));
        // drop helper classes afterwards so hover effects respond instantly
        setTimeout(() => { el.classList.remove('ui-reveal', 'ui-in'); el.style.transitionDelay = ''; }, 900 + delay);
      });
    }, { threshold: 0.08 });
    $$(revealSel).forEach((el) => { el.classList.add('ui-reveal'); io.observe(el); });
  }

  /* ---------- animated counters ---------- */
  $$('.stat-number,.kpi-number').forEach((el) => {
    const raw = el.textContent.trim();
    const m = raw.match(/^([^\d-]*)(-?\d+(?:\.\d+)?)(.*)$/);
    if (!m || reduce) return;
    const [, pre, num, post] = m, end = parseFloat(num), dec = (num.split('.')[1] || '').length;
    const t0 = performance.now(), dur = 1100;
    el.textContent = pre + (0).toFixed(dec) + post;
    (function tick(now) {
      const p = Math.min(1, (now - t0) / dur), eased = 1 - Math.pow(1 - p, 3);
      el.textContent = pre + (end * eased).toFixed(dec) + post;
      if (p < 1) requestAnimationFrame(tick); else el.textContent = raw;
    })(t0);
  });

  /* ---------- button ripple + loading state ---------- */
  const btnSel = 'button[type=submit],.submit-btn,.btn-update-status,.btn-action,.track-btn,.gps-btn';
  document.addEventListener('pointerdown', (e) => {
    const b = e.target.closest(btnSel); if (!b || b.disabled) return;
    const r = b.getBoundingClientRect(), d = Math.max(r.width, r.height) / 2;
    const s = document.createElement('span'); s.className = 'ui-ripple';
    s.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
    b.appendChild(s); setTimeout(() => s.remove(), 700);
  });
  $$('form[method="POST" i]').forEach((f) => f.addEventListener('submit', (e) => {
    if (e.defaultPrevented) return;                       // page's own validation said no
    const b = $('button[type=submit],input[type=submit]', f); if (!b || b.classList.contains('ui-loading')) return;
    b.classList.add('ui-loading');
    setTimeout(() => { b.disabled = true; }, 0);          // stop double submits
    setTimeout(() => { b.disabled = false; b.classList.remove('ui-loading'); }, 15000);
  }));

  /* ---------- hero panel: cursor spotlight + rotating highlight (login/register) ---------- */
  const hero = $('.left-section') || ($('.hero-message') && $('.hero-message').parentElement);
  if (hero && !reduce) {
    if (getComputedStyle(hero).position === 'static') hero.style.position = 'relative';
    const spot = document.createElement('div'); spot.className = 'ui-spot'; hero.appendChild(spot);
    hero.addEventListener('pointermove', (e) => {
      const r = hero.getBoundingClientRect();
      spot.style.setProperty('--mx', e.clientX - r.left + 'px'); spot.style.setProperty('--my', e.clientY - r.top + 'px');
    });
  }
  const words = $$('.navigation span');
  if (words.length && !reduce) {
    let i = 0; (function cycle() {
      words.forEach((w, k) => w.classList.toggle('ui-hl', k === i)); i = (i + 1) % words.length; setTimeout(cycle, 1800);
    })();
  }

  /* ---------- password strength + match (register) ---------- */
  const pw = $('#password'), pw2 = $('#confirm_password');
  if (pw && pw2) {
    const meter = document.createElement('div'); meter.className = 'ui-strength'; meter.dataset.s = '0';
    meter.innerHTML = '<div class="bars"><i></i><i></i><i></i><i></i></div><span>Use 8+ characters with letters, numbers and symbols</span>';
    const anchor = pw.closest('.input-group') || pw; anchor.insertAdjacentElement('afterend', meter);
    const label = ['Too short', 'Weak', 'Fair', 'Good', 'Strong'];
    const score = (v) => {
      if (!v) return 0;
      if (v.length < 8) return 1;
      return Math.min(4, 1 + (/[a-z]/.test(v) && /[A-Z]/.test(v)) + /\d/.test(v) + /[^A-Za-z0-9]/.test(v));
    };
    const update = () => {
      const s = score(pw.value); meter.dataset.s = s;
      if (pw.value) meter.lastChild.textContent = 'Password strength: ' + label[s];
      pw2.classList.toggle('ui-match-ok', !!pw2.value && pw.value === pw2.value);
      pw2.classList.toggle('ui-match-bad', !!pw2.value && pw.value !== pw2.value);
    };
    pw.addEventListener('input', update); pw2.addEventListener('input', update);
  }

  /* ---------- live date/time chip in dashboard top bars ---------- */
  const right = $('.topbar-right');
  if (right) {
    const chip = document.createElement('div'); chip.className = 'ui-clock';
    chip.innerHTML = '<i class="fa-regular fa-clock"></i><span></span>';
    right.insertBefore(chip, right.firstChild);
    const span = chip.lastChild, fmt = { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' };
    (function tick() { span.textContent = new Date().toLocaleString([], fmt); setTimeout(tick, 15000); })();
  }
})();
