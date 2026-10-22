// codecartographer.dev motion. Everything here happens because the reader did
// something: pressed Next or Back on the sample map, used the arrow keys, or
// scrolled a section into view. Nothing plays on its own. Under
// prefers-reduced-motion the arrivals are skipped and the map still steps.
(function () {
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var root = document.documentElement;

  // ---------- the sample map: one session, stepped through by hand ----------
  document.querySelectorAll('.route').forEach(function (route) {
    var trail = route.querySelector('.trail');
    var legs = Array.prototype.slice.call(route.querySelectorAll('.legs > li'));
    var marks = route.querySelector('.marks');
    var count = route.querySelector('.count');
    var next = route.querySelector('.next');
    var back = route.querySelector('.back');
    var n = legs.length;
    if (!trail || !n || !trail.getTotalLength) return;
    var len = trail.getTotalLength();
    trail.style.strokeDasharray = len + ' ' + len;
    // One mark per leg, placed along the trail itself so the drawing and the
    // list can never disagree.
    var dots = [];
    if (marks) {
      legs.forEach(function (leg, i) {
        var pt = trail.getPointAtLength(len * (i + 1) / n);
        var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('class', 'wp');
        g.setAttribute('transform', 'translate(' + pt.x.toFixed(1) + ' ' + pt.y.toFixed(1) + ')');
        var c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        c.setAttribute('r', '7');
        var t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('y', '-14');
        t.setAttribute('text-anchor', 'middle');
        t.textContent = (i + 1 < 10 ? '0' : '') + (i + 1);
        g.appendChild(c); g.appendChild(t);
        marks.appendChild(g);
        dots.push(g);
      });
    }
    var step = 0;
    var render = function () {
      route.setAttribute('data-step', step);
      trail.style.strokeDashoffset = (len * (1 - step / n)).toFixed(1);
      legs.forEach(function (leg, i) {
        leg.classList.toggle('is-shown', i < step);
        leg.classList.toggle('is-now', i === step - 1);
      });
      dots.forEach(function (d, i) {
        d.classList.toggle('is-shown', i < step);
        d.classList.toggle('is-now', i === step - 1);
      });
      if (count) count.textContent = step === 0 ? 'Press Next to begin' : 'Moment ' + step + ' of ' + n;
      if (back) back.disabled = step === 0;
      if (next) next.textContent = step === 0 ? 'Next' : step === n ? 'Start again' : 'Next';
      route.classList.toggle('is-done', step === n);
    };
    var go = function (d) {
      if (d > 0 && step === n) step = 0; else step = Math.max(0, Math.min(n, step + d));
      render();
    };
    if (next) next.addEventListener('click', function () { go(1); });
    if (back) back.addEventListener('click', function () { go(-1); });
    route.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); go(1); }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); go(-1); }
    });
    render();
  });

  // ---------- the copy buttons on install lines (moved here from inline handlers) ----------
  document.querySelectorAll('.cmd button[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      var text = b.getAttribute('data-copy');
      var done = function () { b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () {});
    });
  });

  if (reduce || !('IntersectionObserver' in window)) return;
  root.classList.add('js');

  // ---------- arrival ----------
  var revealable = document.querySelectorAll('.reveal');
  if (revealable.length) {
    var rio = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add('is-in');
        rio.unobserve(e.target);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
    revealable.forEach(function (el) { rio.observe(el); });
    setTimeout(function () { revealable.forEach(function (el) { el.classList.add('is-in'); }); }, 4000);
  }
})();
