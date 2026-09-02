/**
 * Mock exam taking flow — question navigation, per-question TTS (same
 * speechSynthesis approach as listening.js, no audio files), a countdown
 * timer that auto-submits at zero, and a single POST of every answered
 * question on submit (server does the actual grading, see exam_views.exam_submit).
 */
(function () {
  const config = document.getElementById("exam-config");
  if (!config) return;

  const attemptId = config.dataset.attemptId;
  const submitUrl = config.dataset.submitUrl;
  const csrfToken = config.dataset.csrfToken || "";
  let secondsLeft = parseInt(config.dataset.timeLimitSeconds, 10) || 0;

  const questions = Array.from(document.querySelectorAll(".exam-question"));
  const prevBtn = document.getElementById("examPrevBtn");
  const nextBtn = document.getElementById("examNextBtn");
  const submitBtn = document.getElementById("examSubmitBtn");
  const questionLabel = document.getElementById("examQuestionLabel");
  const timerEl = document.getElementById("examTimer");

  const answers = {}; // questionId -> selectedIndex
  let currentIndex = 0;
  let submitting = false;

  function formatTime(totalSeconds) {
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }

  function tickTimer() {
    if (secondsLeft <= 0) {
      timerEl.textContent = "00:00";
      submitExam();
      return;
    }
    timerEl.textContent = formatTime(secondsLeft);
    secondsLeft -= 1;
  }
  tickTimer();
  const timerInterval = setInterval(tickTimer, 1000);

  function showQuestion(index) {
    questions.forEach(function (q, i) {
      q.classList.toggle("hidden", i !== index);
    });
    currentIndex = index;
    questionLabel.textContent = "Question " + (index + 1) + " of " + questions.length;
    prevBtn.disabled = index === 0;
    const isLast = index === questions.length - 1;
    nextBtn.classList.toggle("hidden", isLast);
    submitBtn.classList.toggle("hidden", !isLast);
  }

  function selectOption(questionEl, optEl) {
    const questionId = questionEl.dataset.questionId;
    answers[questionId] = parseInt(optEl.dataset.i, 10);
    questionEl.querySelectorAll(".exam-opt").forEach(function (opt) {
      opt.classList.remove("border-primary", "bg-primary/10", "shadow-glow");
      opt.classList.add("border-border", "bg-secondary/40");
      opt.querySelector(".letter").classList.remove("bg-gradient-primary", "text-primary-foreground");
      opt.querySelector(".letter").classList.add("bg-background", "border", "border-border");
    });
    optEl.classList.add("border-primary", "bg-primary/10", "shadow-glow");
    optEl.classList.remove("border-border", "bg-secondary/40");
    optEl.querySelector(".letter").classList.add("bg-gradient-primary", "text-primary-foreground");
    optEl.querySelector(".letter").classList.remove("bg-background", "border", "border-border");
  }

  questions.forEach(function (q) {
    q.querySelectorAll(".exam-opt").forEach(function (opt) {
      opt.addEventListener("click", function () {
        selectOption(q, opt);
      });
    });

    const playBtn = q.querySelector(".exam-play-btn");
    const passageEl = q.querySelector(".exam-passage-text");
    if (playBtn && passageEl && "speechSynthesis" in window) {
      playBtn.addEventListener("click", function () {
        if (window.speechSynthesis.speaking) {
          window.speechSynthesis.cancel();
          return;
        }
        const utterance = new SpeechSynthesisUtterance(passageEl.textContent.trim());
        utterance.rate = 0.95;
        window.speechSynthesis.speak(utterance);
      });
    } else if (playBtn) {
      playBtn.disabled = true;
    }
  });

  prevBtn.addEventListener("click", function () {
    if (currentIndex > 0) showQuestion(currentIndex - 1);
  });
  nextBtn.addEventListener("click", function () {
    if (currentIndex < questions.length - 1) showQuestion(currentIndex + 1);
  });

  function submitExam() {
    if (submitting) return;
    submitting = true;
    clearInterval(timerInterval);
    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting…";

    const formData = new FormData();
    Object.keys(answers).forEach(function (questionId) {
      formData.append("answer_" + questionId, answers[questionId]);
    });

    fetch(submitUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      body: formData,
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) throw new Error(data.error || "Request failed");
          return data;
        });
      })
      .then(function (data) {
        window.location.href = data.results_url;
      })
      .catch(function (err) {
        submitting = false;
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit exam";
        alert(err.message);
      });
  }

  submitBtn.addEventListener("click", submitExam);

  showQuestion(0);
})();
