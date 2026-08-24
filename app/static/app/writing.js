/**
 * Writing lesson — submit essay, record progress via record_practice_session on server.
 */
(function () {
  const config = document.getElementById("writing-config");
  if (!config) return;

  const lessonId = config.dataset.lessonId;
  const submitUrl = config.dataset.submitUrl;
  const csrfToken = config.dataset.csrfToken || "";
  const alreadyCompleted = config.dataset.alreadyCompleted === "1";

  const essayEl = document.getElementById("essay");
  const wcEl = document.getElementById("wc");
  const submitBtn = document.getElementById("writingSubmitBtn");
  const nextBtn = document.getElementById("writingNextBtn");
  const feedbackEl = document.getElementById("writingFeedback");
  const aiFeedbackText = document.getElementById("aiFeedbackText");

  let submitted = alreadyCompleted;

  function wordCount() {
    const v = essayEl.value.trim();
    return v ? v.split(/\s+/).length : 0;
  }

  function countWords() {
    const count = wordCount();
    wcEl.textContent = count;
    if (!submitted) {
      submitBtn.disabled = count === 0;
    }
  }
  window.countWords = countWords;

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

  function showFeedback(message, xpEarned, alreadyDone) {
    feedbackEl.classList.remove("hidden", "border-destructive/30", "bg-destructive/10", "text-destructive");
    feedbackEl.classList.add("border-success/30", "bg-success/10", "text-success");
    feedbackEl.textContent = alreadyDone ? message + " (already completed — no extra XP)" : message + " +" + xpEarned + " XP";
  }

  if (alreadyCompleted) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Already completed";
    if (nextBtn) nextBtn.classList.remove("hidden");
  }

  if (submitBtn) {
    submitBtn.addEventListener("click", function () {
      if (submitted) return;
      const essay = essayEl.value.trim();
      submitBtn.disabled = true;
      submitBtn.textContent = "Submitting…";

      apiPost(submitUrl, { lesson_id: lessonId, essay: essay })
        .then(function (data) {
          submitted = true;
          showFeedback(data.feedback, data.session.xp_earned, data.already_completed);
          if (aiFeedbackText) aiFeedbackText.textContent = data.feedback;
          submitBtn.textContent = "Submitted";
          if (window.applyLearnerStats) {
            window.applyLearnerStats(data);
          }
          if (data.has_next_lesson && nextBtn) {
            nextBtn.classList.remove("hidden");
          }
        })
        .catch(function (err) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Submit";
          feedbackEl.classList.remove("hidden");
          feedbackEl.className = "mt-4 text-sm rounded-xl p-3 border border-destructive/30 bg-destructive/10 text-destructive";
          feedbackEl.textContent = err.message;
        });
    });
  }

  if (essayEl) {
    essayEl.addEventListener("input", countWords);
    countWords();
  }
})();
