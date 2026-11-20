(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.StampTypographyGeometry = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var DEG = Math.PI / 180;

  function number(value, fallback) {
    var n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function pointOnEllipse(rx, ry, angleDeg) {
    var a = angleDeg * DEG;
    return {x: rx * Math.cos(a), y: ry * Math.sin(a)};
  }

  function round(n) {
    var value = Math.abs(n) < 0.00001 ? 0 : n;
    return Number(value.toFixed(3));
  }

  /**
   * Build a centred top/bottom SVG ellipse arc.
   * Natural traversal is left-to-right and keeps glyphs upright:
   * top uses SVG sweep=1, bottom uses sweep=0.
   */
  function buildArc(options) {
    options = options || {};
    var rx = Math.max(1, number(options.rx, 100));
    var ry = Math.max(1, number(options.ry, rx));
    var side = options.side === 'bottom' ? 'bottom' : 'top';
    var sweep = clamp(Math.abs(number(options.sweep, 180)), 1, 359.9);
    var rotation = number(options.rotation, 0);
    var centre = (side === 'top' ? -90 : 90) + rotation;
    var startAngle;
    var endAngle;
    var sweepFlag;
    if (side === 'top') {
      startAngle = centre - sweep / 2;
      endAngle = centre + sweep / 2;
      sweepFlag = 1;
    } else {
      startAngle = centre + sweep / 2;
      endAngle = centre - sweep / 2;
      sweepFlag = 0;
    }
    if (options.direction === 'reverse') {
      var swap = startAngle;
      startAngle = endAngle;
      endAngle = swap;
      sweepFlag = sweepFlag ? 0 : 1;
    }
    var start = pointOnEllipse(rx, ry, startAngle);
    var end = pointOnEllipse(rx, ry, endAngle);
    var largeArc = sweep > 180 ? 1 : 0;
    return {
      rx: rx,
      ry: ry,
      sweep: sweep,
      rotation: rotation,
      side: side,
      direction: options.direction === 'reverse' ? 'reverse' : 'forward',
      startAngle: startAngle,
      endAngle: endAngle,
      start: start,
      end: end,
      largeArc: largeArc,
      sweepFlag: sweepFlag,
      d: 'M ' + round(start.x) + ' ' + round(start.y) +
        ' A ' + round(rx) + ' ' + round(ry) + ' 0 ' + largeArc + ' ' + sweepFlag +
        ' ' + round(end.x) + ' ' + round(end.y)
    };
  }

  // Simpson integration of ds = sqrt((rx sin t)^2 + (ry cos t)^2) dt.
  function ellipseArcLength(rx, ry, startAngle, sweepDeg) {
    rx = Math.max(1, number(rx, 100));
    ry = Math.max(1, number(ry, rx));
    var radians = Math.abs(number(sweepDeg, 180)) * DEG;
    var start = number(startAngle, 0) * DEG;
    var steps = Math.max(24, Math.ceil(radians / (Math.PI / 48)));
    if (steps % 2) steps += 1;
    var h = radians / steps;
    function speed(t) {
      var a = start + t;
      return Math.sqrt(rx * rx * Math.sin(a) * Math.sin(a) +
        ry * ry * Math.cos(a) * Math.cos(a));
    }
    var total = speed(0) + speed(radians);
    for (var i = 1; i < steps; i += 1) total += (i % 2 ? 4 : 2) * speed(i * h);
    return total * h / 3;
  }

  function estimateTextLength(text, options) {
    options = options || {};
    var value = String(text || '');
    var size = Math.max(1, number(options.size, 18));
    var tracking = number(options.tracking, 0);
    var wordSpacing = number(options.wordSpacing, 0);
    var widthPercent = clamp(number(options.widthPercent, 100), 40, 160) / 100;
    var glyphUnits = 0;
    for (var i = 0; i < value.length; i += 1) {
      var ch = value.charAt(i);
      if (/\s/.test(ch)) glyphUnits += 0.34;
      else if (/[MW@#%]/.test(ch)) glyphUnits += 0.82;
      else if (/[ilI1.,'|]/.test(ch)) glyphUnits += 0.30;
      else glyphUnits += 0.56;
    }
    var gaps = Math.max(0, value.length - 1);
    var words = Math.max(0, (value.match(/\s+/g) || []).length);
    return Math.max(0, (glyphUnits * size + gaps * tracking + words * wordSpacing) * widthPercent);
  }

  function fitText(text, arc, options) {
    options = options || {};
    var available = Math.max(1, ellipseArcLength(arc.rx, arc.ry, arc.startAngle, arc.sweep) -
      Math.max(0, number(options.endPadding, 8)) * 2);
    var natural = estimateTextLength(text, options);
    var mode = options.mode || 'shrink';
    var target = null;
    if (mode === 'fit') target = available;
    if (mode === 'shrink' && natural > available) target = available;
    return {
      available: available,
      natural: natural,
      target: target,
      overflow: natural > available,
      compression: natural > 0 && target !== null ? target / natural : 1
    };
  }

  function safePathRadius(options) {
    options = options || {};
    var outer = Math.max(10, number(options.outerRadius, 140));
    var stroke = Math.max(0, number(options.borderWidth, 3));
    var size = Math.max(1, number(options.fontSize, 18));
    var baseline = number(options.baselineOffset, 0);
    var clearance = Math.max(0, number(options.clearance, 4));
    // Text ascent / cap-height calculation
    var capHeight = size * 0.72;
    // Outward reach of glyphs from the optical centerline
    var outward = capHeight / 2 - baseline;
    return Math.max(10, outer - stroke / 2 - clearance - Math.max(0, outward));
  }

  /**
   * Compute concentric path radius for upper and lower circular inscriptions.
   * Ensures that top and bottom text share the identical optical centerline
   * and concentric curvature within the circular annular band.
   */
  function concentricRadius(options) {
    options = options || {};
    var bandRadius = Math.max(1, number(options.bandRadius, number(options.radius, 115)));
    var size = Math.max(1, number(options.fontSize, number(options.size, 18)));
    var side = options.side === 'bottom' ? 'bottom' : 'top';
    var baseline = number(options.baselineOffset, number(options.baseline, 0));
    var capHeight = size * 0.72;
    var halfCap = capHeight / 2;

    // Top text extends outward from baseline; bottom text extends inward from baseline.
    // Shift the baseline path so the visual optical center of both aligns at bandRadius.
    var radius = (side === 'bottom')
      ? bandRadius + halfCap - baseline
      : bandRadius - halfCap - baseline;

    return Math.max(1, radius);
  }

  /**
   * Build a concentric arc with automatic optical centerline alignment.
   */
  function buildConcentricArc(options) {
    options = options || {};
    var bandRadius = Math.max(1, number(options.bandRadius, number(options.radius, 115)));
    var size = Math.max(1, number(options.fontSize, number(options.size, 18)));
    var side = options.side === 'bottom' ? 'bottom' : 'top';
    var baseline = number(options.baselineOffset, number(options.baseline, 0));
    var r = concentricRadius({
      bandRadius: bandRadius,
      fontSize: size,
      side: side,
      baselineOffset: baseline
    });
    var xScale = Math.max(0.1, number(options.xScale, 1));
    var arcOpts = Object.assign({}, options, {
      rx: r * xScale,
      ry: r,
      side: side
    });
    var arc = buildArc(arcOpts);
    arc.bandRadius = bandRadius;
    arc.concentricRadius = r;
    return arc;
  }

  return {
    buildArc: buildArc,
    buildConcentricArc: buildConcentricArc,
    concentricRadius: concentricRadius,
    ellipseArcLength: ellipseArcLength,
    estimateTextLength: estimateTextLength,
    fitText: fitText,
    safePathRadius: safePathRadius,
    pointOnEllipse: pointOnEllipse
  };
}));
