/**
 * Theme-aware Chart.js helpers — reads the app's --chart-1..5 / --border /
 * --muted-foreground / --popover design tokens (theme.css) instead of
 * hardcoding colors, so charts follow the light/dark toggle like every
 * other component. Charts that want to live-update on toggle register a
 * redraw callback in window.lisaCharts; toggleTheme()/setTheme() (head.html)
 * dispatch "lisa:theme-changed" after flipping the .dark class.
 */
(function () {
  var FONT = "Inter, system-ui, sans-serif";

  function channels(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function solid(name) {
    var c = channels(name);
    return c ? "rgb(" + c.replace(/\s+/g, ",") + ")" : "";
  }

  function alpha(name, a) {
    var c = channels(name).split(/\s+/).map(Number);
    if (c.length !== 3 || c.some(isNaN)) return "";
    return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + a + ")";
  }

  window.chartTheme = function chartTheme() {
    return {
      series: ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5"].map(solid),
      primary: solid("--primary"),
      primaryChannels: channels("--primary"),
      tick: solid("--muted-foreground"),
      grid: alpha("--border", 0.6),
      border: solid("--border"),
      tooltipBg: solid("--popover"),
      tooltipText: solid("--popover-foreground"),
    };
  };

  window.chartBaseOptions = function chartBaseOptions(theme) {
    return {
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          backgroundColor: theme.tooltipBg,
          titleColor: theme.tooltipText,
          bodyColor: theme.tooltipText,
          borderColor: theme.border,
          borderWidth: 1,
          cornerRadius: 10,
          padding: 10,
          displayColors: false,
          titleFont: { family: FONT, weight: "600", size: 12 },
          bodyFont: { family: FONT, size: 12 },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: theme.tick, font: { family: FONT, size: 11 } } },
        y: { grid: { color: theme.grid }, ticks: { color: theme.tick, font: { family: FONT, size: 11 } } },
      },
    };
  };

  window.chartFillGradient = function chartFillGradient(canvas, primaryChannels, height) {
    var parts = primaryChannels.split(/\s+/).map(Number);
    var rgb = parts.join(",");
    var g = canvas.getContext("2d").createLinearGradient(0, 0, 0, height);
    g.addColorStop(0, "rgba(" + rgb + ",0.5)");
    g.addColorStop(1, "rgba(" + rgb + ",0)");
    return g;
  };

  // Charts that want to re-theme live on toggle push a no-arg redraw fn here.
  window.lisaCharts = window.lisaCharts || [];
  window.addEventListener("lisa:theme-changed", function () {
    window.lisaCharts.forEach(function (redraw) {
      try { redraw(); } catch (e) { /* chart not on this page anymore */ }
    });
  });
})();
