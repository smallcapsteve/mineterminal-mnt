/* TYPEAHEAD_V1 (2026-09-14)
   Type-ahead dropdown for the nav search box on MiningNewsTerminal and
   SEDITracker. Ported from MineTerminalPro's MTP_SEARCH_V1 so all three sites
   behave the same way when you start typing a ticker or a company name.

   One file serves both sites: /opt/sedi/app/portal/static is a symlink to
   /opt/mnt/app/portal/static.

   It attaches to any <form data-typeahead> and asks that form's
   data-suggest endpoint (default /api/search) for
       { "results": [ { kind, label, sub, url }, ... ] }
   which is the same payload MTP's /api/search already returns.

   Two deliberate differences from MTP:

   1. Nothing is highlighted until the reader arrows into the list. MTP's box
      has no destination other than a suggestion, so it can highlight the first
      row and let Enter follow it. These two boxes ALSO run the site's own text
      search — news on MNT, insider names on SediTracker — so a bare Enter must
      keep submitting the form exactly as it did before this file existed.
      Arrow down first and Enter follows the highlighted row.

   2. Picking a row is a plain navigation, not history.pushState. MTP is a
      single-page app; these are server-rendered pages.

   Degrades to exactly the old behaviour if the endpoint is missing, slow or
   broken: the form is untouched and still submits.
*/
(function () {
  'use strict';
  if (window.__taSearchV1) return;
  window.__taSearchV1 = true;

  var MIN_CHARS = 1;
  var DEBOUNCE_MS = 180;
  var LIMIT = 14;

  /* kind -> [section heading, icon]. Order here is the order on screen; a kind
     the server sends that is not listed falls into "Other" rather than being
     dropped, so adding a kind server-side needs no change here. */
  var SECTIONS = [
    ['company',  'Companies',  '◆'],
    ['insider',  'Insiders',   '●'],
    ['property', 'Properties', '⛰'],
    ['news',     'News',       '■'],
    ['page',     'Pages',      '➤']
  ];

  var panelSeq = 0;

  function esc(s) {
    s = (s == null) ? '' : String(s);
    return s.replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function setup(form) {
    if (form.__taWired) return;
    var input = form.querySelector('input[type="search"], input[name="q"]');
    if (!input) return;
    form.__taWired = true;

    var endpoint = form.getAttribute('data-suggest') || '/api/search';
    var panel = document.createElement('div');
    panel.className = 'ta-results';
    panel.id = 'ta-results-' + (++panelSeq);
    panel.setAttribute('role', 'listbox');
    form.appendChild(panel);

    /* The browser's own autofill list would sit on top of ours. */
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', panel.id);

    var items = [];        // flat list, index-aligned with the rendered rows
    var active = -1;       // -1 = nothing picked; a bare Enter submits the form
    var timer = null;
    var lastQ = null;
    var reqSeq = 0;        // guards against a slow reply overwriting a fast one

    function close() {
      panel.classList.remove('open');
      panel.innerHTML = '';
      items = [];
      active = -1;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
    }

    function markActive() {
      var rows = panel.querySelectorAll('.ta-item');
      for (var i = 0; i < rows.length; i++) {
        var on = (i === active);
        rows[i].classList.toggle('active', on);
        rows[i].setAttribute('aria-selected', on ? 'true' : 'false');
      }
      if (active >= 0 && rows[active]) {
        rows[active].scrollIntoView({ block: 'nearest' });
        input.setAttribute('aria-activedescendant', rows[active].id);
      } else {
        input.removeAttribute('aria-activedescendant');
      }
    }

    function move(delta) {
      if (!items.length) return;
      if (active < 0) active = (delta > 0) ? 0 : items.length - 1;
      else active = Math.max(0, Math.min(items.length - 1, active + delta));
      markActive();
    }

    function go(i) {
      var pick = items[i];
      if (!pick || !pick.url) return;
      close();
      window.location.href = pick.url;
    }

    function render(list) {
      items = [];
      active = -1;
      if (!list.length) {
        panel.innerHTML = '<div class="ta-empty">No matches</div>';
        panel.classList.add('open');
        input.setAttribute('aria-expanded', 'true');
        return;
      }

      var buckets = {}, order = [];
      list.forEach(function (it) {
        var k = it && it.kind ? String(it.kind) : 'page';
        if (!buckets[k]) { buckets[k] = []; order.push(k); }
        buckets[k].push(it);
      });

      var known = SECTIONS.map(function (s) { return s[0]; });
      var sections = SECTIONS.filter(function (s) { return buckets[s[0]]; });
      order.forEach(function (k) {
        if (known.indexOf(k) === -1) sections.push([k, 'Other', '➤']);
      });

      var html = '';
      var idx = 0;
      sections.forEach(function (s) {
        var rows = buckets[s[0]] || [];
        if (!rows.length) return;
        html += '<div class="ta-group">' + esc(s[1]) + '</div>';
        rows.forEach(function (it) {
          items.push(it);
          var chip = (s[0] === 'company' && it.sub)
            ? '<span class="tk">' + esc(it.sub) + '</span>' : '';
          var sub = (it.sub && s[0] !== 'company')
            ? '<div class="sub">' + esc(it.sub) + '</div>' : '';
          html += '<div class="ta-item" role="option" aria-selected="false"' +
                  ' id="' + panel.id + '-o' + idx + '" data-idx="' + idx + '">' +
                    '<span class="ico" aria-hidden="true">' + s[2] + '</span>' +
                    '<div class="body">' +
                      '<div class="label">' + esc(it.label) + '</div>' + sub +
                    '</div>' + chip +
                  '</div>';
          idx++;
        });
      });

      panel.innerHTML = html;
      panel.classList.add('open');
      input.setAttribute('aria-expanded', 'true');
    }

    function query(q) {
      if (q === lastQ && panel.classList.contains('open')) return;
      lastQ = q;
      var mine = ++reqSeq;
      fetch(endpoint + '?q=' + encodeURIComponent(q) + '&limit=' + LIMIT,
            { credentials: 'omit' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          if (mine !== reqSeq) return;                 // a later keystroke won
          if (!j || !Array.isArray(j.results)) return; // leave the box alone
          render(j.results);
        })
        .catch(function () { /* offline or 500: the form still submits */ });
    }

    input.addEventListener('input', function () {
      var q = input.value.trim();
      if (timer) clearTimeout(timer);
      if (q.length < MIN_CHARS) { lastQ = null; close(); return; }
      timer = setTimeout(function () { query(q); }, DEBOUNCE_MS);
    });

    input.addEventListener('focus', function () {
      var q = input.value.trim();
      if (q.length >= MIN_CHARS && !panel.classList.contains('open')) {
        lastQ = null;
        query(q);
      }
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { close(); return; }
      if (e.key === 'ArrowDown') { e.preventDefault(); move(1); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); return; }
      if (e.key === 'Enter') {
        /* Only hijack Enter when the reader has actually picked a row.
           Otherwise this is the plain text search it has always been. */
        if (active >= 0) { e.preventDefault(); go(active); }
        return;
      }
    });

    panel.addEventListener('mousemove', function (e) {
      var row = e.target.closest ? e.target.closest('.ta-item') : null;
      if (!row) return;
      var i = parseInt(row.getAttribute('data-idx'), 10);
      if (isNaN(i) || i === active) return;
      active = i;
      markActive();
    });

    /* mousedown, not click: the input's blur would otherwise be able to close
       the panel out from under the pointer on some browsers. */
    panel.addEventListener('mousedown', function (e) {
      var row = e.target.closest ? e.target.closest('.ta-item') : null;
      if (!row) return;
      e.preventDefault();
      go(parseInt(row.getAttribute('data-idx'), 10));
    });

    document.addEventListener('click', function (e) {
      if (!form.contains(e.target)) close();
    });

    /* Submitting the form should not leave a dropdown hanging over the next
       page during the load. */
    form.addEventListener('submit', function () { close(); });
  }

  function init() {
    var forms = document.querySelectorAll('form[data-typeahead]');
    for (var i = 0; i < forms.length; i++) setup(forms[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
