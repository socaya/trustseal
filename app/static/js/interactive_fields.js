/* =====================================================================
 * TrustSeal Modern Interactive Placeholder Fields Engine
 * - Converts raw {{document_ref}} tokens into sleek, human-readable,
 *   highlighted interactive field areas (.ts-field-chip)
 * - Auto-fills from known contract/document metadata (Document Ref,
 *   Organization Name, Counterparty, Effective Date, Deal Value, etc.)
 * - Click any field chip to edit inline & sync all occurrences across the doc
 * - @media print: filled fields render as crisp plain text; unfilled fields
 *   render as clean official handwritten fill-in lines (__________________)
 * ===================================================================== */
(function (global) {
  'use strict';

  var STYLE_ID = 'ts-interactive-fields-css';
  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent =
      '.ts-field-chip{display:inline-flex;align-items:center;gap:4px;padding:1px 7px;margin:0 1px;border-radius:4px;font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;font-size:0.92em;font-weight:600;line-height:1.35;cursor:pointer;vertical-align:baseline;transition:all .14s ease;}' +
      '.ts-field-chip.is-empty{background:#fff7ed;color:#b45309;border:1px dashed #f59e0b;box-shadow:inset 0 -1px 0 rgba(245,158,11,.25);}' +
      '.ts-field-chip.is-empty:hover{background:#ffedd5;border-color:#d97706;}' +
      '.ts-field-chip.is-filled{background:#eef4ff;color:#0f3b82;border:1px solid #bfdbfe;}' +
      '.ts-field-chip.is-filled:hover{background:#dbeafe;border-color:#1a73e8;}' +
      '.ts-field-pop{position:fixed;z-index:9700;width:290px;max-width:92vw;background:#ffffff;border:1px solid #cbd5e1;border-radius:9px;box-shadow:0 14px 36px rgba(15,23,42,.18);padding:12px 14px;font-family:Inter,-apple-system,sans-serif;}' +
      '.ts-field-pop[hidden]{display:none;}' +
      '.ts-field-pop__head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;}' +
      '.ts-field-pop__lbl{font-size:11.5px;font-weight:700;color:#0f172a;text-transform:uppercase;letter-spacing:0.04em;}' +
      '.ts-field-pop__key{font-size:10px;color:#64748b;font-family:monospace;}' +
      '.ts-field-pop__in{width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:6px;padding:7px 9px;font-size:13px;color:#0f172a;outline:none;margin-bottom:10px;}' +
      '.ts-field-pop__in:focus{border-color:#002769;box-shadow:0 0 0 2px rgba(0,39,105,.1);}' +
      '.ts-field-pop__foot{display:flex;align-items:center;justify-content:space-between;gap:6px;}' +
      '.ts-field-pop__btn{border:1px solid #cbd5e1;background:#fff;color:#334155;padding:5px 10px;border-radius:5px;font-size:11.5px;font-weight:600;cursor:pointer;}' +
      '.ts-field-pop__btn--pri{background:#002769;border-color:#002769;color:#fff;}' +
      '.ts-field-pop__btn--pri:hover{background:#001d52;}' +
      '@media print{' +
        '.ts-field-pop{display:none !important;}' +
        '.ts-field-chip.is-filled{background:transparent !important;border:0 !important;padding:0 !important;color:inherit !important;font-family:inherit !important;font-size:inherit !important;font-weight:inherit !important;box-shadow:none !important;}' +
        '.ts-field-chip.is-empty{background:transparent !important;border:0 !important;border-bottom:1pt solid #1d3648 !important;border-radius:0 !important;min-width:110pt;color:transparent !important;box-shadow:none !important;}' +
      '}';
    document.head.appendChild(s);
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function normKey(k) {
    return String(k || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  }

  function humanizeKey(key) {
    var ACRONYMS = { id: 1, ref: 1, vat: 1, tin: 1, pin: 1, sla: 1, nda: 1, msa: 1, kpi: 1, okr: 1, hr: 1, it: 1, po: 1, url: 1 };
    return String(key || '').split(/[_\-\s.]+/).filter(Boolean).map(function (p) {
      return ACRONYMS[p.toLowerCase()] ? p.toUpperCase() : (p.charAt(0).toUpperCase() + p.slice(1));
    }).join(' ') || 'Field';
  }

  var _popEl = null;
  var _activeHost = null;
  var _activeKey = '';
  var _activeOnChange = null;

  function ensurePopover() {
    if (_popEl) return _popEl;
    _popEl = document.createElement('div');
    _popEl.className = 'ts-field-pop';
    _popEl.hidden = true;
    _popEl.innerHTML =
      '<div class="ts-field-pop__head">' +
        '<div><div class="ts-field-pop__lbl" data-fp-lbl>Field</div><div class="ts-field-pop__key" data-fp-key></div></div>' +
        '<button type="button" data-fp-close style="border:0;background:transparent;color:#64748b;cursor:pointer;font-size:14px;">✕</button>' +
      '</div>' +
      '<input type="text" class="ts-field-pop__in" data-fp-in placeholder="Enter value…">' +
      '<div class="ts-field-pop__foot">' +
        '<button type="button" class="ts-field-pop__btn" data-fp-clear title="Leave blank (prints as handwritten line)">Leave Blank</button>' +
        '<button type="button" class="ts-field-pop__btn ts-field-pop__btn--pri" data-fp-apply>Apply to All</button>' +
      '</div>';
    document.body.appendChild(_popEl);

    var inp = _popEl.querySelector('[data-fp-in]');
    function commit(val) {
      if (_activeHost && _activeKey) {
        setFieldValue(_activeHost, _activeKey, val);
        if (typeof _activeOnChange === 'function') _activeOnChange(_activeKey, val);
      }
      _popEl.hidden = true;
    }
    _popEl.querySelector('[data-fp-close]').addEventListener('click', function () { _popEl.hidden = true; });
    _popEl.querySelector('[data-fp-apply]').addEventListener('click', function () { commit(inp.value.trim()); });
    _popEl.querySelector('[data-fp-clear]').addEventListener('click', function () { commit(''); });
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); commit(inp.value.trim()); }
      else if (e.key === 'Escape') { _popEl.hidden = true; }
    });
    document.addEventListener('mousedown', function (e) {
      if (_popEl.hidden) return;
      if (_popEl.contains(e.target) || (e.target.closest && e.target.closest('.ts-field-chip'))) return;
      _popEl.hidden = true;
    });
    return _popEl;
  }

  function setFieldValue(rootEl, key, val) {
    if (!rootEl) return 0;
    var nk = normKey(key);
    var label = humanizeKey(key);
    var v = String(val || '').trim();
    var count = 0;
    rootEl.querySelectorAll('.ts-field-chip[data-field-key]').forEach(function (chip) {
      if (normKey(chip.getAttribute('data-field-key')) !== nk) return;
      if (v) {
        chip.textContent = v;
        chip.classList.remove('is-empty');
        chip.classList.add('is-filled');
        chip.title = label + ': ' + v + ' (click to edit)';
      } else {
        chip.textContent = label;
        chip.classList.remove('is-filled');
        chip.classList.add('is-empty');
        chip.title = 'Click to fill ' + label + ' (prints as blank line if left empty)';
      }
      count++;
    });
    return count;
  }

  /**
   * Upgrade all raw {{key}} text occurrences inside rootEl into interactive chips,
   * and auto-fill any chips whose key exists in `context`.
   */
  function hydrate(rootEl, context, opts) {
    injectStyles();
    if (!rootEl) return { upgraded: 0, filled: 0 };
    opts = opts || {};

    var normCtx = {};
    Object.keys(context || {}).forEach(function (k) {
      var v = context[k];
      if (v !== null && v !== undefined && String(v).trim() !== '') {
        normCtx[normKey(k)] = String(v).trim();
      }
    });

    // 1. Replace raw {{key}} tokens in text nodes (without touching scripts/styles/SVGs)
    var upgraded = 0;
    var walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT, null);
    var textNodes = [];
    var n;
    while ((n = walker.nextNode())) {
      if (!n.nodeValue || n.nodeValue.indexOf('{{') === -1) continue;
      var p = n.parentNode;
      if (!p || p.closest && (p.closest('svg, script, style, .tsd-floating-mark, .ts-field-chip'))) continue;
      textNodes.push(n);
    }
    textNodes.forEach(function (tn) {
      var parts = tn.nodeValue.split(/(\{\{\s*[a-zA-Z0-9_.-]+\s*\}\})/g);
      if (parts.length <= 1) return;
      var frag = document.createDocumentFragment();
      parts.forEach(function (part) {
        var m = part.match(/^\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}$/);
        if (!m) {
          if (part) frag.appendChild(document.createTextNode(part));
          return;
        }
        var rawKey = m[1];
        var label = humanizeKey(rawKey);
        var val = normCtx[normKey(rawKey)] || '';
        var span = document.createElement('span');
        span.className = 'ts-field-chip ' + (val ? 'is-filled' : 'is-empty');
        span.setAttribute('data-field-key', rawKey);
        span.setAttribute('data-field-label', label);
        span.setAttribute('contenteditable', 'false');
        span.textContent = val || label;
        span.title = val
          ? (label + ': ' + val + ' (click to edit)')
          : ('Click to fill ' + label + ' (prints as blank line if left empty)');
        frag.appendChild(span);
        upgraded++;
      });
      if (tn.parentNode) tn.parentNode.replaceChild(frag, tn);
    });

    // 2. Auto-fill any existing empty chips that now have values in `context`
    var filled = 0;
    rootEl.querySelectorAll('.ts-field-chip[data-field-key]').forEach(function (chip) {
      var rawKey = chip.getAttribute('data-field-key') || '';
      var label = chip.getAttribute('data-field-label') || humanizeKey(rawKey);
      var val = normCtx[normKey(rawKey)] || '';
      var curTxt = (chip.textContent || '').trim();
      var looksEmpty = chip.classList.contains('is-empty') || !curTxt || curTxt.toLowerCase() === label.toLowerCase();
      if (val && (looksEmpty || opts.forceSync)) {
        chip.textContent = val;
        chip.classList.remove('is-empty');
        chip.classList.add('is-filled');
        chip.title = label + ': ' + val + ' (click to edit)';
        filled++;
      }
    });

    // 3. Attach click handler once per rootEl
    if (!rootEl._tsFieldsWired) {
      rootEl._tsFieldsWired = true;
      rootEl.addEventListener('click', function (e) {
        var chip = e.target.closest && e.target.closest('.ts-field-chip[data-field-key]');
        if (!chip || !rootEl.contains(chip)) return;
        e.preventDefault();
        e.stopPropagation();
        var pop = ensurePopover();
        var rawKey = chip.getAttribute('data-field-key') || '';
        var label = chip.getAttribute('data-field-label') || humanizeKey(rawKey);
        _activeHost = rootEl;
        _activeKey = rawKey;
        _activeOnChange = rootEl._tsFieldsOnChange || null;
        pop.querySelector('[data-fp-lbl]').textContent = label;
        pop.querySelector('[data-fp-key]').textContent = 'Field · ' + rawKey;
        var inp = pop.querySelector('[data-fp-in]');
        inp.value = chip.classList.contains('is-filled') ? (chip.textContent || '').trim() : '';
        inp.placeholder = 'Enter ' + label + '…';
        pop.hidden = false;
        var r = chip.getBoundingClientRect();
        var left = Math.max(10, Math.min(window.innerWidth - 304, r.left));
        var top = r.bottom + 8;
        if (top + 140 > window.innerHeight) top = Math.max(10, r.top - 144);
        pop.style.left = left + 'px';
        pop.style.top = top + 'px';
        inp.focus();
        inp.select();
      });
    }
    if (opts.onChange) rootEl._tsFieldsOnChange = opts.onChange;

    return { upgraded: upgraded, filled: filled };
  }

  global.TSInteractiveFields = {
    hydrate: hydrate,
    setFieldValue: setFieldValue,
    humanizeKey: humanizeKey,
  };
})(window);
