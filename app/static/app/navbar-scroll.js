/**
 * Landing header: toggles `.is-scrolled` on [data-scroll-header] once the
 * page scrolls past a small threshold. The opacity/blur/border transition
 * itself lives in theme.css — this only flips one class.
 *
 * rAF-throttled scroll listener, not a continuous animation loop: the
 * handler runs at most once per animation frame and does nothing between
 * scroll events.
 */
(function () {
  var header = document.querySelector("[data-scroll-header]");
  if (!header) return;

  var SCROLL_THRESHOLD = 24;
  var ticking = false;

  function update() {
    header.classList.toggle("is-scrolled", window.scrollY > SCROLL_THRESHOLD);
    ticking = false;
  }

  window.addEventListener(
    "scroll",
    function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(update);
    },
    { passive: true }
  );

  update();
})();
