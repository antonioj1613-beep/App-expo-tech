/**
 * Apply learner stats to shared chrome after a practice session (no full reload).
 */
(function () {
  function formatNumber(value) {
    return Number(value || 0).toLocaleString();
  }

  function removeToast() {
    const existing = document.getElementById("learnerStatsToast");
    if (existing) existing.remove();
  }

  function showSessionToast(payload) {
    const session = payload.session || {};
    if (!session.xp_earned) return;

    removeToast();
    const toast = document.createElement("div");
    toast.id = "learnerStatsToast";
    toast.className =
      "fixed bottom-6 right-6 z-50 max-w-sm glass rounded-2xl border border-border shadow-elegant p-4 animate-fade-in";
    toast.innerHTML =
      '<p class="text-sm font-semibold">Session saved</p>' +
      '<p class="text-xs text-muted-foreground mt-1">+' +
      formatNumber(session.xp_earned) +
      " XP · Total " +
      formatNumber((payload.profile && payload.profile.total_xp) || 0) +
      " XP</p>";
    document.body.appendChild(toast);
    window.setTimeout(removeToast, 4500);
  }

  window.applyLearnerStats = function applyLearnerStats(payload) {
    if (!payload) return;

    if (payload.ui_mode === "reload") {
      window.location.reload();
      return;
    }

    const profile = payload.profile || {};
    const app = payload.app_user || {};
    const skill = payload.skill_progress || payload.speaking_skill || {};

    const xpTotal = document.getElementById("sidebarXpTotal");
    if (xpTotal) {
      xpTotal.textContent = formatNumber(app.total_xp != null ? app.total_xp : profile.total_xp) + " XP earned";
    }

    const xpBar = document.getElementById("sidebarXpBar");
    if (xpBar) {
      xpBar.style.width = String(app.xp_progress_percent || 0) + "%";
    }

    const xpDetail = document.getElementById("sidebarXpDetail");
    if (xpDetail && app.xp_for_next_level) {
      xpDetail.textContent =
        formatNumber(app.xp_into_level || 0) + " / " + formatNumber(app.xp_for_next_level) + " XP to level " + (app.level + 1);
    }

    const streak = document.getElementById("sidebarStreakDays");
    if (streak) {
      const days = profile.streak_days != null ? profile.streak_days : app.streak_days;
      streak.textContent = String(days || 0) + " day streak";
    }

    const speakingMeta = document.getElementById("speakingSkillMeta");
    if (speakingMeta && skill.lessons_label) {
      speakingMeta.textContent =
        "Level " + skill.level + " · " + skill.lessons_label + " lessons · " + skill.progress_percent + "%";
    }

    const pageHeader = document.getElementById("pageSubtitle");
    if (pageHeader && skill.subtitle) {
      pageHeader.textContent = skill.subtitle;
    }

    showSessionToast(payload);
  };
})();
