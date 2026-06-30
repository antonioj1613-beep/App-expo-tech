(function () {
  function currentSkillSlug(form) {
    var hidden = form.querySelector('input[name="skill"]');
    if (hidden && hidden.type === "hidden") {
      var skillSelect = form.querySelector('select[name="skill"]');
      if (skillSelect && skillSelect.options.length) {
        return skillSelect.value ? skillSelect.options[skillSelect.selectedIndex].text.toLowerCase() : "";
      }
      return form.getAttribute("data-skill-slug") || "";
    }
    var select = form.querySelector('select[name="skill"]');
    if (!select) return form.getAttribute("data-skill-slug") || "";
    var option = select.options[select.selectedIndex];
    if (!option) return "";
    var text = option.textContent.trim().toLowerCase();
    if (text === "listening") return "listening";
    if (text === "reading") return "reading";
    if (text === "writing") return "writing";
    if (text === "vocabulary") return "vocabulary";
    return form.getAttribute("data-skill-slug") || "";
  }

  function updatePanels(form) {
    var slug = currentSkillSlug(form);
    form.querySelectorAll(".staff-skill-panel").forEach(function (panel) {
      var panels = (panel.getAttribute("data-panel") || "").split(/\s+/);
      var show = panels.indexOf(slug) !== -1;
      panel.classList.toggle("is-hidden", !show);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("lesson-form");
    if (!form) return;
    updatePanels(form);
    var skillSelect = form.querySelector('select[name="skill"]');
    if (skillSelect) {
      skillSelect.addEventListener("change", function () {
        updatePanels(form);
      });
    }
  });
})();
