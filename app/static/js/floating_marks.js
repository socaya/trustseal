/* =====================================================================
 * TrustSeal Floating Marks Engine (Stamps, Signatures & Handwritten Initials)
 * - Free-floating over document content (position: absolute, mix-blend-mode for stamps)
 * - Smooth pointer drag anywhere on the document (zoom-aware)
 * - Smooth 360-degree rotation via interactive knob handle + live angle badge
 * - Corner resize handle + floating quick-action bar (tilt, repeat on all pages, delete)
 * - Multi-page placement (current page or all pages) & 4 Handwritten Initials styles
 * ===================================================================== */
(function (global) {
  'use strict';

  var STYLE_ID = 'ts-floating-marks-css';
  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent =
      '.ts-marks-overlay{position:absolute;inset:0;pointer-events:none;z-index:25;overflow:visible;}' +
      '.tsd-floating-mark{position:absolute;pointer-events:auto;cursor:grab;user-select:none;-webkit-user-select:none;transform-origin:center center;padding:4px;border-radius:4px;box-sizing:border-box;transition:box-shadow .12s ease;}' +
      '.tsd-floating-mark[data-mark-kind="stamp"]{mix-blend-mode:multiply;}' +
      '.tsd-floating-mark:hover{outline:1.5px dashed rgba(26,115,232,0.55);outline-offset:2px;}' +
      '.tsd-floating-mark.is-fm-selected{outline:1.5px solid #1a73e8;outline-offset:3px;z-index:45 !important;}' +
      '.tsd-floating-mark.is-fm-dragging{cursor:grabbing;opacity:0.92;}' +
      '.tsd-floating-mark svg{display:block;pointer-events:none;}' +
      '.tsd-floating-mark img{pointer-events:none;}' +
      '.ts-fm-chrome{position:absolute;inset:-4px;pointer-events:none;z-index:50;}' +
      '.ts-fm-rot-stem{position:absolute;left:50%;top:-26px;width:1.5px;height:22px;background:#1a73e8;transform:translateX(-50%);pointer-events:none;}' +
      '.ts-fm-rot-knob{position:absolute;left:50%;top:-36px;width:20px;height:20px;margin-left:-10px;border-radius:50%;background:#1a73e8;color:#fff;border:2px solid #fff;box-shadow:0 2px 6px rgba(15,23,42,.28);cursor:grab;pointer-events:auto;display:flex;align-items:center;justify-content:center;font-size:11px;line-height:1;font-weight:700;}' +
      '.ts-fm-rot-knob:active{cursor:grabbing;background:#002769;}' +
      '.ts-fm-resize-knob{position:absolute;right:-6px;bottom:-6px;width:12px;height:12px;border-radius:2px;background:#fff;border:2px solid #1a73e8;box-shadow:0 1px 4px rgba(15,23,42,.22);cursor:nwse-resize;pointer-events:auto;}' +
      '.ts-fm-angle-pill{position:fixed;z-index:9900;background:#0f172a;color:#fff;font-family:Inter,system-ui,sans-serif;font-size:11px;font-weight:700;padding:3px 8px;border-radius:99px;pointer-events:none;box-shadow:0 4px 12px rgba(15,23,42,.25);}' +
      '.ts-fm-bar{position:fixed;z-index:9400;display:flex;align-items:center;gap:4px;background:#0f172a;color:#fff;padding:4px 6px;border-radius:7px;box-shadow:0 8px 22px rgba(15,23,42,.28);font-family:Inter,system-ui,sans-serif;font-size:11px;}' +
      '.ts-fm-bar[hidden]{display:none;}' +
      '.ts-fm-bar button{border:0;background:rgba(255,255,255,.1);color:#fff;padding:4px 7px;border-radius:4px;font-size:11px;font-weight:600;cursor:pointer;white-space:nowrap;}' +
      '.ts-fm-bar button:hover{background:rgba(255,255,255,.22);}' +
      '.ts-fm-bar .ts-fm-bar__deg{padding:0 5px;color:#93c5fd;font-weight:700;min-width:34px;text-align:center;font-variant-numeric:tabular-nums;}' +
      '.ts-fm-bar .ts-fm-bar__del{background:rgba(220,38,38,.28);color:#fecaca;}' +
      '.ts-fm-bar .ts-fm-bar__del:hover{background:#dc2626;color:#fff;}' +
      '.ts-fm-initials-wrap{display:inline-flex;flex-direction:column;align-items:center;padding:4px 8px;}' +
      '@media print{.ts-fm-chrome,.ts-fm-bar,.ts-fm-angle-pill{display:none !important;}.tsd-floating-mark{outline:none !important;}}';
    document.head.appendChild(s);
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  var PX_PER_MM = 96 / 25.4; // 3.7795275591 px/mm (matches A4 210mm = 794px)

  /**
   * Compute exact physical pixel dimensions (at 96 DPI) for a TrustSeal stamp
   * from its layout metadata (width_mm / height_mm / size_value) or SVG width/height.
   */
  function computePhysicalStampPx(stampObj, svgHtml) {
    var lay = (stampObj && stampObj.layout && typeof stampObj.layout === 'object') ? stampObj.layout : {};
    var kind = String((stampObj && stampObj.kind) || '').toLowerCase();
    function num(v, fb) {
      var n = parseFloat(v);
      return (!isNaN(n) && n >= 8 && n <= 200) ? n : fb;
    }

    var wMm = null, hMm = null;
    if (lay.width_mm != null && lay.height_mm != null) {
      wMm = num(lay.width_mm, null);
      hMm = num(lay.height_mm, null);
    }
    if (wMm === null && lay.size_value) {
      var sv = String(lay.size_value).toLowerCase().replace(/×/g, 'x').trim();
      if (sv === 'custom') {
        wMm = num(lay.custom_w, 42);
        hMm = num(lay.custom_h, wMm);
      } else if (sv.indexOf('x') !== -1) {
        var pts = sv.split('x');
        wMm = num(pts[0], null);
        hMm = num(pts[1], null);
      } else {
        var diam = num(sv, null);
        if (diam !== null) { wMm = diam; hMm = diam; }
      }
    }

    // Fallback to SVG's authored 96-DPI physical width/height attributes
    if ((wMm === null || hMm === null) && svgHtml) {
      var mW = String(svgHtml).match(/<svg\b[^>]*\bwidth=["']([0-9.]+)(px|mm)?["']/i);
      var mH = String(svgHtml).match(/<svg\b[^>]*\bheight=["']([0-9.]+)(px|mm)?["']/i);
      if (mW && mH) {
        var rawW = parseFloat(mW[1]), rawH = parseFloat(mH[1]);
        var uW = (mW[2] || 'px').toLowerCase(), uH = (mH[2] || 'px').toLowerCase();
        var pxW = uW === 'mm' ? (rawW * PX_PER_MM) : rawW;
        var pxH = uH === 'mm' ? (rawH * PX_PER_MM) : rawH;
        if (pxW >= 32 && pxW <= 680 && pxH >= 24 && pxH <= 680) {
          return {
            wPx: Math.round(pxW),
            hPx: Math.round(pxH),
            wMm: Math.round((pxW / PX_PER_MM) * 10) / 10,
            hMm: Math.round((pxH / PX_PER_MM) * 10) / 10,
          };
        }
      }
    }

    // Kind-based physical defaults matching Stamp Studio
    if (wMm === null || hMm === null) {
      if (kind === 'company_rect' || kind === 'signature') { wMm = 80; hMm = 40; }
      else if (kind === 'rubber' || kind === 'date') { wMm = 59; hMm = 23; }
      else { wMm = 42; hMm = 42; }
    }
    return {
      wPx: Math.round(wMm * PX_PER_MM),
      hPx: Math.round(hMm * PX_PER_MM),
      wMm: Math.round(wMm * 10) / 10,
      hMm: Math.round(hMm * 10) / 10,
    };
  }

  function deriveInitials(name) {
    var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'A.S.';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase() + '.';
    return parts.slice(0, 3).map(function (p) { return p.charAt(0).toUpperCase(); }).join('.') + '.';
  }

  /**
   * Build authentic handwritten initials HTML (4 calligraphic styles)
   */
  var SIGNATURE_FONTS = [
    { id: 'mrs-saint-delafield', name: 'Mrs Saint Delafield', tag: 'Raw Ink Autograph', stack: "'Mrs Saint Delafield','Snell Roundhand',cursive", baseSize: 38, italic: false },
    { id: 'herr-von-muellerhoff', name: 'Herr Von Muellerhoff', tag: 'Executive Pen Autograph', stack: "'Herr Von Muellerhoff','Snell Roundhand',cursive", baseSize: 40, italic: false },
    { id: 'mr-de-haviland', name: 'Mr De Haviland', tag: 'Classic Fountain Autograph', stack: "'Mr De Haviland','Snell Roundhand',cursive", baseSize: 38, italic: false },
    { id: 'mr-dafoe', name: 'Mr Dafoe', tag: 'Fast Ballpoint Signature', stack: "'Mr Dafoe','Brush Script MT',cursive", baseSize: 34, italic: false },
    { id: 'allison', name: 'Allison', tag: 'Modern Fine-Pen Signature', stack: "'Allison','Segoe Script',cursive", baseSize: 40, italic: false },
    { id: 'kristi', name: 'Kristi', tag: 'Rapid Executive Scribble', stack: "'Kristi','Segoe Script',cursive", baseSize: 38, italic: false },
    { id: 'la-belle-aurore', name: 'La Belle Aurore', tag: 'Fine Nib Personal Hand', stack: "'La Belle Aurore','Segoe Script',cursive", baseSize: 30, italic: false },
    { id: 'zeyada', name: 'Zeyada', tag: 'Natural Everyday Pen', stack: "'Zeyada','Bradley Hand',cursive", baseSize: 34, italic: false },
    { id: 'reenie-beanie', name: 'Reenie Beanie', tag: 'Pure Ballpoint Hand', stack: "'Reenie Beanie','Bradley Hand',cursive", baseSize: 36, italic: false },
    { id: 'homemade-apple', name: 'Homemade Apple', tag: 'Genuine Cursive Hand', stack: "'Homemade Apple','Bradley Hand',cursive", baseSize: 23, italic: false },
    { id: 'cedarville-cursive', name: 'Cedarville Cursive', tag: 'True Penmanship Cursive', stack: "'Cedarville Cursive','Segoe Script',cursive", baseSize: 28, italic: false },
    { id: 'meddon', name: 'Meddon', tag: 'Archival Dip-Pen Hand', stack: "'Meddon','Snell Roundhand',cursive", baseSize: 24, italic: false },
    { id: 'qwigley', name: 'Qwigley', tag: 'Fluid Fountain Signature', stack: "'Qwigley','Snell Roundhand',cursive", baseSize: 42, italic: false },
    { id: 'arizonia', name: 'Arizonia', tag: 'Swift Brush-Pen Autograph', stack: "'Arizonia','Brush Script MT',cursive", baseSize: 34, italic: false },
    { id: 'birthstone', name: 'Birthstone', tag: 'Graceful Real Cursive', stack: "'Birthstone','Snell Roundhand',cursive", baseSize: 38, italic: false },
    { id: 'windsong', name: 'WindSong', tag: 'Expressive Ink Flourish', stack: "'WindSong','Snell Roundhand',cursive", baseSize: 30, italic: false },
    { id: 'cherish', name: 'Cherish', tag: 'Slender Rollerball Hand', stack: "'Cherish','Segoe Script',cursive", baseSize: 38, italic: false },
    { id: 'meow-script', name: 'Meow Script', tag: 'Relaxed Personal Cursive', stack: "'Meow Script','Segoe Script',cursive", baseSize: 34, italic: false },
    { id: 'monsieur-la-doulaise', name: 'Monsieur La Doulaise', tag: 'Heritage Formal Autograph', stack: "'Monsieur La Doulaise','Snell Roundhand',cursive", baseSize: 36, italic: false },
    { id: 'ruthie', name: 'Ruthie', tag: 'Classic Fine-Ink Cursive', stack: "'Ruthie','Snell Roundhand',cursive", baseSize: 38, italic: false },
  ];

  function ensureSignatureFontsLoaded() {
    if (document.getElementById('ts-sig-fonts-link')) return;
    var link = document.createElement('link');
    link.id = 'ts-sig-fonts-link';
    link.rel = 'stylesheet';
    link.href = 'https://fonts.googleapis.com/css2?family=Allison&family=Arizonia&family=Birthstone&family=Cedarville+Cursive&family=Cherish&family=Herr+Von+Muellerhoff&family=Homemade+Apple&family=Kristi&family=La+Belle+Aurore&family=Meddon&family=Meow+Script&family=Monsieur+La+Doulaise&family=Mr+Dafoe&family=Mr+De+Haviland&family=Mrs+Saint+Delafield&family=Qwigley&family=Reenie+Beanie&family=Ruthie&family=WindSong:wght@400;500&family=Zeyada&display=swap';
    document.head.appendChild(link);
  }
  ensureSignatureFontsLoaded();

  function getSignatureFont(fontId) {
    for (var i = 0; i < SIGNATURE_FONTS.length; i++) {
      if (SIGNATURE_FONTS[i].id === fontId || SIGNATURE_FONTS[i].name === fontId) return SIGNATURE_FONTS[i];
    }
    return SIGNATURE_FONTS[0];
  }

  function buildHandwrittenSignatureHtml(opts) {
    ensureSignatureFontsLoaded();
    var text = String((opts && opts.name) || 'Authorized Signatory').trim() || 'Authorized Signatory';
    var f = getSignatureFont(opts && opts.font);
    var ink = (opts && opts.ink) || '#002769';
    var slant = (opts && opts.slant != null) ? Number(opts.slant) : -4;
    var scale = (opts && opts.size != null) ? Number(opts.size) : 1;
    var fontSize = Math.max(16, Math.min(54, Math.round(f.baseSize * scale)));
    var flourish = (opts && opts.flourish !== false);
    var fontStyle = f.italic ? 'italic' : 'normal';
    var flourishSvg = flourish
      ? '<svg width="190" height="12" viewBox="0 0 190 12" style="display:block;margin:-4px auto 0;overflow:visible;"><path d="M 8 9 C 56 2, 128 11, 182 3" fill="none" stroke="' + esc(ink) + '" stroke-width="1.5" stroke-linecap="round" opacity="0.78"/></svg>'
      : '';
    return '<div class="ts-fm-sig-wrap" data-sig-font="' + esc(f.id) + '" style="display:inline-flex;flex-direction:column;align-items:center;padding:4px 10px;user-select:none;">' +
      '<div style="font-family:' + f.stack + ';font-size:' + fontSize + 'px;font-style:' + fontStyle + ';color:' + esc(ink) + ';line-height:1.15;white-space:nowrap;transform:rotate(' + slant + 'deg);">' + esc(text) + '</div>' +
      flourishSvg +
    '</div>';
  }

  function buildHandwrittenInitialsHtml(opts) {
    ensureSignatureFontsLoaded();
    var text = String((opts && opts.initials) || deriveInitials(opts && opts.name) || 'A.S.').trim().slice(0, 10);
    var style = (opts && opts.style) || 'cursive';
    var ink = (opts && opts.ink) || '#002769';
    var showDate = !!(opts && opts.showDate);
    var dateStr = (opts && opts.dateStr) || new Date().toISOString().slice(0, 10);
    var slant = (opts && opts.slant != null) ? Number(opts.slant) : -5;
    var scale = (opts && opts.size != null) ? Number(opts.size) : 1;
    var customFont = (opts && opts.font) ? getSignatureFont(opts.font) : null;

    var fontStack = customFont ? customFont.stack : "'Great Vibes','Snell Roundhand','Brush Script MT',cursive";
    var fontSize = Math.round((customFont ? customFont.baseSize : 30) * scale);
    var fontStyle = (customFont && customFont.italic) ? 'italic' : 'normal';
    var letterSpacing = '0.02em';
    var extraDecor = '';

    if (style === 'fountain') {
      if (!customFont) { fontStack = "'Dancing Script','Apple Chancery','Segoe Script',cursive"; fontSize = Math.round(26 * scale); }
      letterSpacing = '0.04em';
      extraDecor = '<svg width="86" height="10" viewBox="0 0 86 10" style="margin-top:-4px;overflow:visible;"><path d="M 4 7 Q 38 1 82 5" fill="none" stroke="' + esc(ink) + '" stroke-width="1.6" stroke-linecap="round" opacity="0.82"/></svg>';
    } else if (style === 'editorial') {
      if (!customFont) { fontStack = "'Playfair Display',Georgia,'Palatino Linotype',serif"; fontSize = Math.round(22 * scale); fontStyle = 'italic'; }
      letterSpacing = '0.08em';
      extraDecor = '<svg width="76" height="8" viewBox="0 0 76 8" style="margin-top:-2px;"><path d="M 6 5 L 70 4" fill="none" stroke="' + esc(ink) + '" stroke-width="1.2" stroke-linecap="round" opacity="0.65"/></svg>';
    } else if (style === 'monogram') {
      var monoSize = Math.max(16, Math.min(34, Math.round(fontSize * 0.78)));
      return '<div class="ts-fm-initials-wrap" data-initials-style="monogram" data-sig-font="' + esc(customFont ? customFont.id : 'great-vibes') + '" style="padding:2px;">' +
        '<div style="width:64px;height:64px;border-radius:50%;border:1.8px solid ' + esc(ink) + ';display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,0.65);">' +
          '<span style="font-family:' + fontStack + ';font-size:' + monoSize + 'px;font-style:' + fontStyle + ';color:' + esc(ink) + ';line-height:1;transform:rotate(' + slant + 'deg);display:inline-block;">' + esc(text) + '</span>' +
        '</div>' +
        (showDate ? '<div style="font-family:Inter,Arial,sans-serif;font-size:8px;color:' + esc(ink) + ';opacity:0.75;margin-top:2px;letter-spacing:0.04em;">' + esc(dateStr) + '</div>' : '') +
      '</div>';
    } else {
      extraDecor = '<svg width="92" height="12" viewBox="0 0 92 12" style="margin-top:-5px;overflow:visible;"><path d="M 4 9 C 28 2, 62 11, 88 3" fill="none" stroke="' + esc(ink) + '" stroke-width="1.7" stroke-linecap="round" opacity="0.85"/></svg>';
    }

    return '<div class="ts-fm-initials-wrap" data-initials-style="' + esc(style) + '" data-sig-font="' + esc(customFont ? customFont.id : 'great-vibes') + '">' +
      '<div style="font-family:' + fontStack + ';font-size:' + fontSize + 'px;font-style:' + fontStyle + ';color:' + esc(ink) + ';line-height:1.05;letter-spacing:' + letterSpacing + ';white-space:nowrap;transform:rotate(' + slant + 'deg);">' + esc(text) + '</div>' +
      extraDecor +
      (showDate ? '<div style="font-family:Inter,Arial,sans-serif;font-size:8px;color:' + esc(ink) + ';opacity:0.75;margin-top:1px;letter-spacing:0.04em;">' + esc(dateStr) + '</div>' : '') +
    '</div>';
  }

  function renderFontGallery(containerEl, opts) {
    if (!containerEl) return;
    ensureSignatureFontsLoaded();
    var sample = String((opts && opts.sampleText) || 'S.O.').trim() || 'S.O.';
    var activeId = (opts && opts.activeFontId) || 'mrs-saint-delafield';
    var ink = (opts && opts.ink) || '#002769';
    var cols = (opts && opts.cols) || 3;
    containerEl.style.display = 'grid';
    containerEl.style.gridTemplateColumns = 'repeat(' + cols + ', minmax(0, 1fr))';
    containerEl.style.gap = '6px';
    containerEl.innerHTML = SIGNATURE_FONTS.map(function (f) {
      var on = (f.id === activeId);
      var fSize = Math.max(15, Math.min(26, Math.round(f.baseSize * (sample.length > 10 ? 0.62 : 0.78))));
      return '<button type="button" data-ts-font-id="' + esc(f.id) + '" title="' + esc(f.name + ' — ' + f.tag) + '" style="border:1.5px solid ' + (on ? '#002769' : '#d5dce6') + ';background:' + (on ? '#edf2fa' : '#ffffff') + ';padding:6px 5px;cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;min-height:54px;overflow:hidden;">' +
        '<span style="font-family:' + f.stack + ';font-size:' + fSize + 'px;font-style:' + (f.italic ? 'italic' : 'normal') + ';color:' + esc(ink) + ';line-height:1.1;white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis;">' + esc(sample) + '</span>' +
        '<span style="font-size:9px;font-weight:700;color:' + (on ? '#002769' : '#64748b') + ';white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis;">' + esc(f.name) + '</span>' +
      '</button>';
    }).join('');
  }

  /**
   * Attach interactive drag, 360° rotate, resize, and "Repeat on All Pages"
   * to a transparent overlay container sitting over a page / multi-page surface.
   */
  function attach(overlayEl, opts) {
    injectStyles();
    if (!overlayEl) return null;
    if (overlayEl._tsFmController) return overlayEl._tsFmController;

    opts = opts || {};
    var getHostRect = opts.getHostRect || function () { return overlayEl.getBoundingClientRect(); };
    var getHostUnzoomed = opts.getHostUnzoomed || function () {
      return { w: overlayEl.offsetWidth || 794, h: overlayEl.offsetHeight || 1123 };
    };
    var getPageMetrics = opts.getPageMetrics || function () {
      var u = getHostUnzoomed();
      return { pageW: u.w, pageH: 1123, gap: 22, pageCount: Math.max(1, Math.round(u.h / 1123)), scrollTop: 0 };
    };
    var onChange = opts.onChange || function () {};
    var onToast = opts.onToast || function () {};
    var onSignStamp = typeof opts.onSignStamp === 'function' ? opts.onSignStamp : null;

    var selectedEl = null;

    // Shared floating toolbar & live angle badge
    var bar = document.createElement('div');
    bar.className = 'ts-fm-bar';
    bar.hidden = true;
    bar.innerHTML =
      '<button type="button" data-fm-act="sign-stamp" style="background:#02982E;" title="Load an authorized signature into this stamp\'s signature area" hidden>✎ Sign Stamp</button>' +
      '<button type="button" data-fm-act="rot-ccw" title="Rotate -15°">⟲ -15°</button>' +
      '<span class="ts-fm-bar__deg" data-fm-deg>0°</span>' +
      '<button type="button" data-fm-act="rot-cw" title="Rotate +15°">⟳ +15°</button>' +
      '<button type="button" data-fm-act="rot-0" title="Reset angle">0°</button>' +
      '<button type="button" data-fm-act="all-pages" title="Apply this mark at the same position & angle on every page">📄 All Pages</button>' +
      '<button type="button" class="ts-fm-bar__del" data-fm-act="delete" title="Remove mark">✕</button>';
    document.body.appendChild(bar);

    var anglePill = document.createElement('div');
    anglePill.className = 'ts-fm-angle-pill';
    anglePill.hidden = true;
    document.body.appendChild(anglePill);

    function getAngle(el) {
      var a = parseFloat(el.getAttribute('data-angle') || '0');
      return isNaN(a) ? 0 : Math.round(a);
    }
    function setAngle(el, deg) {
      var norm = Math.round(deg);
      while (norm > 180) norm -= 360;
      while (norm < -180) norm += 360;
      el.setAttribute('data-angle', String(norm));
      el.style.transform = 'rotate(' + norm + 'deg)';
      var degEl = bar.querySelector('[data-fm-deg]');
      if (degEl && el === selectedEl) degEl.textContent = norm + '°';
    }

    function positionBar() {
      if (!selectedEl || !document.body.contains(selectedEl)) {
        bar.hidden = true;
        return;
      }
      var r = selectedEl.getBoundingClientRect();
      bar.hidden = false;
      var bw = bar.offsetWidth || 280;
      var left = Math.max(8, Math.min(window.innerWidth - bw - 8, r.left + (r.width - bw) / 2));
      var top = r.bottom + 10;
      if (top + 36 > window.innerHeight - 10) top = Math.max(8, r.top - 42);
      bar.style.left = left + 'px';
      bar.style.top = top + 'px';
      var degEl = bar.querySelector('[data-fm-deg]');
      if (degEl) degEl.textContent = getAngle(selectedEl) + '°';
      var signBtn = bar.querySelector('[data-fm-act="sign-stamp"]');
      if (signBtn) {
        signBtn.hidden = !(onSignStamp && selectedEl.getAttribute('data-mark-kind') === 'stamp');
      }
    }

    function stripChrome(el) {
      if (!el) return;
      el.classList.remove('is-fm-selected', 'is-fm-dragging');
      el.querySelectorAll('.ts-fm-chrome').forEach(function (c) { c.remove(); });
    }

    function attachChrome(el) {
      stripChrome(el);
      el.classList.add('is-fm-selected');
      var chrome = document.createElement('div');
      chrome.className = 'ts-fm-chrome';
      chrome.setAttribute('data-fm-chrome', '1');
      var isStamp = el.getAttribute('data-mark-kind') === 'stamp';
      chrome.innerHTML =
        '<div class="ts-fm-rot-stem"></div>' +
        '<div class="ts-fm-rot-knob" data-fm-handle="rotate" title="Drag to rotate at any angle (hold Shift to snap 15°)">↻</div>' +
        (isStamp ? '' : '<div class="ts-fm-resize-knob" data-fm-handle="resize" title="Drag to resize"></div>');
      el.appendChild(chrome);
    }

    function select(el) {
      if (selectedEl && selectedEl !== el) stripChrome(selectedEl);
      selectedEl = el || null;
      if (selectedEl) {
        attachChrome(selectedEl);
        positionBar();
      } else {
        bar.hidden = true;
      }
    }

    function cleanForPersist() {
      // Returns cloned HTML of all floating marks without editor selection chrome
      var tmp = document.createElement('div');
      overlayEl.querySelectorAll('.tsd-floating-mark').forEach(function (m) {
        var cl = m.cloneNode(true);
        cl.classList.remove('is-fm-selected', 'is-fm-dragging', 'tsd-verify-flash');
        cl.querySelectorAll('.ts-fm-chrome').forEach(function (c) { c.remove(); });
        tmp.appendChild(cl);
      });
      return tmp.innerHTML;
    }

    function duplicateToAllPages(sourceEl) {
      if (!sourceEl) return;
      var pm = getPageMetrics();
      var pageCount = Math.max(1, pm.pageCount || 1);
      if (pageCount <= 1) {
        onToast('Document currently has 1 page — mark is placed on Page 1.');
        return;
      }
      var cycle = (pm.pageH || 1123) + (pm.gap || 22);
      var srcLeft = parseFloat(sourceEl.style.left) || 40;
      var srcTop = parseFloat(sourceEl.style.top) || 40;
      var srcPageIdx = Math.max(0, Math.min(pageCount - 1, Math.floor(srcTop / cycle)));
      var localY = srcTop - (srcPageIdx * cycle);
      var angle = getAngle(sourceEl);

      var added = 0;
      for (var p = 0; p < pageCount; p++) {
        if (p === srcPageIdx) continue;
        var cl = sourceEl.cloneNode(true);
        cl.classList.remove('is-fm-selected', 'is-fm-dragging', 'tsd-verify-flash');
        cl.querySelectorAll('.ts-fm-chrome').forEach(function (c) { c.remove(); });
        cl.style.left = Math.round(srcLeft) + 'px';
        cl.style.top = Math.round(p * cycle + localY) + 'px';
        cl.setAttribute('data-page-idx', String(p));
        setAngle(cl, angle);
        overlayEl.appendChild(cl);
        added++;
      }
      onChange();
      onToast('Applied to all ' + pageCount + ' pages (' + added + ' added)');
    }

    // Floating bar actions
    bar.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-fm-act]');
      if (!btn || !selectedEl) return;
      e.stopPropagation();
      var act = btn.getAttribute('data-fm-act');
      if (act === 'sign-stamp' && onSignStamp) { onSignStamp(selectedEl); return; }
      if (act === 'rot-ccw') { setAngle(selectedEl, getAngle(selectedEl) - 15); positionBar(); onChange(); }
      else if (act === 'rot-cw') { setAngle(selectedEl, getAngle(selectedEl) + 15); positionBar(); onChange(); }
      else if (act === 'rot-0') { setAngle(selectedEl, 0); positionBar(); onChange(); }
      else if (act === 'all-pages') { duplicateToAllPages(selectedEl); }
      else if (act === 'delete') {
        var victim = selectedEl;
        select(null);
        victim.remove();
        onChange();
        onToast('Mark removed');
      }
    });

    // Pointer interaction: drag, 360° rotate, or corner resize
    overlayEl.addEventListener('pointerdown', function (e) {
      var mark = e.target.closest('.tsd-floating-mark');
      if (!mark || !overlayEl.contains(mark)) return;
      e.preventDefault();
      e.stopPropagation();
      select(mark);

      var handleEl = e.target.closest('[data-fm-handle]');
      var mode = handleEl ? handleEl.getAttribute('data-fm-handle') : 'drag';

      var hostRect = getHostRect();
      var hostU = getHostUnzoomed();
      var scaleX = (hostU.w > 0 && hostRect.width > 0) ? (hostRect.width / hostU.w) : 1;
      var scaleY = (hostU.h > 0 && hostRect.height > 0) ? (hostRect.height / hostU.h) : 1;

      var startX = e.clientX;
      var startY = e.clientY;
      var origLeft = parseFloat(mark.style.left) || 0;
      var origTop = parseFloat(mark.style.top) || 0;
      var origW = mark.offsetWidth || 168;

      var markRect = mark.getBoundingClientRect();
      var cx = markRect.left + markRect.width / 2;
      var cy = markRect.top + markRect.height / 2;
      var startAngle = getAngle(mark);
      var startPointerRad = Math.atan2(e.clientY - cy, e.clientX - cx);

      if (mode === 'drag') mark.classList.add('is-fm-dragging');

      function onMove(ev) {
        if (mode === 'drag') {
          var dx = (ev.clientX - startX) / scaleX;
          var dy = (ev.clientY - startY) / scaleY;
          var maxW = Math.max(hostU.w, 600);
          var maxH = Math.max(hostU.h, 800);
          var nx = Math.max(-20, Math.min(maxW - 30, origLeft + dx));
          var ny = Math.max(0, Math.min(maxH - 30, origTop + dy));
          mark.style.left = Math.round(nx) + 'px';
          mark.style.top = Math.round(ny) + 'px';
          positionBar();
        } else if (mode === 'rotate') {
          var curRad = Math.atan2(ev.clientY - cy, ev.clientX - cx);
          var deltaDeg = (curRad - startPointerRad) * (180 / Math.PI);
          var nextDeg = startAngle + deltaDeg;
          if (ev.shiftKey) nextDeg = Math.round(nextDeg / 15) * 15;
          setAngle(mark, nextDeg);
          anglePill.textContent = getAngle(mark) + '°';
          anglePill.style.left = (ev.clientX + 14) + 'px';
          anglePill.style.top = (ev.clientY - 26) + 'px';
          anglePill.hidden = false;
          positionBar();
        } else if (mode === 'resize') {
          var dSize = ((ev.clientX - startX) / scaleX);
          var nextW = Math.max(58, Math.min(380, Math.round(origW + dSize)));
          mark.style.width = nextW + 'px';
          mark.setAttribute('data-mark-width', String(nextW));
          var innerSvg = mark.querySelector('svg');
          if (innerSvg && mark.getAttribute('data-mark-kind') === 'stamp') {
            innerSvg.style.width = Math.max(48, nextW - 8) + 'px';
          }
          positionBar();
        }
      }

      function onUp() {
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onUp);
        document.removeEventListener('pointercancel', onUp);
        mark.classList.remove('is-fm-dragging');
        anglePill.hidden = true;
        positionBar();
        onChange();
      }

      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
      document.addEventListener('pointercancel', onUp);
    });

    // Deselect when clicking outside marks & bar
    document.addEventListener('pointerdown', function (e) {
      if (!selectedEl) return;
      if (overlayEl.contains(e.target) && e.target.closest('.tsd-floating-mark')) return;
      if (bar.contains(e.target)) return;
      select(null);
    });

    // Delete key removes selected mark
    document.addEventListener('keydown', function (e) {
      if (!selectedEl) return;
      if (e.key === 'Escape') { select(null); return; }
      if ((e.key === 'Delete' || e.key === 'Backspace') && document.activeElement &&
          !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) &&
          !document.activeElement.isContentEditable) {
        var v = selectedEl;
        select(null);
        v.remove();
        onChange();
      }
    });

    // Keep bar aligned on scroll/resize
    window.addEventListener('scroll', function () { if (selectedEl) positionBar(); }, true);
    window.addEventListener('resize', function () { if (selectedEl) positionBar(); });

    /**
     * Place a new floating mark (on current visible page OR across ALL pages)
     */
    function placeMark(innerHtml, placeOpts) {
      placeOpts = placeOpts || {};
      var kind = placeOpts.kind || 'stamp';
      var placement = placeOpts.placement || 'current';
      var angle = Number(placeOpts.angle || 0) || 0;
      var phys = (kind === 'stamp') ? computePhysicalStampPx(placeOpts.stampObj || null, innerHtml) : null;
      var widthPx = Number(placeOpts.width || (phys ? (phys.wPx + 8) : (kind === 'initials' ? 110 : 220)));
      var heightPx = Number(placeOpts.height || (phys ? phys.hPx : 0)) || 0;

      var pm = getPageMetrics();
      var pageW = pm.pageW || 794;
      var pageH = pm.pageH || 1123;
      var gap = pm.gap || 22;
      var cycle = pageH + gap;
      var pageCount = Math.max(1, pm.pageCount || 1);

      var targetPages = [];
      if (placement === 'current') {
        var visPage = Math.max(0, Math.min(pageCount - 1, Math.floor(((pm.scrollTop || 0) + 180) / cycle)));
        targetPages = [visPage];
      } else {
        for (var p = 0; p < pageCount; p++) targetPages.push(p);
      }

      var estH = kind === 'initials' ? 76 : (kind === 'signature' ? 92 : (heightPx || 159));
      var created = [];

      targetPages.forEach(function (pIdx, idx) {
        var wrap = document.createElement('div');
        wrap.className = 'tsd-floating-mark' + (kind === 'stamp' ? ' tsd-stamp-mark' : ' tsd-sig-block');
        wrap.setAttribute('data-floating-mark', '1');
        wrap.setAttribute('data-mark-kind', kind);
        wrap.setAttribute('data-page-idx', String(pIdx));
        wrap.setAttribute('contenteditable', 'false');

        // Compute clean default coordinates on the target page
        var leftPx, localY;
        var isSigOrInit = (kind === 'signature' || kind === 'initials');
        var footerBottomPad = isSigOrInit ? 40 : 68;
        if (placement === 'all_bl') {
          leftPx = 64;
          localY = Math.max(60, pageH - estH - footerBottomPad);
        } else if (placement === 'all_tr') {
          leftPx = Math.max(40, pageW - widthPx - 64);
          localY = 64;
        } else if (placement === 'all_br') {
          leftPx = Math.max(40, pageW - widthPx - 64);
          localY = Math.max(60, pageH - estH - footerBottomPad);
        } else if (isSigOrInit) {
          // Default for standalone Signatures & Initials: place cleanly in the footer area
          // of the current page (overlay allowed, never blocking document body contents).
          var samePageSigs = overlayEl.querySelectorAll(
            '.tsd-floating-mark[data-page-idx="' + pIdx + '"][data-mark-kind="signature"],' +
            '.tsd-floating-mark[data-page-idx="' + pIdx + '"][data-mark-kind="initials"]'
          ).length;
          var horizStep = kind === 'initials' ? 120 : 210;
          leftPx = Math.max(56, pageW - widthPx - 58 - ((samePageSigs % 3) * horizStep));
          localY = Math.max(60, pageH - estH - footerBottomPad);
        } else {
          // 'current' for Stamps — drop visibly near center-right of the active viewport page
          var existingCnt = overlayEl.querySelectorAll('.tsd-floating-mark[data-mark-kind="stamp"]').length;
          leftPx = Math.max(60, Math.min(pageW - widthPx - 54, pageW - widthPx - 88 - ((existingCnt % 3) * 24)));
          var visOffsetInPage = Math.max(110, Math.min(pageH - estH - 90, ((pm.scrollTop || 0) - pIdx * cycle) + 210));
          localY = visOffsetInPage + ((existingCnt % 3) * 18);
        }

        wrap.style.left = Math.round(leftPx) + 'px';
        wrap.style.top = Math.round(pIdx * cycle + localY) + 'px';
        wrap.style.width = widthPx + 'px';
        wrap.innerHTML = innerHtml;
        setAngle(wrap, angle);

        // Apply exact physical 96-DPI dimensions for stamps (never squished or oversized)
        if (kind === 'stamp') {
          var svgEl = wrap.querySelector('svg');
          if (svgEl) {
            if (!svgEl.getAttribute('viewBox')) {
              var wa = parseFloat(svgEl.getAttribute('width')) || (phys ? phys.wPx : 159);
              var ha = parseFloat(svgEl.getAttribute('height')) || (phys ? phys.hPx : 159);
              svgEl.setAttribute('viewBox', '0 0 ' + wa + ' ' + ha);
            }
            var exactW = phys ? phys.wPx : Math.max(40, widthPx - 8);
            var exactH = phys ? phys.hPx : heightPx;
            svgEl.style.display = 'block';
            svgEl.style.width = exactW + 'px';
            svgEl.style.height = exactH ? (exactH + 'px') : 'auto';
            svgEl.style.maxWidth = 'none';
            svgEl.style.overflow = 'visible';
            var innerSpan = wrap.querySelector('.tsd-stamp-mark');
            if (innerSpan && innerSpan !== wrap) {
              innerSpan.style.width = exactW + 'px';
              innerSpan.style.maxWidth = 'none';
              innerSpan.style.margin = '0';
            }
          }
        }

        overlayEl.appendChild(wrap);
        created.push(wrap);
      });

      if (created.length) {
        select(created[0]);
        try { created[0].scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (_e) {}
      }
      onChange();
      return created;
    }

    /**
     * Upgrade any legacy inline stamps/signatures found inside overlayEl into positioned floating marks
     */
    function upgradeExisting() {
      var pm = getPageMetrics();
      var pageW = pm.pageW || 794;
      var idx = 0;
      Array.prototype.slice.call(overlayEl.children).forEach(function (child) {
        if (child.classList.contains('tsd-floating-mark')) {
          if (!child.style.left) child.style.left = Math.max(60, pageW - 260) + 'px';
          if (!child.style.top) child.style.top = (160 + idx * 180) + 'px';
          setAngle(child, getAngle(child));
          idx++;
          return;
        }
        if (child.classList.contains('tsd-stamp-mark') || child.classList.contains('tsd-sig-block') ||
            child.classList.contains('cw-affixed-stamp') || child.classList.contains('cw-affixed-sig')) {
          var kind = (child.classList.contains('tsd-stamp-mark') || child.classList.contains('cw-affixed-stamp')) ? 'stamp' : 'signature';
          child.classList.add('tsd-floating-mark');
          child.setAttribute('data-floating-mark', '1');
          child.setAttribute('data-mark-kind', kind);
          child.setAttribute('contenteditable', 'false');
          if (!child.style.left) child.style.left = Math.max(60, pageW - 260) + 'px';
          if (!child.style.top) child.style.top = (180 + idx * 170) + 'px';
          setAngle(child, getAngle(child));
          idx++;
        }
      });
    }

    var ctrl = {
      select: select,
      placeMark: placeMark,
      upgradeExisting: upgradeExisting,
      cleanForPersist: cleanForPersist,
      duplicateToAllPages: duplicateToAllPages,
      getSelected: function () { return selectedEl; },
    };
    overlayEl._tsFmController = ctrl;
    return ctrl;
  }

  global.TSFloatingMarks = {
    attach: attach,
    deriveInitials: deriveInitials,
    SIGNATURE_FONTS: SIGNATURE_FONTS,
    ensureSignatureFontsLoaded: ensureSignatureFontsLoaded,
    getSignatureFont: getSignatureFont,
    renderFontGallery: renderFontGallery,
    buildHandwrittenSignatureHtml: buildHandwrittenSignatureHtml,
    buildHandwrittenInitialsHtml: buildHandwrittenInitialsHtml,
    computePhysicalStampPx: computePhysicalStampPx,
  };
})(window);
