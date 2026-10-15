/* Civic Sync - shared responsive behaviour (progressive enhancement). */
(function () {
  'use strict';
  var mq = window.matchMedia('(max-width: 850px)');

  /* ---- off-canvas sidebar for pages that don't already wire one up ---- */
  var sidebar = document.querySelector('.sidebar');
  if (sidebar && !document.getElementById('menuToggle')) {
    var topbar = document.querySelector('.topbar');
    var btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'rs-menu-btn';
    btn.setAttribute('aria-label', 'Open navigation');
    btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>';
    var overlay = document.createElement('div'); overlay.className = 'rs-overlay';
    document.body.appendChild(overlay);
    if (topbar) topbar.insertBefore(btn, topbar.firstChild);
    else document.body.appendChild(btn);

    var setOpen = function (open) {
      sidebar.classList.toggle('open', open);
      overlay.classList.toggle('show', open);
      document.body.classList.toggle('rs-lock', open && mq.matches);
      btn.setAttribute('aria-expanded', String(open));
      btn.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    };
    btn.addEventListener('click', function () { setOpen(!sidebar.classList.contains('open')); });
    overlay.addEventListener('click', function () { setOpen(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });
    sidebar.addEventListener('click', function (e) { if (e.target.closest('a')) setOpen(false); });
    (mq.addEventListener ? mq.addEventListener.bind(mq, 'change') : mq.addListener.bind(mq))(function () { setOpen(false); });
  }

  /* ---- label table cells so the phone card layout can show column names ---- */
  function labelTable(table) {
    var heads = Array.prototype.map.call(table.querySelectorAll('thead th'), function (th) { return th.textContent.trim(); });
    if (!heads.length) return;
    Array.prototype.forEach.call(table.querySelectorAll('tbody tr'), function (tr) {
      Array.prototype.forEach.call(tr.children, function (td, i) {
        if (td.tagName === 'TD' && !td.hasAttribute('colspan') && heads[i] && td.getAttribute('data-label') !== heads[i]) td.setAttribute('data-label', heads[i]);
      });
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll('.table-responsive table'), function (table) {
    labelTable(table);
    var body = table.tBodies[0];
    if (body && 'MutationObserver' in window) new MutationObserver(function () { labelTable(table); }).observe(body, { childList: true });
  });
})();
