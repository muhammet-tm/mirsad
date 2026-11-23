/* Mirsad deck: navigation, scaling, and motion (GSAP, vendored in vendor/).
   Keys: right, down, space, page down = next; left, up, page up = back; Home, End; F = full screen.
   URL: #5 opens slide 5; ?still shows final states without motion; ?print lays out every slide for PDF.
   Numbers are never computed here: each counts up to the exact text that the build wrote into the page. */
(function () {
  'use strict';
  var Q = new URLSearchParams(location.search);
  var PRINT = Q.has('print');
  var STILL = PRINT || Q.has('still') || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  if (STILL) document.documentElement.classList.add('still');
  var deck = document.getElementById('deck');
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var bar = document.querySelector('#hud i');
  var cur = -1, tl = null;

  /* ---- big numbers: "95.5%" becomes 95<small>.5%</small>; the text itself is untouched ---- */
  var NUM = /^([^\d]*)(\d[\d,]*)(\.\d+)?(.*)$/;
  function splitHtml(text) {
    var m = NUM.exec(text.trim());
    if (!m) return text;
    return m[1] + m[2] + '<small>' + (m[3] || '') + m[4] + '</small>';
  }
  function fmt(v, decimals, commas) {
    var s = v.toFixed(decimals);
    if (!commas) return s;
    var p = s.split('.');
    p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return p.join('.');
  }
  document.querySelectorAll('[data-count]').forEach(function (el) {
    el.dataset.final = el.textContent.trim();
    if (el.hasAttribute('data-split')) el.innerHTML = splitHtml(el.dataset.final);
  });

  function counter(el) {
    var m = NUM.exec(el.dataset.final);
    if (!m) return null;
    var whole = m[2], frac = m[3] || '';
    var target = parseFloat(whole.replace(/,/g, '') + frac);
    var decimals = frac ? frac.length - 1 : 0, commas = whole.indexOf(',') >= 0;
    var split = el.hasAttribute('data-split'), o = {v: 0};
    return gsap.to(o, {v: target, duration: 1.2, ease: 'power3.out', onUpdate: function () {
      var t = m[1] + fmt(o.v, decimals, commas) + m[4];
      if (split) el.innerHTML = splitHtml(t); else el.textContent = t;
    }, onComplete: function () {
      if (split) el.innerHTML = splitHtml(el.dataset.final); else el.textContent = el.dataset.final;
    }});
  }

  /* ---- isometric drawings: trace each outline, then fill the faces ---- */
  function drawIso(svg, at, t) {
    var shapes = svg.querySelectorAll('polygon, line, polyline, path, circle');
    var faces = [];
    shapes.forEach(function (s) {
      var len = 0;
      try { len = s.getTotalLength ? s.getTotalLength() : 0; } catch (e) { len = 0; }
      if (!len) return;
      var fill = s.getAttribute('fill');
      var dash = s.getAttribute('stroke-dasharray');
      if (fill && fill !== 'none') { faces.push(s); gsap.set(s, {fillOpacity: 0}); }
      if (!dash) { gsap.set(s, {strokeDasharray: len, strokeDashoffset: len}); s.dataset.trace = '1'; }
      else gsap.set(s, {opacity: 0});
    });
    var traced = Array.prototype.filter.call(shapes, function (s) { return s.dataset.trace; });
    t.to(traced, {strokeDashoffset: 0, duration: 1.1, ease: 'power2.inOut', stagger: {amount: 0.9}}, at);
    t.to(svg.querySelectorAll('[stroke-dasharray]'), {opacity: 1, duration: 0.5, stagger: 0.02}, at + 0.6);
    t.to(faces, {fillOpacity: 1, duration: 0.6, stagger: {amount: 0.5}}, at + 0.9);
    t.from(svg.querySelectorAll('text'), {opacity: 0, duration: 0.4, stagger: 0.08}, at + 1.2);
    t.fromTo(svg.querySelectorAll('.hot'), {y: -40}, {y: 0, duration: 0.6, ease: 'back.out(2)'}, at + 1.4);
  }

  function build(slide) {
    var t = gsap.timeline({defaults: {ease: 'power3.out'}});
    var at = 0;
    slide.querySelectorAll('[data-a]').forEach(function (el) {
      var a = el.dataset.a;
      if (a === 'wipe') { t.fromTo(el, {clipPath: 'inset(0 0 0 100%)'}, {clipPath: 'inset(0 0 0 0%)', duration: 0.8, ease: 'power4.inOut'}, 0); return; }
      if (a === 'signal') { t.from(el.querySelectorAll('path, rect'), {opacity: 0, scale: 0.6, transformOrigin: '0% 100%', duration: 0.5, stagger: 0.12}, 0.5); return; }
      if (a === 'grow') { t.fromTo(el, {scaleX: 0}, {scaleX: 1, duration: 1.0, ease: 'power3.inOut', transformOrigin: 'left center'}, at + 0.1); return; }
      if (a === 'fade') { t.from(el, {opacity: 0, duration: 0.6}, at); return; }
      t.from(el, {y: 28, opacity: 0, duration: 0.7}, at);
      at += 0.08;
    });
    slide.querySelectorAll('svg.iso').forEach(function (svg) { drawIso(svg, 0.25, t); });
    slide.querySelectorAll('[data-count]').forEach(function (el) {
      var c = counter(el);
      if (c) t.add(c, 0.35);
    });
    return t;
  }

  /* ---- layout ---- */
  function fit() {
    if (PRINT) return;
    var s = Math.min(innerWidth / 1920, innerHeight / 1080);
    deck.style.transform = 'translate(' + (innerWidth - 1920 * s) / 2 + 'px,' + (innerHeight - 1080 * s) / 2 + 'px) scale(' + s + ')';
  }

  function show(i) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    if (i === cur) return;
    if (tl) { tl.progress(1).kill(); tl = null; }
    if (cur >= 0) slides[cur].classList.remove('on');
    cur = i;
    var s = slides[cur];
    s.classList.add('on');
    if (!STILL && window.gsap) tl = build(s);
    if (bar) bar.style.width = ((cur + 1) / slides.length * 100) + '%';
    if (location.hash !== '#' + (cur + 1)) history.replaceState(null, '', '#' + (cur + 1));
    document.title = 'Mirsad, ' + (cur + 1) + ' of ' + slides.length + ': ' + (s.dataset.title || '');
  }

  if (PRINT) {
    document.documentElement.classList.add('print');
    slides.forEach(function (s) { s.classList.add('on'); });
    return;
  }

  document.addEventListener('keydown', function (e) {
    var k = e.key;
    if (k === 'ArrowRight' || k === 'ArrowDown' || k === 'PageDown' || k === ' ' || k === 'Enter') { e.preventDefault(); show(cur + 1); }
    else if (k === 'ArrowLeft' || k === 'ArrowUp' || k === 'PageUp' || k === 'Backspace') { e.preventDefault(); show(cur - 1); }
    else if (k === 'Home') show(0);
    else if (k === 'End') show(slides.length - 1);
    else if (k === 'f' || k === 'F') { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen(); }
  });
  document.addEventListener('click', function (e) { if (e.clientX > innerWidth / 3) show(cur + 1); else show(cur - 1); });
  addEventListener('resize', fit);
  addEventListener('hashchange', function () { show(parseInt(location.hash.slice(1), 10) - 1 || 0); });
  fit();
  var start = parseInt(location.hash.slice(1), 10) - 1 || 0;
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { show(start); });
  else show(start);
}());
