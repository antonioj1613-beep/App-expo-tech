/**
 * Writing lesson — live rule-based flagging while typing (no Ollama, pure
 * client-side regex — see writing feature design doc) plus submit-time AI
 * grading via the server.
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
  const checkNowBtn = document.getElementById("writingCheckNowBtn");
  const liveFlagsEl = document.getElementById("writingLiveFlags");
  const errorsBlock = document.getElementById("writingErrorsBlock");
  const errorsList = document.getElementById("writingErrorsList");
  const recommendationsBlock = document.getElementById("writingRecommendationsBlock");
  const recommendationsList = document.getElementById("writingRecommendationsList");
  const weakPointsBlock = document.getElementById("writingWeakPointsBlock");
  const weakPointsText = document.getElementById("writingWeakPointsText");

  let submitted = alreadyCompleted;

  // ---------------------------------------------------------------------
  // Live rule-based checks — a modest starter set, not comprehensive
  // grammar checking. Real depth is the submit-time AI pass's job. These
  // run entirely client-side: no network call, no Ollama, no contention
  // with Speaking's live conversational chat on the same local instance.
  // ---------------------------------------------------------------------

  function checkRepeatedWords(text) {
    const flags = [];
    const re = /\b([a-zA-Z]+)\s+\1\b/gi;
    let m;
    while ((m = re.exec(text)) !== null) {
      flags.push({
        type: "repeated_word",
        snippet: m[0],
        message: 'You wrote "' + m[1] + '" twice in a row.',
      });
    }
    return flags;
  }

  const SV_VERB_FIXES = {
    go: "goes", like: "likes", want: "wants", need: "needs", have: "has", do: "does",
    make: "makes", take: "takes", come: "comes", know: "knows", think: "thinks",
    say: "says", see: "sees", get: "gets", use: "uses", work: "works", play: "plays",
    study: "studies", live: "lives", walk: "walks", talk: "talks", watch: "watches",
    write: "writes", read: "reads", run: "runs", eat: "eats", drink: "drinks",
    sleep: "sleeps", love: "loves", hate: "hates", believe: "believes",
  };

  function checkSubjectVerbAgreement(text) {
    const flags = [];
    const verbs = Object.keys(SV_VERB_FIXES).join("|");
    const re = new RegExp("\\b(he|she|it)\\s+(" + verbs + ")\\b", "gi");
    let m;
    while ((m = re.exec(text)) !== null) {
      const pronoun = m[1];
      const verb = m[2].toLowerCase();
      const fix = SV_VERB_FIXES[verb];
      flags.push({
        type: "subject_verb_agreement",
        snippet: m[0],
        message: 'Try "' + pronoun + " " + fix + '" — "' + pronoun + '" needs the -s form of the verb.',
      });
    }
    return flags;
  }

  const UNCOUNTABLE_NOUNS = [
    "advice", "information", "furniture", "homework", "equipment", "news",
    "feedback", "luggage", "money", "traffic", "weather", "research",
    "evidence", "knowledge",
  ];

  function checkArticleUsage(text) {
    const flags = [];
    const nouns = UNCOUNTABLE_NOUNS.join("|");
    const re = new RegExp("\\b(a|an)\\s+(" + nouns + ")s?\\b", "gi");
    let m;
    while ((m = re.exec(text)) !== null) {
      const article = m[1];
      const noun = m[2].toLowerCase();
      flags.push({
        type: "articles",
        snippet: m[0],
        message: '"' + noun + '" is usually uncountable — try "' + noun + '" without "' + article.toLowerCase() + '", or "some ' + noun + '".',
      });
    }
    return flags;
  }

  function checkCapitalization(text) {
    const flags = [];
    const re = /(^|[.!?]\s+)([a-z])(\S*)/g;
    let m;
    while ((m = re.exec(text)) !== null) {
      const rest = m[2] + m[3];
      const snippet = rest.length > 20 ? rest.slice(0, 20) + "…" : rest;
      flags.push({
        type: "capitalization",
        snippet: snippet,
        message: "Start this sentence with a capital letter.",
      });
    }
    return flags;
  }

  function runLiveChecks(text) {
    if (!text || text.trim().length < 3) return [];
    return [].concat(
      checkRepeatedWords(text),
      checkSubjectVerbAgreement(text),
      checkArticleUsage(text),
      checkCapitalization(text)
    );
  }
  window.runLiveChecks = runLiveChecks; // exposed for direct verification, matches window.countWords precedent

  function renderLiveFlags(flags) {
    if (!liveFlagsEl) return;
    if (!flags.length) {
      liveFlagsEl.classList.add("hidden");
      liveFlagsEl.innerHTML = "";
      return;
    }
    liveFlagsEl.innerHTML = flags
      .map(function (f) {
        return (
          '<li class="rounded-lg border border-warning/30 bg-warning/10 p-2">' +
          '<strong>"' + escapeHtml(f.snippet) + '"</strong> — ' + escapeHtml(f.message) +
          "</li>"
        );
      })
      .join("");
    liveFlagsEl.classList.remove("hidden");
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  // ---------------------------------------------------------------------
  // Trigger strategy: debounce 1.5s after typing stops, OR immediately on
  // sentence-ending punctuation, OR a 6s max-wait fallback so a long
  // unfinished sentence still eventually gets checked. Provisional/tunable
  // timings, same status as the CEFR thresholds.
  // ---------------------------------------------------------------------
  const IDLE_DEBOUNCE_MS = 1500;
  const MAX_WAIT_MS = 6000;

  let idleTimer = null;
  let maxWaitTimer = null;
  let lastCheckedValue = "";

  function clearMaxWait() {
    if (maxWaitTimer) {
      clearTimeout(maxWaitTimer);
      maxWaitTimer = null;
    }
  }

  function scheduleMaxWait() {
    if (maxWaitTimer) return;
    maxWaitTimer = setTimeout(function () {
      maxWaitTimer = null;
      performLiveCheck();
    }, MAX_WAIT_MS);
  }

  function performLiveCheck() {
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
    clearMaxWait();
    const text = essayEl.value;
    if (text === lastCheckedValue) return;
    lastCheckedValue = text;
    renderLiveFlags(runLiveChecks(text));
  }
  window.performWritingLiveCheck = performLiveCheck; // exposed for direct verification

  function forceLiveCheck() {
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
    clearMaxWait();
    lastCheckedValue = essayEl.value;
    renderLiveFlags(runLiveChecks(essayEl.value));
  }

  function onEssayInput() {
    countWords();
    const text = essayEl.value;
    const lastChar = text.slice(-1);
    if (lastChar === "." || lastChar === "!" || lastChar === "?") {
      performLiveCheck();
      return;
    }
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(performLiveCheck, IDLE_DEBOUNCE_MS);
    scheduleMaxWait();
  }

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

  function renderList(listEl, blockEl, items, formatter) {
    if (!listEl || !blockEl) return;
    if (!items || !items.length) {
      blockEl.classList.add("hidden");
      listEl.innerHTML = "";
      return;
    }
    listEl.innerHTML = items.map(formatter).join("");
    blockEl.classList.remove("hidden");
  }

  const CATEGORY_LABELS = {
    verb_tense_past_perfect: "Past perfect vs. simple past",
    verb_tense_present_perfect: "Present perfect vs. simple past",
    subject_verb_agreement: "Subject-verb agreement",
    articles: "Article usage",
    prepositions: "Preposition usage",
    word_order: "Word order",
    modal_verbs: "Modal verbs",
    countable_uncountable_nouns: "Countable vs. uncountable nouns",
    false_friends_word_choice: "False friends / word choice",
    spelling: "Spelling",
    run_on_sentences: "Run-on sentences",
    punctuation: "Punctuation usage",
  };

  function renderSubmitResults(data) {
    if (liveFlagsEl) {
      liveFlagsEl.classList.add("hidden");
      liveFlagsEl.innerHTML = "";
    }
    renderList(errorsList, errorsBlock, data.errors, function (e) {
      const label = CATEGORY_LABELS[e.category] || e.category;
      return (
        '<li class="rounded-lg border border-border bg-secondary/25 p-2">' +
        "<strong>" + escapeHtml(label) + "</strong>" +
        (e.example ? ' — "' + escapeHtml(e.example) + '"' : "") +
        "</li>"
      );
    });
    renderList(recommendationsList, recommendationsBlock, data.recommendations, function (r) {
      return "<li>" + escapeHtml(r) + "</li>";
    });
    if (weakPointsBlock && weakPointsText) {
      if (data.weak_points) {
        weakPointsText.textContent = data.weak_points;
        weakPointsBlock.classList.remove("hidden");
      } else {
        weakPointsBlock.classList.add("hidden");
      }
    }
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
          renderSubmitResults(data);
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

  if (checkNowBtn) {
    checkNowBtn.addEventListener("click", forceLiveCheck);
  }

  if (essayEl) {
    essayEl.addEventListener("input", onEssayInput);
    countWords();
  }
})();
