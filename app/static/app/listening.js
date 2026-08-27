/**
 * Listening lesson — submit answer, refresh progress chrome, and play the
 * transcript aloud via the browser's built-in TTS (no audio files, no
 * hosting — see the content-migration design doc for why: it's synthesizing
 * our own arbitrary scripts on the fly, so script writing isn't constrained
 * by what a fixed stock-audio library happens to have).
 */
(function () {
  const playBtn = document.getElementById("playBtn");
  const playIcon = document.getElementById("playIcon");
  const passageEl = document.getElementById("listeningPassageText");

  function setIcon(name) {
    if (!playIcon) return;
    playIcon.setAttribute("data-lucide", name);
    if (window.lucide) window.lucide.createIcons();
  }

  if (playBtn && passageEl && "speechSynthesis" in window) {
    playBtn.addEventListener("click", function () {
      if (window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
        setIcon("play");
        return;
      }
      const text = passageEl.textContent.trim();
      if (!text) return;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.95;
      utterance.onend = function () {
        setIcon("play");
      };
      utterance.onerror = function () {
        setIcon("play");
      };
      window.speechSynthesis.speak(utterance);
      setIcon("pause");
    });
  } else if (playBtn) {
    playBtn.disabled = true;
    playBtn.title = "Audio playback isn't supported in this browser.";
  }

  const config = document.getElementById("listening-config");
  if (!config) return;

  const lessonId = config.dataset.lessonId;
  const submitUrl = config.dataset.submitUrl;
  const csrfToken = config.dataset.csrfToken || "";
  const alreadyCompleted = config.dataset.alreadyCompleted === "1";

  const submitBtn = document.getElementById("listeningSubmitBtn");
  const nextBtn = document.getElementById("listeningNextBtn");
  const feedbackEl = document.getElementById("listeningFeedback");
  const options = document.querySelectorAll(".listening-opt");

  let selectedIndex = null;
  let submitted = alreadyCompleted;

  function selectOption(el) {
    if (submitted) return;
    selectedIndex = parseInt(el.dataset.i, 10);
    options.forEach(function (opt) {
      opt.classList.remove("border-primary", "bg-primary/10", "shadow-glow");
      opt.classList.add("border-border", "bg-secondary/40");
      opt.querySelector(".letter").classList.remove("bg-gradient-primary", "text-primary-foreground");
      opt.querySelector(".letter").classList.add("bg-background", "border", "border-border");
    });
    el.classList.add("border-primary", "bg-primary/10", "shadow-glow");
    el.classList.remove("border-border", "bg-secondary/40");
    el.querySelector(".letter").classList.add("bg-gradient-primary", "text-primary-foreground");
    el.querySelector(".letter").classList.remove("bg-background", "border", "border-border");
    submitBtn.disabled = false;
  }

  function showFeedback(correct, correctIndex, xpEarned, alreadyDone) {
    feedbackEl.classList.remove("hidden", "border-success/30", "bg-success/10", "text-success", "border-destructive/30", "bg-destructive/10", "text-destructive");
    if (correct) {
      feedbackEl.classList.add("border-success/30", "bg-success/10", "text-success");
      feedbackEl.textContent = alreadyDone
        ? "Correct — you already completed this lesson (no extra XP)."
        : "Correct! +" + xpEarned + " XP";
    } else {
      feedbackEl.classList.add("border-destructive/30", "bg-destructive/10", "text-destructive");
      const optionsList = document.querySelectorAll(".listening-opt");
      if (optionsList[correctIndex]) {
        optionsList[correctIndex].classList.add("border-success/50", "bg-success/10");
      }
      feedbackEl.textContent = alreadyDone
        ? "Not quite — listen again. (Already completed, no extra XP.)"
        : "Not quite. +" + xpEarned + " XP for completing the lesson.";
    }
  }

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

  options.forEach(function (el) {
    el.addEventListener("click", function () {
      selectOption(el);
    });
  });

  if (alreadyCompleted) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Already completed";
    nextBtn.classList.remove("hidden");
  }

  submitBtn.addEventListener("click", function () {
    if (selectedIndex === null || submitted) return;
    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting…";

    apiPost(submitUrl, {
      lesson_id: lessonId,
      selected_index: selectedIndex,
    })
      .then(function (data) {
        submitted = true;
        showFeedback(data.was_correct, data.correct_index, data.session.xp_earned, data.already_completed);
        submitBtn.textContent = data.was_correct ? "Correct" : "Submitted";
        if (window.applyLearnerStats) {
          window.applyLearnerStats(data);
        }
        if (data.has_next_lesson) {
          nextBtn.classList.remove("hidden");
        }
      })
      .catch(function (err) {
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit answer";
        feedbackEl.classList.remove("hidden");
        feedbackEl.className = "mt-4 text-sm rounded-xl p-3 border border-destructive/30 bg-destructive/10 text-destructive";
        feedbackEl.textContent = err.message;
      });
  });
})();
