/**
 * Fade-in-on-scroll via Intersection Observer (no scroll listeners).
 */
(function () {
  function init() {
    var elements = document.querySelectorAll(".fade-in");
    if (!elements.length) return;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      elements.forEach(function (el) {
        el.classList.add("is-visible");
      });
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;

          var el = entry.target;
          var delay = parseInt(el.getAttribute("data-delay") || "0", 10);

          window.setTimeout(function () {
            el.classList.add("is-visible");
          }, delay);

          observer.unobserve(el);
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -50px 0px" }
    );

    elements.forEach(function (el) {
      observer.observe(el);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
