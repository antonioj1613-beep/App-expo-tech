/**
 * Vocabulary review — SM-2 flashcard flow. Grading posts to the submit API,
 * then reloads so the server picks the next due word (the due queue can
 * change shape after every review, so always trust the server for "what's
 * next" rather than tracking a client-side queue).
 */
(function () {
  const config = document.getElementById("vocab-config");
  if (!config) return;

  const lessonId = config.dataset.lessonId;
  const submitUrl = config.dataset.submitUrl;
  const csrfToken = config.dataset.csrfToken || "";

  const gotItBtn = document.getElementById("vocabGotItBtn");
  const stillLearningBtn = document.getElementById("vocabStillLearningBtn");
  const feedbackEl = document.getElementById("vocabFeedback");

  let submitted = false;

  function apiPost(url, body) {
    const formData = new FormData();
    Object.keys(body).forEach(function (key) {
      if (body[key] !== undefined && body[key] !== null) formData.append(key, body[key]);
    });
    return fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      body: formData,
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) throw new Error(data.error || "Request failed");
        return data;
      });
    });
  }

  function showFeedback(message, isSuccess) {
    feedbackEl.classList.remove("hidden", "border-success/30", "bg-success/10", "text-success", "border-destructive/30", "bg-destructive/10", "text-destructive");
    feedbackEl.classList.add(
      isSuccess ? "border-success/30" : "border-destructive/30",
      isSuccess ? "bg-success/10" : "bg-destructive/10",
      isSuccess ? "text-success" : "text-destructive"
    );
    feedbackEl.textContent = message;
  }

  function grade(correct) {
    if (submitted) return;
    submitted = true;
    gotItBtn.disabled = true;
    stillLearningBtn.disabled = true;

    apiPost(submitUrl, { lesson_id: lessonId, correct: correct ? "1" : "0" })
      .then(function (data) {
        const days = data.interval_days;
        const unit = days === 1 ? "day" : "days";
        showFeedback(
          (correct ? "Nice! " : "No worries — ") + "next review in " + days + " " + unit + (data.xp_earned ? " · +" + data.xp_earned + " XP" : ""),
          correct
        );
        if (window.applyLearnerStats) {
          window.applyLearnerStats(data);
        }
        window.setTimeout(function () {
          window.location.reload();
        }, 900);
      })
      .catch(function (err) {
        submitted = false;
        gotItBtn.disabled = false;
        stillLearningBtn.disabled = false;
        showFeedback(err.message, false);
      });
  }

  if (gotItBtn) gotItBtn.addEventListener("click", function () { grade(true); });
  if (stillLearningBtn) stillLearningBtn.addEventListener("click", function () { grade(false); });
})();
