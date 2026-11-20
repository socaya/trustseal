/* ============================================================================
 * TrustSeal Luxury Dual-Tone Letterhead Pattern Engine (120 Premium Patterns)
 * Shared by Letterheads Designer (/letterheads) and TSD Document Editor.
 * ============================================================================ */
(function (global) {
  'use strict';

  var PATTERNS = [
    /* 0. Clean */
    { value: 'none', label: 'None (Clean paper)', group: 'Clean' },

    /* 1. Executive Curves & Sweeps (14) */
    { value: 'curved_band',      label: 'Curved Brand Band',       group: 'Executive Curves' },
    { value: 'top_wave',         label: 'Organic Top Wave',        group: 'Executive Curves' },
    { value: 'double_arc',       label: 'Double Arc Crest',        group: 'Executive Curves' },
    { value: 'silk_ribbon',      label: 'Silk Ribbon Sweep',       group: 'Executive Curves' },
    { value: 'scurve_meridian',  label: 'S-Curve Meridian',        group: 'Executive Curves' },
    { value: 'twin_crescent',    label: 'Twin Crescent Arcs',      group: 'Executive Curves' },
    { value: 'sovereign_horizon',label: 'Sovereign Horizon',       group: 'Executive Curves' },
    { value: 'swooping_wing',    label: 'Swooping Wing',           group: 'Executive Curves' },
    { value: 'asym_wave_duo',    label: 'Asymmetric Wave Duo',     group: 'Executive Curves' },
    { value: 'flowing_veil',     label: 'Flowing Silk Veil',       group: 'Executive Curves' },
    { value: 'executive_tide',   label: 'Executive Tide',          group: 'Executive Curves' },
    { value: 'crown_archway',    label: 'Crown Archway',           group: 'Executive Curves' },
    { value: 'ribbon_cascade',   label: 'Ribbon Cascade',          group: 'Executive Curves' },
    { value: 'velvet_swoosh',    label: 'Velvet Swoosh',           group: 'Executive Curves' },

    /* 2. Architectural & Geometric Bands (14) */
    { value: 'diagonal_band',    label: 'Diagonal Brand Band',     group: 'Architectural' },
    { value: 'prism_corner',     label: 'Prism Corner',            group: 'Architectural' },
    { value: 'minimal_corners',  label: 'Minimalist Corners',      group: 'Architectural' },
    { value: 'stepped_ziggurat', label: 'Stepped Ziggurat',        group: 'Architectural' },
    { value: 'beveled_facet',    label: 'Beveled Facet',           group: 'Architectural' },
    { value: 'split_monolith',   label: 'Split Monolith',          group: 'Architectural' },
    { value: 'origami_fold',     label: 'Origami Fold',            group: 'Architectural' },
    { value: 'bauhaus_block',    label: 'Bauhaus Corner Block',    group: 'Architectural' },
    { value: 'cantilever_stripe',label: 'Cantilever Stripe',       group: 'Architectural' },
    { value: 'angled_truss',     label: 'Angled Truss',            group: 'Architectural' },
    { value: 'isometric_wedge',  label: 'Isometric Wedge',         group: 'Architectural' },
    { value: 'diamond_facet',    label: 'Diamond Facet Header',    group: 'Architectural' },
    { value: 'dual_shard',       label: 'Dual-Tone Shard',         group: 'Architectural' },
    { value: 'geo_horizon',      label: 'Geometric Horizon',       group: 'Architectural' },

    /* 3. Pillars, Sidebars & Spine Framing (12) */
    { value: 'side_pillar',      label: 'Side Pillar Accent',      group: 'Pillars & Spines' },
    { value: 'twin_rails',       label: 'Twin Vertical Rails',     group: 'Pillars & Spines' },
    { value: 'asym_spine',       label: 'Asymmetric Spine',        group: 'Pillars & Spines' },
    { value: 'offset_ribbon_col',label: 'Offset Ribbon Column',    group: 'Pillars & Spines' },
    { value: 'exec_bookmark',    label: 'Executive Bookmark',      group: 'Pillars & Spines' },
    { value: 'stepped_pillar',   label: 'Stepped Left Pillar',     group: 'Pillars & Spines' },
    { value: 'margin_rule_arch', label: 'Architectural Margin Rule',group: 'Pillars & Spines' },
    { value: 'split_dual_pillar',label: 'Split Dual Pillar',       group: 'Pillars & Spines' },
    { value: 'spine_bracket',    label: 'Corner-to-Spine Bracket', group: 'Pillars & Spines' },
    { value: 'index_spine',      label: 'Minimalist Index Spine',  group: 'Pillars & Spines' },
    { value: 'folio_edge',       label: 'Folio Edge Trim',         group: 'Pillars & Spines' },
    { value: 'double_hairline',  label: 'Double Hairline Rail',    group: 'Pillars & Spines' },

    /* 4. Formal Frames, Certificates & Legal Borders (14) */
    { value: 'certificate_frame',label: 'Certificate Double Frame',group: 'Formal Frames' },
    { value: 'corner_brackets',  label: 'Corner Brackets',         group: 'Formal Frames' },
    { value: 'architect_frame',  label: 'Architect Frame',         group: 'Formal Frames' },
    { value: 'diplomatic_frame', label: 'Diplomatic Seal Frame',   group: 'Formal Frames' },
    { value: 'treasury_filigree',label: 'Treasury Filigree Border',group: 'Formal Frames' },
    { value: 'notch_frame',      label: 'Notch-Corner Frame',      group: 'Formal Frames' },
    { value: 'artdeco_frame',    label: 'Art Deco Frame',          group: 'Formal Frames' },
    { value: 'royal_inset',      label: 'Royal Inset Border',      group: 'Formal Frames' },
    { value: 'law_ledger_frame', label: 'Law-Firm Ledger Frame',   group: 'Formal Frames' },
    { value: 'double_miter',     label: 'Double-Mitered Frame',    group: 'Formal Frames' },
    { value: 'sovereign_plaque', label: 'Sovereign Plaque',        group: 'Formal Frames' },
    { value: 'beveled_cartouche',label: 'Beveled Cartouche',       group: 'Formal Frames' },
    { value: 'scallop_corners',  label: 'Scalloped Corner Frame',  group: 'Formal Frames' },
    { value: 'neoclassic_border',label: 'Neo-Classical Border',    group: 'Formal Frames' },

    /* 5. Guilloché, Banknote & Security Engraving (12) */
    { value: 'guilloche_wave',   label: 'Guilloché Wave',          group: 'Security & Guilloché' },
    { value: 'banknote_rosette', label: 'Banknote Rosette Corner', group: 'Security & Guilloché' },
    { value: 'spiro_crest',      label: 'Spirograph Crest',        group: 'Security & Guilloché' },
    { value: 'harmonic_sine',    label: 'Harmonic Sine Mesh',      group: 'Security & Guilloché' },
    { value: 'treasury_waveband',label: 'Treasury Waveband',       group: 'Security & Guilloché' },
    { value: 'security_micro',   label: 'Security Micro-Wave',     group: 'Security & Guilloché' },
    { value: 'concentric_ripple',label: 'Concentric Ripple Corner',group: 'Security & Guilloché' },
    { value: 'interlaced_oval',  label: 'Interlaced Ellipses',     group: 'Security & Guilloché' },
    { value: 'sovereign_braid',  label: 'Sovereign Ribbon Braid',  group: 'Security & Guilloché' },
    { value: 'moire_arc',        label: 'Moiré Security Arc',      group: 'Security & Guilloché' },
    { value: 'engraving_sweep',  label: 'Fine Engraving Sweep',    group: 'Security & Guilloché' },
    { value: 'mint_lattice',     label: 'Mint Seal Lattice',       group: 'Security & Guilloché' },

    /* 6. Art Deco, Heritage & Luxury Motifs (12) */
    { value: 'deco_sunburst',    label: 'Art Deco Sunburst',       group: 'Art Deco & Luxury' },
    { value: 'deco_fan_arch',    label: 'Fan Arch Deco',           group: 'Art Deco & Luxury' },
    { value: 'gilded_chevron',   label: 'Gilded Chevron',          group: 'Art Deco & Luxury' },
    { value: 'empire_keyline',   label: 'Empire Keyline',          group: 'Art Deco & Luxury' },
    { value: 'gatsby_rays',      label: 'Gatsby Corner Rays',      group: 'Art Deco & Luxury' },
    { value: 'deco_steps',       label: 'Stepping-Stone Deco',     group: 'Art Deco & Luxury' },
    { value: 'chrysler_crown',   label: 'Chrysler Crown',          group: 'Art Deco & Luxury' },
    { value: 'diamond_crest',    label: 'Diamond Lattice Crest',   group: 'Art Deco & Luxury' },
    { value: 'cathedral_arch',   label: 'Cathedral Arch',          group: 'Art Deco & Luxury' },
    { value: 'venetian_lattice', label: 'Venetian Lattice',        group: 'Art Deco & Luxury' },
    { value: 'heraldic_diamond', label: 'Heraldic Diamond Band',   group: 'Art Deco & Luxury' },
    { value: 'regency_laurel',   label: 'Regency Laurel Arc',      group: 'Art Deco & Luxury' },

    /* 7. Modern Tech, Fintech & Data Grids (12) */
    { value: 'dot_matrix',       label: 'Dot Matrix Grid',         group: 'Modern & Tech' },
    { value: 'hex_mesh',         label: 'Hexagonal Mesh',          group: 'Modern & Tech' },
    { value: 'subtle_grid',      label: 'Subtle Hairline Grid',    group: 'Modern & Tech' },
    { value: 'circuit_corner',   label: 'Circuit Trace Corner',    group: 'Modern & Tech' },
    { value: 'iso_cubes',        label: 'Isometric Cube Field',    group: 'Modern & Tech' },
    { value: 'orbital_rings',    label: 'Orbital Node Rings',      group: 'Modern & Tech' },
    { value: 'matrix_cascade',   label: 'Matrix Cascade',          group: 'Modern & Tech' },
    { value: 'crosshair_grid',   label: 'Precision Crosshair Grid',group: 'Modern & Tech' },
    { value: 'radar_sweep',      label: 'Radar Sweep Arc',         group: 'Modern & Tech' },
    { value: 'fiber_streams',    label: 'Fiber-Optic Streams',     group: 'Modern & Tech' },
    { value: 'constellation',    label: 'Constellation Mesh',      group: 'Modern & Tech' },
    { value: 'pixel_fade',       label: 'Pixel Gradient Fade',     group: 'Modern & Tech' },

    /* 8. Editorial, Stripes & Textured Papers (10) */
    { value: 'diagonal_lines',   label: 'Diagonal Lines',          group: 'Editorial & Stripes' },
    { value: 'ledger_stripes',   label: 'Ledger Stripes',          group: 'Editorial & Stripes' },
    { value: 'pinstripe_margin', label: 'Pinstripe Margin',        group: 'Editorial & Stripes' },
    { value: 'herringbone',      label: 'Herringbone Weave',       group: 'Editorial & Stripes' },
    { value: 'linen_crosshatch', label: 'Linen Crosshatch',        group: 'Editorial & Stripes' },
    { value: 'woven_plaid',      label: 'Woven Plaid Corner',      group: 'Editorial & Stripes' },
    { value: 'fine_ruled',       label: 'Fine Ruled Stationery',   group: 'Editorial & Stripes' },
    { value: 'tapered_speed',    label: 'Tapered Speedlines',      group: 'Editorial & Stripes' },
    { value: 'parallel_horizon', label: 'Parallel Horizon Bars',   group: 'Editorial & Stripes' },
    { value: 'acoustic_bars',    label: 'Acoustic Wave Bars',      group: 'Editorial & Stripes' },

    /* 9. Botanical, Organic & Celestial (10) */
    { value: 'water_ribbon',     label: 'Water Ribbon',            group: 'Organic & Celestial' },
    { value: 'horizon_sunrise',  label: 'Horizon Sunrise',         group: 'Organic & Celestial' },
    { value: 'aurora_bands',     label: 'Aurora Glow Bands',       group: 'Organic & Celestial' },
    { value: 'pebble_mosaic',    label: 'Pebble Mosaic Corner',    group: 'Organic & Celestial' },
    { value: 'bamboo_accent',    label: 'Bamboo Stalk Accent',     group: 'Organic & Celestial' },
    { value: 'leaf_vein_arc',    label: 'Leaf Vein Arc',           group: 'Organic & Celestial' },
    { value: 'coastal_contour',  label: 'Coastal Contour Lines',   group: 'Organic & Celestial' },
    { value: 'topo_ridge',       label: 'Topographic Ridge',       group: 'Organic & Celestial' },
    { value: 'eclipse_halo',     label: 'Eclipse Halo',            group: 'Organic & Celestial' },
    { value: 'solar_meridian',   label: 'Solar Meridian',          group: 'Organic & Celestial' },

    /* 10. Chevrons, Ribbons & Heraldic Accents (10) */
    { value: 'chevron_ribbon',   label: 'Chevron Ribbon',          group: 'Chevrons & Ribbons' },
    { value: 'double_chevron',   label: 'Double Chevron Crest',    group: 'Chevrons & Ribbons' },
    { value: 'arrowhead_banner', label: 'Arrowhead Banner',        group: 'Chevrons & Ribbons' },
    { value: 'shield_tip',       label: 'Shield Tip Header',       group: 'Chevrons & Ribbons' },
    { value: 'pennant_corner',   label: 'Pennant Flag Corner',     group: 'Chevrons & Ribbons' },
    { value: 'folded_banner',    label: 'Folded Banner Top',       group: 'Chevrons & Ribbons' },
    { value: 'heraldic_sash',    label: 'Heraldic Sash',           group: 'Chevrons & Ribbons' },
    { value: 'vcut_executive',   label: 'V-Cut Executive Header',  group: 'Chevrons & Ribbons' },
    { value: 'triple_ribbon',    label: 'Triple Ribbon Accent',    group: 'Chevrons & Ribbons' },
    { value: 'royal_sash_diag',  label: 'Royal Sash Diagonal',     group: 'Chevrons & Ribbons' },
  ];

  var _uid = 0;

  function _sinePath(y0, amp, freq, phase, step) {
    var d = 'M0,' + (y0 + Math.sin(phase) * amp).toFixed(1);
    for (var x = step; x <= 800; x += step) {
      var y = y0 + Math.sin((x / 800) * Math.PI * 2 * freq + phase) * amp;
      d += ' L' + x + ',' + y.toFixed(1);
    }
    return d;
  }

  function _rays(cx, cy, r1, r2, count, startDeg, endDeg, col, sw, op) {
    var out = '';
    for (var i = 0; i < count; i++) {
      var a = (startDeg + (endDeg - startDeg) * (i / Math.max(1, count - 1))) * Math.PI / 180;
      out += '<line x1="' + (cx + Math.cos(a) * r1).toFixed(1) + '" y1="' + (cy + Math.sin(a) * r1).toFixed(1) +
        '" x2="' + (cx + Math.cos(a) * r2).toFixed(1) + '" y2="' + (cy + Math.sin(a) * r2).toFixed(1) +
        '" stroke="' + col + '" stroke-width="' + sw + '" stroke-opacity="' + op + '"/>';
    }
    return out;
  }

  function _concentric(cx, cy, rStart, step, count, p, b, sw, op) {
    var out = '';
    for (var i = 0; i < count; i++) {
      var col = (i % 2 === 0) ? p : b;
      out += '<circle cx="' + cx + '" cy="' + cy + '" r="' + (rStart + i * step) +
        '" fill="none" stroke="' + col + '" stroke-width="' + sw + '" stroke-opacity="' + op + '"/>';
    }
    return out;
  }

  function buildPatternBody(key, p, b, uid) {
    var body = '';
    var i, x, y;

    /* ---- 1. Executive Curves & Sweeps ---- */
    if (key === 'curved_band') {
      return '<path d="M0,0 L560,0 C420,95 210,125 0,105 Z" fill="' + p + '" fill-opacity="0.14"/>' +
        '<path d="M0,108 C220,128 430,96 580,0" fill="none" stroke="' + b + '" stroke-width="5" stroke-opacity="0.26"/>' +
        '<path d="M800,1120 L260,1120 C400,1030 610,1005 800,1022 Z" fill="' + p + '" fill-opacity="0.11"/>';
    }
    if (key === 'top_wave') {
      return '<path d="M0,0 L800,0 L800,96 Q600,148 400,94 T0,118 Z" fill="' + p + '" fill-opacity="0.14"/>' +
        '<path d="M0,124 Q200,82 400,102 T800,102" fill="none" stroke="' + b + '" stroke-width="4" stroke-opacity="0.28"/>' +
        '<path d="M0,1120 L0,1045 Q260,998 520,1065 T800,1030 L800,1120 Z" fill="' + p + '" fill-opacity="0.11"/>';
    }
    if (key === 'double_arc') {
      return '<circle cx="0" cy="0" r="240" fill="none" stroke="' + p + '" stroke-width="24" stroke-opacity="0.11"/>' +
        '<circle cx="0" cy="0" r="264" fill="none" stroke="' + b + '" stroke-width="5" stroke-opacity="0.26"/>' +
        '<circle cx="800" cy="1120" r="220" fill="none" stroke="' + p + '" stroke-width="20" stroke-opacity="0.10"/>' +
        '<circle cx="800" cy="1120" r="242" fill="none" stroke="' + b + '" stroke-width="4" stroke-opacity="0.22"/>';
    }
    if (key === 'silk_ribbon') {
      return '<path d="M0,45 C240,140 540,-10 800,72 L800,112 C540,35 240,175 0,88 Z" fill="' + p + '" fill-opacity="0.12"/>' +
        '<path d="M0,88 C240,175 540,35 800,112" fill="none" stroke="' + b + '" stroke-width="3.5" stroke-opacity="0.32"/>' +
        '<path d="M0,1048 C260,995 540,1095 800,1035 L800,1072 C540,1122 260,1025 0,1078 Z" fill="' + p + '" fill-opacity="0.10"/>';
    }
    if (key === 'scurve_meridian') {
      return '<path d="M0,0 L165,0 C95,280 220,560 95,840 C40,965 110,1055 155,1120 L0,1120 Z" fill="' + p + '" fill-opacity="0.09"/>' +
        '<path d="M165,0 C95,280 220,560 95,840 C40,965 110,1055 155,1120" fill="none" stroke="' + b + '" stroke-width="3" stroke-opacity="0.28"/>';
    }
    if (key === 'twin_crescent') {
      return '<path d="M0,0 L340,0 A340,150 0 0,1 0,150 Z" fill="' + p + '" fill-opacity="0.13"/>' +
        '<path d="M800,0 L460,0 A340,120 0 0,0 800,120 Z" fill="' + b + '" fill-opacity="0.11"/>' +
        '<path d="M0,1120 L320,1120 A320,110 0 0,0 0,1010 Z" fill="' + b + '" fill-opacity="0.09"/>' +
        '<path d="M800,1120 L480,1120 A320,130 0 0,1 800,990 Z" fill="' + p + '" fill-opacity="0.12"/>';
    }
    if (key === 'sovereign_horizon') {
      return '<path d="M0,0 L800,0 L800,64 Q400,138 0,64 Z" fill="' + p + '" fill-opacity="0.13"/>' +
        '<path d="M0,70 Q400,146 800,70" fill="none" stroke="' + b + '" stroke-width="3.5" stroke-opacity="0.34"/>' +
        '<path d="M0,1120 L800,1120 L800,1064 Q400,1005 0,1064 Z" fill="' + p + '" fill-opacity="0.11"/>';
    }
    if (key === 'swooping_wing') {
      return '<path d="M0,0 L800,0 L800,42 C560,30 310,145 0,130 Z" fill="' + p + '" fill-opacity="0.14"/>' +
        '<path d="M0,136 C310,152 560,38 800,50" fill="none" stroke="' + b + '" stroke-width="4" stroke-opacity="0.30"/>' +
        '<path d="M800,1120 L0,1120 L0,1084 C240,1095 490,995 800,1010 Z" fill="' + p + '" fill-opacity="0.11"/>';
    }
    if (key === 'asym_wave_duo') {
      return '<path d="M0,0 L800,0 L800,78 C620,130 340,22 0,92 Z" fill="' + p + '" fill-opacity="0.12"/>' +
        '<path d="M0,0 L800,0 L800,54 C580,10 290,122 0,68 Z" fill="' + b + '" fill-opacity="0.10"/>' +
        '<path d="M0,1120 L800,1120 L800,1044 C560,995 260,1095 0,1040 Z" fill="' + p + '" fill-opacity="0.10"/>';
    }
    if (key === 'flowing_veil') {
      for (i = 0; i < 6; i++) {
        body += '<path d="M0,' + (24 + i * 14) + ' C250,' + (92 - i * 8) + ' 550,' + (10 + i * 10) + ' 800,' + (66 + i * 7) +
          '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.8" stroke-opacity="' + (0.24 - i * 0.02).toFixed(2) + '"/>';
      }
      return body + '<path d="M0,1080 C280,1020 520,1105 800,1050" fill="none" stroke="' + b + '" stroke-width="2.5" stroke-opacity="0.25"/>';
    }
    if (key === 'executive_tide') {
      return '<path d="M0,0 L800,0 L800,110 C650,60 520,135 360,88 C210,44 100,112 0,76 Z" fill="' + p + '" fill-opacity="0.13"/>' +
        '<path d="M0,84 C100,120 210,52 360,96 C520,143 650,68 800,118" fill="none" stroke="' + b + '" stroke-width="3" stroke-opacity="0.28"/>' +
        '<path d="M0,1120 L800,1120 L800,1050 C600,1090 360,1010 0,1068 Z" fill="' + p + '" fill-opacity="0.10"/>';
    }
    if (key === 'crown_archway') {
      return '<path d="M0,125 Q400,-30 800,125 L800,0 L0,0 Z" fill="' + p + '" fill-opacity="0.14"/>' +
        '<path d="M0,132 Q400,-22 800,132" fill="none" stroke="' + b + '" stroke-width="3.2" stroke-opacity="0.30"/>' +
        '<path d="M0,998 Q400,1145 800,998 L800,1120 L0,1120 Z" fill="' + p + '" fill-opacity="0.11"/>';
    }
    if (key === 'ribbon_cascade') {
      return '<path d="M620,0 C660,180 740,260 800,320 L800,0 Z" fill="' + p + '" fill-opacity="0.13"/>' +
        '<path d="M665,0 C700,150 755,220 800,275 L800,0 Z" fill="' + b + '" fill-opacity="0.14"/>' +
        '<path d="M180,1120 C140,940 60,860 0,800 L0,1120 Z" fill="' + p + '" fill-opacity="0.11"/>';
    }
    if (key === 'velvet_swoosh') {
      return '<path d="M0,0 L480,0 C340,52 170,84 0,72 Z" fill="' + p + '" fill-opacity="0.16"/>' +
        '<path d="M360,0 L640,0 C480,68 250,106 0,92 L0,72 C170,84 340,52 480,0 Z" fill="' + b + '" fill-opacity="0.13"/>' +
        '<path d="M800,1120 L320,1120 C460,1068 630,1036 800,1048 Z" fill="' + p + '" fill-opacity="0.13"/>';
    }

    /* ---- 2. Architectural & Geometric Bands ---- */
    if (key === 'diagonal_band') {
      return '<polygon points="0,0 800,0 800,125 0,48" fill="' + p + '" fill-opacity="0.12"/>' +
        '<polygon points="0,48 800,125 800,136 0,59" fill="' + b + '" fill-opacity="0.24"/>' +
        '<polygon points="0,1072 800,1010 800,1120 0,1120" fill="' + p + '" fill-opacity="0.10"/>';
    }
    if (key === 'prism_corner') {
      return '<polygon points="0,0 250,0 0,200" fill="' + p + '" fill-opacity="0.14"/>' +
        '<polygon points="0,0 140,0 0,115" fill="' + b + '" fill-opacity="0.22"/>' +
        '<polygon points="800,1120 550,1120 800,920" fill="' + p + '" fill-opacity="0.12"/>' +
        '<polygon points="800,1120 670,1120 800,1010" fill="' + b + '" fill-opacity="0.18"/>';
    }
    if (key === 'minimal_corners') {
      return '<polygon points="0,0 115,0 0,115" fill="' + p + '" fill-opacity="0.17"/>' +
        '<polygon points="800,1120 685,1120 800,1005" fill="' + b + '" fill-opacity="0.22"/>';
    }
    if (key === 'stepped_ziggurat') {
      return '<polygon points="0,0 800,0 800,36 620,36 590,66 210,66 180,36 0,36" fill="' + p + '" fill-opacity="0.13"/>' +
        '<polyline points="0,42 180,42 210,72 590,72 620,42 800,42" fill="none" stroke="' + b + '" stroke-width="3" stroke-opacity="0.30"/>' +
        '<polygon points="0,1120 800,1120 800,1084 620,1084 590,1054 210,1054 180,1084 0,1084" fill="' + p + '" fill-opacity="0.11"/>';
    }
    if (key === 'beveled_facet') {
      return '<polygon points="0,0 800,0 740,78 60,78" fill="' + p + '" fill-opacity="0.12"/>' +
        '<polygon points="0,0 60,78 0,110" fill="' + b + '" fill-opacity="0.18"/>' +
        '<polygon points="800,0 740,78 800,110" fill="' + b + '" fill-opacity="0.18"/>' +
        '<polygon points="0,1120 800,1120 740,1050 60,1050" fill="' + p + '" fill-opacity="0.10"/>';
    }
    if (key === 'split_monolith') {
      return '<rect x="0" y="0" width="520" height="24" fill="' + p + '" fill-opacity="0.22"/>' +
        '<rect x="528" y="0" width="272" height="24" fill="' + b + '" fill-opacity="0.28"/>' +
        '<rect x="0" y="1096" width="272" height="24" fill="' + b + '" fill-opacity="0.24"/>' +
        '<rect x="280" y="1096" width="520" height="24" fill="' + p + '" fill-opacity="0.18"/>';
    }
    if (key === 'origami_fold') {
      return '<polygon points="0,0 320,0 210,96 0,60" fill="' + p + '" fill-opacity="0.14"/>' +
        '<polygon points="320,0 540,0 210,96" fill="' + b + '" fill-opacity="0.13"/>' +
        '<polygon points="800,1120 480,1120 590,1024 800,1060" fill="' + p + '" fill-opacity="0.12"/>' +
        '<polygon points="480,1120 260,1120 590,1024" fill="' + b + '" fill-opacity="0.11"/>';
    }
    if (key === 'bauhaus_block') {
      return '<rect x="0" y="0" width="90" height="90" fill="' + p + '" fill-opacity="0.18"/>' +
        '<rect x="90" y="0" width="45" height="45" fill="' + b + '" fill-opacity="0.24"/>' +
        '<circle cx="112" cy="68" r="18" fill="' + p + '" fill-opacity="0.14"/>' +
        '<rect x="710" y="1030" width="90" height="90" fill="' + p + '" fill-opacity="0.14"/>' +
        '<rect x="665" y="1075" width="45" height="45" fill="' + b + '" fill-opacity="0.22"/>';
    }
    if (key === 'cantilever_stripe') {
      return '<rect x="0" y="0" width="800" height="14" fill="' + p + '" fill-opacity="0.20"/>' +
        '<rect x="0" y="20" width="420" height="6" fill="' + b + '" fill-opacity="0.32"/>' +
        '<rect x="380" y="1094" width="420" height="6" fill="' + b + '" fill-opacity="0.28"/>' +
        '<rect x="0" y="1106" width="800" height="14" fill="' + p + '" fill-opacity="0.18"/>';
    }
    if (key === 'angled_truss') {
      return '<polygon points="0,0 800,0 800,28 0,88" fill="' + p + '" fill-opacity="0.12"/>' +
        '<line x1="0" y1="92" x2="800" y2="32" stroke="' + b + '" stroke-width="3" stroke-opacity="0.30"/>' +
        '<line x1="0" y1="100" x2="800" y2="40" stroke="' + p + '" stroke-width="1.2" stroke-opacity="0.22"/>' +
        '<polygon points="0,1092 800,1032 800,1120 0,1120" fill="' + p + '" fill-opacity="0.10"/>';
    }
    if (key === 'isometric_wedge') {
      return '<polygon points="0,0 400,0 0,145" fill="' + p + '" fill-opacity="0.12"/>' +
        '<polygon points="400,0 800,0 800,82" fill="' + b + '" fill-opacity="0.12"/>' +
        '<polygon points="0,1038 0,1120 400,1120" fill="' + b + '" fill-opacity="0.11"/>' +
        '<polygon points="800,975 800,1120 400,1120" fill="' + p + '" fill-opacity="0.12"/>';
    }
    if (key === 'diamond_facet') {
      return '<polygon points="400,0 800,0 800,72 400,122 0,72 0,0" fill="' + p + '" fill-opacity="0.11"/>' +
        '<polyline points="0,76 400,126 800,76" fill="none" stroke="' + b + '" stroke-width="3" stroke-opacity="0.30"/>' +
        '<polygon points="400,1010 800,1055 800,1120 0,1120 0,1055" fill="' + p + '" fill-opacity="0.09"/>';
    }
    if (key === 'dual_shard') {
      return '<polygon points="560,0 800,0 800,190" fill="' + p + '" fill-opacity="0.14"/>' +
        '<polygon points="650,0 800,0 800,120" fill="' + b + '" fill-opacity="0.20"/>' +
        '<polygon points="0,930 240,1120 0,1120" fill="' + p + '" fill-opacity="0.12"/>' +
        '<polygon points="0,1000 150,1120 0,1120" fill="' + b + '" fill-opacity="0.18"/>';
    }
    if (key === 'geo_horizon') {
      return '<rect x="0" y="0" width="800" height="72" fill="' + p + '" fill-opacity="0.09"/>' +
        '<polygon points="0,72 260,72 300,96 0,96" fill="' + p + '" fill-opacity="0.15"/>' +
        '<polygon points="260,72 340,72 380,96 300,96" fill="' + b + '" fill-opacity="0.26"/>' +
        '<rect x="0" y="1062" width="800" height="58" fill="' + p + '" fill-opacity="0.08"/>';
    }

    /* ---- 3. Pillars, Sidebars & Spine Framing ---- */
    if (key === 'side_pillar') {
      return '<rect x="0" y="0" width="22" height="1120" fill="' + p + '" fill-opacity="0.22"/>' +
        '<rect x="22" y="0" width="5" height="1120" fill="' + b + '" fill-opacity="0.38"/>';
    }
    if (key === 'twin_rails') {
      return '<rect x="0" y="0" width="10" height="1120" fill="' + p + '" fill-opacity="0.22"/>' +
        '<rect x="14" y="0" width="3" height="1120" fill="' + b + '" fill-opacity="0.34"/>' +
        '<rect x="783" y="0" width="3" height="1120" fill="' + b + '" fill-opacity="0.34"/>' +
        '<rect x="790" y="0" width="10" height="1120" fill="' + p + '" fill-opacity="0.22"/>';
    }
    if (key === 'asym_spine') {
      return '<rect x="0" y="0" width="34" height="320" fill="' + p + '" fill-opacity="0.20"/>' +
        '<rect x="0" y="320" width="34" height="120" fill="' + b + '" fill-opacity="0.26"/>' +
        '<rect x="0" y="440" width="12" height="680" fill="' + p + '" fill-opacity="0.14"/>';
    }
    if (key === 'offset_ribbon_col') {
      return '<rect x="24" y="0" width="14" height="1120" fill="' + p + '" fill-opacity="0.14"/>' +
        '<rect x="42" y="0" width="3" height="1120" fill="' + b + '" fill-opacity="0.32"/>';
    }
    if (key === 'exec_bookmark') {
      return '<polygon points="710,0 762,0 762,150 736,126 710,150" fill="' + p + '" fill-opacity="0.20"/>' +
        '<polygon points="718,0 754,0 754,136 736,118 718,136" fill="none" stroke="' + b + '" stroke-width="2" stroke-opacity="0.45"/>' +
        '<rect x="0" y="1108" width="800" height="12" fill="' + p + '" fill-opacity="0.16"/>';
    }
    if (key === 'stepped_pillar') {
      return '<polygon points="0,0 44,0 44,240 24,260 24,860 44,880 44,1120 0,1120" fill="' + p + '" fill-opacity="0.16"/>' +
        '<polyline points="48,0 48,242 28,262 28,858 48,878 48,1120" fill="none" stroke="' + b + '" stroke-width="2.5" stroke-opacity="0.34"/>';
    }
    if (key === 'margin_rule_arch') {
      return '<line x1="48" y1="32" x2="48" y2="1088" stroke="' + p + '" stroke-width="2" stroke-opacity="0.24"/>' +
        '<line x1="54" y1="32" x2="54" y2="1088" stroke="' + b + '" stroke-width="1" stroke-opacity="0.36"/>' +
        '<circle cx="48" cy="32" r="4" fill="' + b + '" fill-opacity="0.45"/>' +
        '<circle cx="48" cy="1088" r="4" fill="' + b + '" fill-opacity="0.45"/>';
    }
    if (key === 'split_dual_pillar') {
      return '<rect x="0" y="0" width="16" height="560" fill="' + p + '" fill-opacity="0.22"/>' +
        '<rect x="0" y="560" width="16" height="560" fill="' + b + '" fill-opacity="0.24"/>' +
        '<rect x="784" y="0" width="16" height="560" fill="' + b + '" fill-opacity="0.24"/>' +
        '<rect x="784" y="560" width="16" height="560" fill="' + p + '" fill-opacity="0.22"/>';
    }
    if (key === 'spine_bracket') {
      return '<path d="M180,24 L24,24 L24,1096 L180,1096" fill="none" stroke="' + p + '" stroke-width="3.5" stroke-opacity="0.28"/>' +
        '<path d="M160,34 L34,34 L34,1086 L160,1086" fill="none" stroke="' + b + '" stroke-width="1.5" stroke-opacity="0.40"/>';
    }
    if (key === 'index_spine') {
      for (i = 0; i < 14; i++) {
        body += '<rect x="0" y="' + (40 + i * 74) + '" width="' + (i % 3 === 0 ? 18 : 10) + '" height="22" fill="' + (i % 2 === 0 ? p : b) + '" fill-opacity="0.24"/>';
      }
      return body;
    }
    if (key === 'folio_edge') {
      return '<rect x="774" y="0" width="26" height="1120" fill="' + p + '" fill-opacity="0.16"/>' +
        '<rect x="768" y="0" width="4" height="1120" fill="' + b + '" fill-opacity="0.34"/>';
    }
    if (key === 'double_hairline') {
      return '<line x1="20" y1="0" x2="20" y2="1120" stroke="' + p + '" stroke-width="1.5" stroke-opacity="0.26"/>' +
        '<line x1="26" y1="0" x2="26" y2="1120" stroke="' + b + '" stroke-width="1" stroke-opacity="0.36"/>' +
        '<line x1="774" y1="0" x2="774" y2="1120" stroke="' + b + '" stroke-width="1" stroke-opacity="0.36"/>' +
        '<line x1="780" y1="0" x2="780" y2="1120" stroke="' + p + '" stroke-width="1.5" stroke-opacity="0.26"/>';
    }

    /* ---- 4. Formal Frames, Certificates & Legal Borders ---- */
    if (key === 'certificate_frame') {
      return '<rect x="18" y="18" width="764" height="1084" fill="none" stroke="' + p + '" stroke-width="3.2" stroke-opacity="0.32"/>' +
        '<rect x="26" y="26" width="748" height="1068" fill="none" stroke="' + b + '" stroke-width="1.5" stroke-opacity="0.45"/>' +
        '<circle cx="34" cy="34" r="4.5" fill="' + b + '" fill-opacity="0.55"/>' +
        '<circle cx="766" cy="34" r="4.5" fill="' + b + '" fill-opacity="0.55"/>' +
        '<circle cx="34" cy="1086" r="4.5" fill="' + b + '" fill-opacity="0.55"/>' +
        '<circle cx="766" cy="1086" r="4.5" fill="' + b + '" fill-opacity="0.55"/>';
    }
    if (key === 'corner_brackets') {
      return '<path d="M22,84 L22,22 L84,22 M716,22 L778,22 L778,84 M22,1036 L22,1098 L84,1098 M716,1098 L778,1098 L778,1036" fill="none" stroke="' + p + '" stroke-width="4" stroke-opacity="0.36"/>' +
        '<path d="M32,74 L32,32 L74,32 M726,32 L768,32 L768,74 M32,1046 L32,1088 L74,1088 M726,1088 L768,1088 L768,1046" fill="none" stroke="' + b + '" stroke-width="2" stroke-opacity="0.46"/>';
    }
    if (key === 'architect_frame') {
      return '<rect x="16" y="16" width="768" height="1088" fill="none" stroke="' + p + '" stroke-width="1.6" stroke-opacity="0.28"/>' +
        '<line x1="16" y1="124" x2="784" y2="124" stroke="' + b + '" stroke-width="1.5" stroke-opacity="0.32"/>' +
        '<line x1="16" y1="1036" x2="784" y2="1036" stroke="' + b + '" stroke-width="1.5" stroke-opacity="0.32"/>';
    }
    if (key === 'diplomatic_frame') {
      return '<rect x="14" y="14" width="772" height="1092" fill="none" stroke="' + p + '" stroke-width="6" stroke-opacity="0.18"/>' +
        '<rect x="24" y="24" width="752" height="1072" fill="none" stroke="' + b + '" stroke-width="2" stroke-opacity="0.38"/>' +
        '<rect x="30" y="30" width="740" height="1060" fill="none" stroke="' + p + '" stroke-width="0.9" stroke-opacity="0.25"/>';
    }
    if (key === 'treasury_filigree') {
      return '<rect x="18" y="18" width="764" height="1084" fill="none" stroke="' + p + '" stroke-width="2.2" stroke-opacity="0.30"/>' +
        '<rect x="26" y="26" width="748" height="1068" fill="none" stroke="' + b + '" stroke-width="1.8" stroke-dasharray="6,4" stroke-opacity="0.45"/>' +
        '<rect x="34" y="34" width="732" height="1052" fill="none" stroke="' + p + '" stroke-width="1" stroke-opacity="0.24"/>';
    }
    if (key === 'notch_frame') {
      return '<path d="M52,18 L748,18 L782,52 L782,1068 L748,1102 L52,1102 L18,1068 L18,52 Z" fill="none" stroke="' + p + '" stroke-width="2.8" stroke-opacity="0.32"/>' +
        '<path d="M58,28 L742,28 L772,58 L772,1062 L742,1092 L58,1092 L28,1062 L28,58 Z" fill="none" stroke="' + b + '" stroke-width="1.4" stroke-opacity="0.44"/>';
    }
    if (key === 'artdeco_frame') {
      return '<rect x="20" y="20" width="760" height="1080" fill="none" stroke="' + p + '" stroke-width="2.2" stroke-opacity="0.30"/>' +
        '<path d="M20,58 L58,58 L58,20 M742,20 L742,58 L780,58 M20,1062 L58,1062 L58,1100 M742,1100 L742,1062 L780,1062" fill="none" stroke="' + b + '" stroke-width="2.4" stroke-opacity="0.48"/>' +
        '<rect x="32" y="32" width="736" height="1056" fill="none" stroke="' + b + '" stroke-width="1" stroke-opacity="0.30"/>';
    }
    if (key === 'royal_inset') {
      return '<rect x="16" y="16" width="768" height="1088" fill="none" stroke="' + p + '" stroke-width="4" stroke-opacity="0.24"/>' +
        '<path d="M16,44 Q44,44 44,16 M756,16 Q756,44 784,44 M16,1076 Q44,1076 44,1104 M756,1104 Q756,1076 784,1076" fill="none" stroke="' + b + '" stroke-width="3" stroke-opacity="0.46"/>';
    }
    if (key === 'law_ledger_frame') {
      return '<line x1="36" y1="18" x2="764" y2="18" stroke="' + p + '" stroke-width="3" stroke-opacity="0.34"/>' +
        '<line x1="36" y1="24" x2="764" y2="24" stroke="' + b + '" stroke-width="1.2" stroke-opacity="0.42"/>' +
        '<line x1="36" y1="1096" x2="764" y2="1096" stroke="' + b + '" stroke-width="1.2" stroke-opacity="0.42"/>' +
        '<line x1="36" y1="1102" x2="764" y2="1102" stroke="' + p + '" stroke-width="3" stroke-opacity="0.34"/>';
    }
    if (key === 'double_miter') {
      return '<rect x="16" y="16" width="768" height="1088" fill="none" stroke="' + p + '" stroke-width="2" stroke-opacity="0.28"/>' +
        '<rect x="28" y="28" width="744" height="1064" fill="none" stroke="' + p + '" stroke-width="2" stroke-opacity="0.22"/>' +
        '<line x1="16" y1="16" x2="48" y2="48" stroke="' + b + '" stroke-width="2" stroke-opacity="0.45"/>' +
        '<line x1="784" y1="16" x2="752" y2="48" stroke="' + b + '" stroke-width="2" stroke-opacity="0.45"/>' +
        '<line x1="16" y1="1104" x2="48" y2="1072" stroke="' + b + '" stroke-width="2" stroke-opacity="0.45"/>' +
        '<line x1="784" y1="1104" x2="752" y2="1072" stroke="' + b + '" stroke-width="2" stroke-opacity="0.45"/>';
    }
    if (key === 'sovereign_plaque') {
      return '<rect x="22" y="22" width="756" height="1076" rx="18" fill="none" stroke="' + p + '" stroke-width="2.6" stroke-opacity="0.30"/>' +
        '<rect x="30" y="30" width="740" height="1060" rx="14" fill="none" stroke="' + b + '" stroke-width="1.3" stroke-opacity="0.42"/>';
    }
    if (key === 'beveled_cartouche') {
      return '<path d="M60,20 L740,20 Q780,20 780,60 L780,1060 Q780,1100 740,1100 L60,1100 Q20,1100 20,1060 L20,60 Q20,20 60,20 Z" fill="none" stroke="' + p + '" stroke-width="2.5" stroke-opacity="0.28"/>' +
        '<polygon points="400,8 414,20 400,32 386,20" fill="' + b + '" fill-opacity="0.48"/>' +
        '<polygon points="400,1088 414,1100 400,1112 386,1100" fill="' + b + '" fill-opacity="0.48"/>';
    }
    if (key === 'scallop_corners') {
      return '<rect x="22" y="22" width="756" height="1076" fill="none" stroke="' + p + '" stroke-width="2" stroke-opacity="0.26"/>' +
        '<circle cx="22" cy="22" r="26" fill="none" stroke="' + b + '" stroke-width="2" stroke-opacity="0.40"/>' +
        '<circle cx="778" cy="22" r="26" fill="none" stroke="' + b + '" stroke-width="2" stroke-opacity="0.40"/>' +
        '<circle cx="22" cy="1098" r="26" fill="none" stroke="' + b + '" stroke-width="2" stroke-opacity="0.40"/>' +
        '<circle cx="778" cy="1098" r="26" fill="none" stroke="' + b + '" stroke-width="2" stroke-opacity="0.40"/>';
    }
    if (key === 'neoclassic_border') {
      return '<rect x="14" y="14" width="772" height="1092" fill="none" stroke="' + p + '" stroke-width="1.5" stroke-opacity="0.28"/>' +
        '<rect x="22" y="22" width="756" height="1076" fill="none" stroke="' + p + '" stroke-width="3.5" stroke-opacity="0.22"/>' +
        '<rect x="30" y="30" width="740" height="1060" fill="none" stroke="' + b + '" stroke-width="1.2" stroke-opacity="0.45"/>';
    }

    /* ---- 5. Guilloché, Banknote & Security Engraving ---- */
    if (key === 'guilloche_wave') {
      return '<path d="' + _sinePath(165, 22, 2, 0, 20) + '" fill="none" stroke="' + p + '" stroke-width="1.4" stroke-opacity="0.24"/>' +
        '<path d="' + _sinePath(175, 22, 2, 0.9, 20) + '" fill="none" stroke="' + b + '" stroke-width="1.4" stroke-opacity="0.30"/>' +
        '<path d="' + _sinePath(185, 22, 2, 1.8, 20) + '" fill="none" stroke="' + p + '" stroke-width="1.2" stroke-opacity="0.20"/>' +
        '<path d="' + _sinePath(985, 18, 2, 0.4, 20) + '" fill="none" stroke="' + p + '" stroke-width="1.4" stroke-opacity="0.20"/>' +
        '<path d="' + _sinePath(995, 18, 2, 1.3, 20) + '" fill="none" stroke="' + b + '" stroke-width="1.4" stroke-opacity="0.26"/>';
    }
    if (key === 'banknote_rosette') {
      for (i = 0; i < 12; i++) {
        body += '<ellipse cx="0" cy="0" rx="140" ry="52" transform="rotate(' + (i * 15) + ' 0 0)" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1" stroke-opacity="0.22"/>';
        body += '<ellipse cx="800" cy="1120" rx="140" ry="52" transform="rotate(' + (i * 15) + ' 800 1120)" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1" stroke-opacity="0.20"/>';
      }
      return body;
    }
    if (key === 'spiro_crest') {
      for (i = 0; i < 10; i++) {
        body += '<ellipse cx="400" cy="24" rx="220" ry="44" transform="rotate(' + (i * 18) + ' 400 24)" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1" stroke-opacity="0.18"/>';
      }
      return body + '<line x1="0" y1="1104" x2="800" y2="1104" stroke="' + p + '" stroke-width="3" stroke-opacity="0.22"/>';
    }
    if (key === 'harmonic_sine') {
      for (i = 0; i < 7; i++) {
        body += '<path d="' + _sinePath(60 + i * 8, 18, 3, i * 0.45, 16) + '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.1" stroke-opacity="0.22"/>';
        body += '<path d="' + _sinePath(1030 + i * 7, 14, 3, i * 0.45, 16) + '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.1" stroke-opacity="0.18"/>';
      }
      return body;
    }
    if (key === 'treasury_waveband') {
      for (i = 0; i < 5; i++) {
        body += '<path d="' + _sinePath(28 + i * 6, 10, 6, i * 0.7, 10) + '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.1" stroke-opacity="0.26"/>';
        body += '<path d="' + _sinePath(1070 + i * 6, 10, 6, i * 0.7, 10) + '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.1" stroke-opacity="0.24"/>';
      }
      return body;
    }
    if (key === 'security_micro') {
      return '<defs><pattern id="pt-' + uid + '" width="40" height="16" patternUnits="userSpaceOnUse">' +
        '<path d="M0,8 Q10,1 20,8 T40,8" fill="none" stroke="' + p + '" stroke-width="0.9" stroke-opacity="0.16"/>' +
        '<path d="M0,12 Q10,5 20,12 T40,12" fill="none" stroke="' + b + '" stroke-width="0.7" stroke-opacity="0.18"/>' +
        '</pattern></defs><rect x="0" y="0" width="800" height="115" fill="url(#pt-' + uid + ')"/><rect x="0" y="1025" width="800" height="95" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'concentric_ripple') {
      return _concentric(0, 0, 30, 18, 11, p, b, 1.3, 0.22) + _concentric(800, 1120, 30, 18, 10, p, b, 1.3, 0.20);
    }
    if (key === 'interlaced_oval') {
      for (i = 0; i < 9; i++) {
        body += '<ellipse cx="' + (60 + i * 85) + '" cy="28" rx="68" ry="22" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.2" stroke-opacity="0.25"/>';
        body += '<ellipse cx="' + (60 + i * 85) + '" cy="1092" rx="68" ry="22" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.2" stroke-opacity="0.22"/>';
      }
      return body;
    }
    if (key === 'sovereign_braid') {
      for (i = 0; i < 4; i++) {
        body += '<path d="' + _sinePath(24, 14, 5, i * 1.57, 12) + '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.5" stroke-opacity="0.28"/>';
        body += '<path d="' + _sinePath(1094, 14, 5, i * 1.57, 12) + '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.5" stroke-opacity="0.25"/>';
      }
      return body;
    }
    if (key === 'moire_arc') {
      return _concentric(400, -140, 180, 14, 14, p, b, 1.1, 0.20) + _concentric(400, 1260, 180, 14, 12, p, b, 1.1, 0.18);
    }
    if (key === 'engraving_sweep') {
      for (i = 0; i < 12; i++) {
        body += '<path d="M0,' + (10 + i * 9) + ' Q400,' + (140 - i * 6) + ' 800,' + (18 + i * 8) + '" fill="none" stroke="' + (i % 3 === 0 ? b : p) + '" stroke-width="0.9" stroke-opacity="0.20"/>';
      }
      return body;
    }
    if (key === 'mint_lattice') {
      return '<defs><pattern id="pt-' + uid + '" width="26" height="26" patternUnits="userSpaceOnUse">' +
        '<path d="M0,13 L13,0 L26,13 L13,26 Z" fill="none" stroke="' + p + '" stroke-width="0.9" stroke-opacity="0.18"/>' +
        '<circle cx="13" cy="13" r="1.5" fill="' + b + '" fill-opacity="0.26"/>' +
        '</pattern></defs><rect x="0" y="0" width="800" height="96" fill="url(#pt-' + uid + ')"/><rect x="0" y="1044" width="800" height="76" fill="url(#pt-' + uid + ')"/>';
    }

    /* ---- 6. Art Deco, Heritage & Luxury Motifs ---- */
    if (key === 'deco_sunburst') {
      return _rays(400, 0, 20, 260, 21, 10, 170, p, 1.6, 0.20) +
        _rays(400, 0, 20, 190, 11, 18, 162, b, 1.4, 0.28) +
        '<rect x="0" y="1104" width="800" height="16" fill="' + p + '" fill-opacity="0.16"/>';
    }
    if (key === 'deco_fan_arch') {
      for (i = 0; i < 8; i++) {
        var cx = 50 + i * 100;
        body += '<path d="M' + (cx - 48) + ',68 A48,48 0 0,1 ' + (cx + 48) + ',68" fill="none" stroke="' + p + '" stroke-width="1.5" stroke-opacity="0.24"/>';
        body += '<path d="M' + (cx - 32) + ',68 A32,32 0 0,1 ' + (cx + 32) + ',68" fill="none" stroke="' + b + '" stroke-width="1.3" stroke-opacity="0.30"/>';
      }
      return body + '<line x1="0" y1="68" x2="800" y2="68" stroke="' + p + '" stroke-width="2" stroke-opacity="0.26"/>';
    }
    if (key === 'gilded_chevron') {
      for (i = 0; i < 4; i++) {
        body += '<polyline points="0,' + (16 + i * 14) + ' 400,' + (58 + i * 14) + ' 800,' + (16 + i * 14) +
          '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="2.2" stroke-opacity="0.28"/>';
      }
      return body + '<polyline points="0,1104 400,1062 800,1104" fill="none" stroke="' + b + '" stroke-width="2.5" stroke-opacity="0.30"/>';
    }
    if (key === 'empire_keyline') {
      return '<path d="M16,64 L16,16 L784,16 L784,64 M32,56 L32,32 L768,32 L768,56" fill="none" stroke="' + p + '" stroke-width="2.2" stroke-opacity="0.30"/>' +
        '<path d="M16,1056 L16,1104 L784,1104 L784,1056 M32,1064 L32,1088 L768,1088 L768,1064" fill="none" stroke="' + b + '" stroke-width="2" stroke-opacity="0.36"/>';
    }
    if (key === 'gatsby_rays') {
      return _rays(0, 0, 12, 240, 13, 5, 85, p, 1.8, 0.22) + _rays(0, 0, 12, 170, 7, 12, 78, b, 1.6, 0.30) +
        _rays(800, 1120, 12, 220, 13, 185, 265, p, 1.8, 0.20);
    }
    if (key === 'deco_steps') {
      return '<path d="M0,120 L40,120 L40,80 L80,80 L80,40 L120,40 L120,0 L0,0 Z" fill="' + p + '" fill-opacity="0.16"/>' +
        '<path d="M800,120 L760,120 L760,80 L720,80 L720,40 L680,40 L680,0 L800,0 Z" fill="' + b + '" fill-opacity="0.16"/>' +
        '<path d="M0,1000 L40,1000 L40,1040 L80,1040 L80,1080 L120,1080 L120,1120 L0,1120 Z" fill="' + b + '" fill-opacity="0.14"/>' +
        '<path d="M800,1000 L760,1000 L760,1040 L720,1040 L720,1080 L680,1080 L680,1120 L800,1120 Z" fill="' + p + '" fill-opacity="0.14"/>';
    }
    if (key === 'chrysler_crown') {
      return '<path d="M220,0 A180,95 0 0,0 580,0" fill="none" stroke="' + p + '" stroke-width="3" stroke-opacity="0.26"/>' +
        '<path d="M270,0 A130,70 0 0,0 530,0" fill="none" stroke="' + b + '" stroke-width="2.5" stroke-opacity="0.34"/>' +
        '<path d="M320,0 A80,44 0 0,0 480,0" fill="none" stroke="' + p + '" stroke-width="2" stroke-opacity="0.26"/>' +
        '<line x1="0" y1="1102" x2="800" y2="1102" stroke="' + p + '" stroke-width="2.5" stroke-opacity="0.24"/>';
    }
    if (key === 'diamond_crest') {
      for (i = 0; i < 16; i++) {
        x = 25 + i * 50;
        body += '<polygon points="' + x + ',10 ' + (x + 18) + ',28 ' + x + ',46 ' + (x - 18) + ',28" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.5" stroke-opacity="0.30"/>';
      }
      return body + '<line x1="0" y1="54" x2="800" y2="54" stroke="' + p + '" stroke-width="1.5" stroke-opacity="0.24"/>';
    }
    if (key === 'cathedral_arch') {
      return '<path d="M28,1096 L28,180 Q28,24 400,24 Q772,24 772,180 L772,1096 Z" fill="none" stroke="' + p + '" stroke-width="2.5" stroke-opacity="0.26"/>' +
        '<path d="M38,1086 L38,184 Q38,36 400,36 Q762,36 762,184 L762,1086 Z" fill="none" stroke="' + b + '" stroke-width="1.3" stroke-opacity="0.36"/>';
    }
    if (key === 'venetian_lattice') {
      return '<defs><pattern id="pt-' + uid + '" width="36" height="36" patternUnits="userSpaceOnUse">' +
        '<circle cx="18" cy="18" r="14" fill="none" stroke="' + p + '" stroke-width="1" stroke-opacity="0.16"/>' +
        '<circle cx="0" cy="0" r="14" fill="none" stroke="' + b + '" stroke-width="1" stroke-opacity="0.18"/>' +
        '</pattern></defs><rect x="0" y="0" width="800" height="86" fill="url(#pt-' + uid + ')"/><rect x="0" y="1050" width="800" height="70" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'heraldic_diamond') {
      return '<polygon points="0,0 800,0 800,20 0,20" fill="' + p + '" fill-opacity="0.20"/>' +
        '<polygon points="400,8 424,26 400,44 376,26" fill="' + b + '" fill-opacity="0.40"/>' +
        '<line x1="0" y1="26" x2="368" y2="26" stroke="' + b + '" stroke-width="1.8" stroke-opacity="0.35"/>' +
        '<line x1="432" y1="26" x2="800" y2="26" stroke="' + b + '" stroke-width="1.8" stroke-opacity="0.35"/>';
    }
    if (key === 'regency_laurel') {
      return '<path d="M18,220 C18,80 90,18 230,18 M782,220 C782,80 710,18 570,18" fill="none" stroke="' + p + '" stroke-width="3" stroke-opacity="0.28"/>' +
        '<path d="M28,210 C28,90 96,28 220,28 M772,210 C772,90 704,28 580,28" fill="none" stroke="' + b + '" stroke-width="1.5" stroke-opacity="0.40"/>' +
        '<path d="M18,900 C18,1040 90,1102 230,1102 M782,900 C782,1040 710,1102 570,1102" fill="none" stroke="' + p + '" stroke-width="2.5" stroke-opacity="0.24"/>';
    }

    /* ---- 7. Modern Tech, Fintech & Data Grids ---- */
    if (key === 'dot_matrix') {
      return '<defs><pattern id="pt-' + uid + '" width="18" height="18" patternUnits="userSpaceOnUse">' +
        '<circle cx="4" cy="4" r="1.4" fill="' + p + '" fill-opacity="0.20"/>' +
        '<circle cx="13" cy="13" r="1.1" fill="' + b + '" fill-opacity="0.22"/>' +
        '</pattern></defs><rect width="800" height="1120" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'hex_mesh') {
      return '<defs><pattern id="pt-' + uid + '" width="44" height="38" patternUnits="userSpaceOnUse">' +
        '<polygon points="22,1 43,10 43,28 22,37 1,28 1,10" fill="none" stroke="' + p + '" stroke-width="0.9" stroke-opacity="0.16"/>' +
        '<circle cx="22" cy="19" r="1.4" fill="' + b + '" fill-opacity="0.22"/>' +
        '</pattern></defs><rect width="800" height="1120" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'subtle_grid') {
      return '<defs><pattern id="pt-' + uid + '" width="24" height="24" patternUnits="userSpaceOnUse">' +
        '<path d="M24,0 L0,0 0,24" fill="none" stroke="' + p + '" stroke-width="0.7" stroke-opacity="0.14"/>' +
        '</pattern></defs><rect width="800" height="1120" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'circuit_corner') {
      return '<path d="M0,44 L86,44 L112,70 L185,70 M0,72 L58,72 L84,98 L140,98 M140,0 L140,40 L166,66" fill="none" stroke="' + p + '" stroke-width="2" stroke-opacity="0.28"/>' +
        '<circle cx="185" cy="70" r="4" fill="' + b + '" fill-opacity="0.45"/><circle cx="140" cy="98" r="4" fill="' + b + '" fill-opacity="0.45"/>' +
        '<path d="M800,1076 L714,1076 L688,1050 L615,1050 M800,1048 L742,1048 L716,1022 L660,1022" fill="none" stroke="' + p + '" stroke-width="2" stroke-opacity="0.24"/>' +
        '<circle cx="615" cy="1050" r="4" fill="' + b + '" fill-opacity="0.42"/>';
    }
    if (key === 'iso_cubes') {
      return '<defs><pattern id="pt-' + uid + '" width="48" height="42" patternUnits="userSpaceOnUse">' +
        '<path d="M24,0 L48,14 L24,28 L0,14 Z" fill="' + p + '" fill-opacity="0.06" stroke="' + p + '" stroke-width="0.7" stroke-opacity="0.16"/>' +
        '<path d="M24,28 L48,14 L48,42 L24,42 Z" fill="' + b + '" fill-opacity="0.05"/>' +
        '</pattern></defs><rect x="0" y="0" width="800" height="130" fill="url(#pt-' + uid + ')"/><rect x="0" y="1010" width="800" height="110" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'orbital_rings') {
      return '<circle cx="720" cy="70" r="95" fill="none" stroke="' + p + '" stroke-width="1.5" stroke-opacity="0.20"/>' +
        '<circle cx="720" cy="70" r="62" fill="none" stroke="' + b + '" stroke-width="1.3" stroke-dasharray="6,5" stroke-opacity="0.32"/>' +
        '<circle cx="658" cy="70" r="4.5" fill="' + b + '" fill-opacity="0.48"/>' +
        '<circle cx="80" cy="1050" r="88" fill="none" stroke="' + p + '" stroke-width="1.5" stroke-opacity="0.18"/>';
    }
    if (key === 'matrix_cascade') {
      for (i = 0; i < 18; i++) {
        var h = 24 + ((i * 37) % 85);
        body += '<rect x="' + (14 + i * 44) + '" y="0" width="6" height="' + h + '" fill="' + (i % 3 === 0 ? b : p) + '" fill-opacity="0.16"/>';
      }
      return body;
    }
    if (key === 'crosshair_grid') {
      return '<defs><pattern id="pt-' + uid + '" width="40" height="40" patternUnits="userSpaceOnUse">' +
        '<path d="M17,20 L23,20 M20,17 L20,23" stroke="' + p + '" stroke-width="1" stroke-opacity="0.22"/>' +
        '<circle cx="0" cy="0" r="1.2" fill="' + b + '" fill-opacity="0.24"/>' +
        '</pattern></defs><rect width="800" height="1120" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'radar_sweep') {
      return _concentric(800, 0, 50, 32, 7, p, b, 1.3, 0.22) +
        '<line x1="800" y1="0" x2="610" y2="190" stroke="' + b + '" stroke-width="2" stroke-opacity="0.34"/>' +
        _concentric(0, 1120, 45, 30, 6, p, b, 1.2, 0.18);
    }
    if (key === 'fiber_streams') {
      for (i = 0; i < 8; i++) {
        body += '<path d="M0,' + (12 + i * 10) + ' C220,' + (12 + i * 10) + ' 320,' + (58 + i * 6) + ' 800,' + (58 + i * 6) +
          '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.5" stroke-opacity="0.22"/>';
      }
      return body;
    }
    if (key === 'constellation') {
      var pts = [[40,35],[125,68],[210,28],[310,74],[460,32],[590,70],[710,26],[765,88]];
      var poly = pts.map(function (q) { return q[0] + ',' + q[1]; }).join(' ');
      body = '<polyline points="' + poly + '" fill="none" stroke="' + p + '" stroke-width="1.2" stroke-opacity="0.24"/>';
      pts.forEach(function (q, idx) {
        body += '<circle cx="' + q[0] + '" cy="' + q[1] + '" r="' + (idx % 2 === 0 ? 3.5 : 2.5) + '" fill="' + (idx % 2 === 0 ? b : p) + '" fill-opacity="0.40"/>';
      });
      return body;
    }
    if (key === 'pixel_fade') {
      for (i = 0; i < 25; i++) {
        for (var r = 0; r < 4; r++) {
          if ((i + r * 3) % 2 === 0) {
            body += '<rect x="' + (i * 32) + '" y="' + (r * 18) + '" width="16" height="16" fill="' + (r % 2 === 0 ? p : b) + '" fill-opacity="' + (0.20 - r * 0.04).toFixed(2) + '"/>';
          }
        }
      }
      return body;
    }

    /* ---- 8. Editorial, Stripes & Textured Papers ---- */
    if (key === 'diagonal_lines') {
      return '<defs><pattern id="pt-' + uid + '" width="22" height="22" patternUnits="userSpaceOnUse">' +
        '<path d="M0,22 L22,0" stroke="' + p + '" stroke-width="1" stroke-opacity="0.14"/>' +
        '<path d="M11,22 L22,11" stroke="' + b + '" stroke-width="0.9" stroke-opacity="0.16"/>' +
        '</pattern></defs><rect width="800" height="1120" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'ledger_stripes') {
      return '<defs><pattern id="pt-' + uid + '" width="800" height="28" patternUnits="userSpaceOnUse">' +
        '<rect x="0" y="0" width="800" height="14" fill="' + p + '" fill-opacity="0.045"/>' +
        '<line x1="0" y1="27.5" x2="800" y2="27.5" stroke="' + b + '" stroke-width="0.5" stroke-opacity="0.14"/>' +
        '</pattern></defs><rect width="800" height="1120" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'pinstripe_margin') {
      for (i = 0; i < 5; i++) {
        body += '<line x1="' + (12 + i * 6) + '" y1="0" x2="' + (12 + i * 6) + '" y2="1120" stroke="' + (i === 4 ? b : p) + '" stroke-width="' + (i === 0 ? 2 : 1) + '" stroke-opacity="0.24"/>';
      }
      return body;
    }
    if (key === 'herringbone') {
      return '<defs><pattern id="pt-' + uid + '" width="28" height="28" patternUnits="userSpaceOnUse">' +
        '<path d="M0,14 L14,0 L28,14 M0,28 L14,14 L28,28" fill="none" stroke="' + p + '" stroke-width="0.9" stroke-opacity="0.15"/>' +
        '</pattern></defs><rect x="0" y="0" width="800" height="100" fill="url(#pt-' + uid + ')"/><rect x="0" y="1036" width="800" height="84" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'linen_crosshatch') {
      return '<defs><pattern id="pt-' + uid + '" width="16" height="16" patternUnits="userSpaceOnUse">' +
        '<path d="M0,8 L16,8 M8,0 L8,16" stroke="' + p + '" stroke-width="0.6" stroke-opacity="0.11"/>' +
        '</pattern></defs><rect width="800" height="1120" fill="url(#pt-' + uid + ')"/>';
    }
    if (key === 'woven_plaid') {
      return '<rect x="0" y="0" width="800" height="18" fill="' + p + '" fill-opacity="0.14"/>' +
        '<rect x="0" y="24" width="800" height="5" fill="' + b + '" fill-opacity="0.22"/>' +
        '<rect x="0" y="0" width="18" height="1120" fill="' + p + '" fill-opacity="0.14"/>' +
        '<rect x="24" y="0" width="5" height="1120" fill="' + b + '" fill-opacity="0.22"/>';
    }
    if (key === 'fine_ruled') {
      return '<defs><pattern id="pt-' + uid + '" width="800" height="24" patternUnits="userSpaceOnUse">' +
        '<line x1="56" y1="23.5" x2="744" y2="23.5" stroke="' + p + '" stroke-width="0.6" stroke-opacity="0.12"/>' +
        '</pattern></defs><rect x="0" y="160" width="800" height="860" fill="url(#pt-' + uid + ')"/>' +
        '<line x1="68" y1="160" x2="68" y2="1020" stroke="' + b + '" stroke-width="1.2" stroke-opacity="0.24"/>';
    }
    if (key === 'tapered_speed') {
      for (i = 0; i < 6; i++) {
        body += '<polygon points="0,' + (10 + i * 10) + ' ' + (680 - i * 80) + ',' + (10 + i * 10) + ' ' + (650 - i * 80) + ',' + (15 + i * 10) + ' 0,' + (15 + i * 10) +
          '" fill="' + (i % 2 === 0 ? p : b) + '" fill-opacity="0.20"/>';
      }
      return body;
    }
    if (key === 'parallel_horizon') {
      return '<rect x="0" y="14" width="800" height="6" fill="' + p + '" fill-opacity="0.24"/>' +
        '<rect x="0" y="24" width="800" height="2.5" fill="' + b + '" fill-opacity="0.34"/>' +
        '<rect x="0" y="1092" width="800" height="2.5" fill="' + b + '" fill-opacity="0.34"/>' +
        '<rect x="0" y="1099" width="800" height="6" fill="' + p + '" fill-opacity="0.24"/>';
    }
    if (key === 'acoustic_bars') {
      for (i = 0; i < 32; i++) {
        var bh = 12 + Math.round(Math.abs(Math.sin(i * 0.45)) * 42);
        body += '<rect x="' + (12 + i * 24.5) + '" y="0" width="8" height="' + bh + '" fill="' + (i % 3 === 0 ? b : p) + '" fill-opacity="0.18"/>';
      }
      return body;
    }

    /* ---- 9. Botanical, Organic & Celestial ---- */
    if (key === 'water_ribbon') {
      return '<path d="M0,18 Q200,82 400,26 T800,32 L800,0 L0,0 Z" fill="' + p + '" fill-opacity="0.13"/>' +
        '<path d="M0,38 Q200,102 400,46 T800,52" fill="none" stroke="' + b + '" stroke-width="3" stroke-opacity="0.28"/>' +
        '<path d="M0,1120 L0,1072 Q260,1020 520,1080 T800,1055 L800,1120 Z" fill="' + p + '" fill-opacity="0.11"/>';
    }
    if (key === 'horizon_sunrise') {
      return '<circle cx="400" cy="0" r="150" fill="' + b + '" fill-opacity="0.10"/>' +
        '<circle cx="400" cy="0" r="220" fill="none" stroke="' + p + '" stroke-width="2" stroke-opacity="0.18"/>' +
        '<circle cx="400" cy="0" r="265" fill="none" stroke="' + b + '" stroke-width="1.2" stroke-opacity="0.24"/>';
    }
    if (key === 'aurora_bands') {
      return '<path d="M0,0 L800,0 L800,88 C610,140 380,45 190,115 C95,148 35,115 0,98 Z" fill="' + p + '" fill-opacity="0.11"/>' +
        '<path d="M0,0 L800,0 L800,58 C580,105 320,18 0,74 Z" fill="' + b + '" fill-opacity="0.11"/>';
    }
    if (key === 'pebble_mosaic') {
      var pebs = [[38,34,24],[86,26,16],[28,82,18],[76,72,14],[124,42,12],[762,1084,26],[712,1090,16],[770,1034,18]];
      pebs.forEach(function (q, idx) {
        body += '<circle cx="' + q[0] + '" cy="' + q[1] + '" r="' + q[2] + '" fill="' + (idx % 2 === 0 ? p : b) + '" fill-opacity="0.16"/>';
      });
      return body;
    }
    if (key === 'bamboo_accent') {
      return '<line x1="28" y1="0" x2="28" y2="1120" stroke="' + p + '" stroke-width="5" stroke-opacity="0.20"/>' +
        '<line x1="40" y1="0" x2="40" y2="1120" stroke="' + b + '" stroke-width="3" stroke-opacity="0.26"/>' +
        '<line x1="20" y1="180" x2="48" y2="180" stroke="' + b + '" stroke-width="2.5" stroke-opacity="0.38"/>' +
        '<line x1="20" y1="540" x2="48" y2="540" stroke="' + b + '" stroke-width="2.5" stroke-opacity="0.38"/>' +
        '<line x1="20" y1="900" x2="48" y2="900" stroke="' + b + '" stroke-width="2.5" stroke-opacity="0.38"/>';
    }
    if (key === 'leaf_vein_arc') {
      return '<path d="M0,220 Q120,110 260,0" fill="none" stroke="' + p + '" stroke-width="2.5" stroke-opacity="0.28"/>' +
        '<path d="M0,175 Q95,90 205,0 M0,130 Q70,68 150,0 M0,85 Q45,44 95,0" fill="none" stroke="' + b + '" stroke-width="1.5" stroke-opacity="0.30"/>' +
        '<path d="M800,900 Q680,1010 540,1120" fill="none" stroke="' + p + '" stroke-width="2.5" stroke-opacity="0.24"/>';
    }
    if (key === 'coastal_contour') {
      for (i = 0; i < 6; i++) {
        body += '<path d="M0,' + (34 + i * 16) + ' Q180,' + (10 + i * 12) + ' 360,' + (44 + i * 14) + ' T800,' + (24 + i * 14) +
          '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.3" stroke-opacity="0.22"/>';
      }
      return body;
    }
    if (key === 'topo_ridge') {
      for (i = 0; i < 5; i++) {
        body += '<path d="M0,' + (92 - i * 14) + ' C160,' + (32 - i * 6) + ' 320,' + (116 - i * 12) + ' 520,' + (48 - i * 8) + ' C640,' + (22 - i * 4) + ' 730,' + (78 - i * 10) + ' 800,' + (58 - i * 8) +
          '" fill="none" stroke="' + (i % 2 === 0 ? p : b) + '" stroke-width="1.5" stroke-opacity="0.24"/>';
      }
      return body;
    }
    if (key === 'eclipse_halo') {
      return '<circle cx="720" cy="68" r="76" fill="' + p + '" fill-opacity="0.11"/>' +
        '<circle cx="734" cy="60" r="68" fill="#ffffff" fill-opacity="0.88"/>' +
        '<circle cx="720" cy="68" r="84" fill="none" stroke="' + b + '" stroke-width="2" stroke-opacity="0.30"/>';
    }
    if (key === 'solar_meridian') {
      return '<circle cx="400" cy="560" r="240" fill="none" stroke="' + p + '" stroke-width="1.2" stroke-opacity="0.10"/>' +
        '<circle cx="400" cy="560" r="280" fill="none" stroke="' + b + '" stroke-width="1" stroke-dasharray="6,8" stroke-opacity="0.16"/>' +
        '<line x1="400" y1="0" x2="400" y2="90" stroke="' + b + '" stroke-width="2" stroke-opacity="0.30"/>' +
        '<line x1="400" y1="1030" x2="400" y2="1120" stroke="' + b + '" stroke-width="2" stroke-opacity="0.30"/>';
    }

    /* ---- 10. Chevrons, Ribbons & Heraldic Accents ---- */
    if (key === 'chevron_ribbon') {
      return '<polygon points="0,0 800,0 800,68 400,120 0,68" fill="' + p + '" fill-opacity="0.13"/>' +
        '<polyline points="0,72 400,124 800,72" fill="none" stroke="' + b + '" stroke-width="4" stroke-opacity="0.30"/>';
    }
    if (key === 'double_chevron') {
      return '<polygon points="0,0 800,0 800,48 400,98 0,48" fill="' + p + '" fill-opacity="0.13"/>' +
        '<polyline points="0,56 400,106 800,56" fill="none" stroke="' + b + '" stroke-width="3.5" stroke-opacity="0.32"/>' +
        '<polyline points="0,68 400,118 800,68" fill="none" stroke="' + p + '" stroke-width="2" stroke-opacity="0.24"/>';
    }
    if (key === 'arrowhead_banner') {
      return '<polygon points="0,0 740,0 800,36 740,72 0,72" fill="' + p + '" fill-opacity="0.12"/>' +
        '<polyline points="0,76 740,76 800,40" fill="none" stroke="' + b + '" stroke-width="3" stroke-opacity="0.32"/>';
    }
    if (key === 'shield_tip') {
      return '<path d="M0,0 L800,0 L800,52 Q400,132 0,52 Z" fill="' + p + '" fill-opacity="0.12"/>' +
        '<polygon points="384,82 416,82 400,104" fill="' + b + '" fill-opacity="0.38"/>';
    }
    if (key === 'pennant_corner') {
      return '<polygon points="0,0 260,0 210,36 260,72 0,72" fill="' + p + '" fill-opacity="0.16"/>' +
        '<polygon points="0,72 180,72 150,90 0,90" fill="' + b + '" fill-opacity="0.24"/>';
    }
    if (key === 'folded_banner') {
      return '<rect x="0" y="0" width="800" height="44" fill="' + p + '" fill-opacity="0.15"/>' +
        '<polygon points="0,44 64,44 0,84" fill="' + b + '" fill-opacity="0.28"/>' +
        '<polygon points="800,44 736,44 800,84" fill="' + b + '" fill-opacity="0.28"/>';
    }
    if (key === 'heraldic_sash') {
      return '<polygon points="620,0 710,0 800,90 800,180" fill="' + p + '" fill-opacity="0.16"/>' +
        '<polygon points="710,0 745,0 800,55 800,90" fill="' + b + '" fill-opacity="0.26"/>' +
        '<polygon points="0,940 0,1030 90,1120 180,1120" fill="' + p + '" fill-opacity="0.14"/>';
    }
    if (key === 'vcut_executive') {
      return '<polygon points="0,0 800,0 800,84 400,34 0,84" fill="' + p + '" fill-opacity="0.14"/>' +
        '<polyline points="0,88 400,38 800,88" fill="none" stroke="' + b + '" stroke-width="3.5" stroke-opacity="0.30"/>';
    }
    if (key === 'triple_ribbon') {
      return '<rect x="0" y="0" width="800" height="10" fill="' + p + '" fill-opacity="0.24"/>' +
        '<rect x="0" y="13" width="800" height="5" fill="' + b + '" fill-opacity="0.32"/>' +
        '<rect x="0" y="21" width="800" height="2" fill="' + p + '" fill-opacity="0.20"/>' +
        '<rect x="0" y="1097" width="800" height="2" fill="' + p + '" fill-opacity="0.20"/>' +
        '<rect x="0" y="1102" width="800" height="5" fill="' + b + '" fill-opacity="0.32"/>' +
        '<rect x="0" y="1110" width="800" height="10" fill="' + p + '" fill-opacity="0.24"/>';
    }
    if (key === 'royal_sash_diag') {
      return '<polygon points="0,120 120,0 210,0 0,210" fill="' + p + '" fill-opacity="0.14"/>' +
        '<polygon points="210,0 240,0 0,240 0,210" fill="' + b + '" fill-opacity="0.24"/>' +
        '<polygon points="800,1000 680,1120 590,1120 800,910" fill="' + p + '" fill-opacity="0.14"/>' +
        '<polygon points="590,1120 560,1120 800,880 800,910" fill="' + b + '" fill-opacity="0.24"/>';
    }

    return '';
  }

  function buildTsLhPatternSvg(pattern, accent, brand2, opPct) {
    if (!pattern || pattern === 'none') return '';
    _uid += 1;
    var op = (Math.max(5, Math.min(100, parseInt(opPct != null ? opPct : 85, 10) || 85)) / 100).toFixed(2);
    var p = accent || '#002769';
    var b = brand2 || '#02982E';
    var body = buildPatternBody(pattern, p, b, 'lhp' + _uid);
    if (!body) return '';
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 1120" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;opacity:' + op + ';pointer-events:none;">' + body + '</svg>';
  }

  var LABEL_MAP = {};
  PATTERNS.forEach(function (item) { LABEL_MAP[item.value] = item.label; });

  global.TS_LH_PATTERNS = PATTERNS;
  global.TS_LH_PATTERN_LABELS = LABEL_MAP;
  global.buildTsLhPatternSvg = buildTsLhPatternSvg;
})(window);
