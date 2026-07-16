/**
 * Speaking practice — record audio locally, transcribe on server (Vosk), TTS in browser.
 */

(function () {
  const config = document.getElementById("speaking-config");
  if (!config || !document.getElementById("callBtn")) return;

  const startUrl = config.dataset.startUrl;
  const chatUrl = config.dataset.chatUrl;
  const transcribeUrl = config.dataset.transcribeUrl;
  const endUrl = config.dataset.endUrl;
  const csrfToken = config.dataset.csrfToken || "";

  const callBtn = document.getElementById("callBtn");
  const callIcon = document.getElementById("callIcon");
  const statusEl = document.getElementById("status");
  const stepHintEl = document.getElementById("stepHint");
  const liveTranscriptEl = document.getElementById("liveTranscript");
  const doneSpeakingBtn = document.getElementById("doneSpeakingBtn");
  const textFallback = document.getElementById("textFallback");
  const typedAnswer = document.getElementById("typedAnswer");
  const sendTypedBtn = document.getElementById("sendTypedBtn");
  const statusBadgeTextEl = document.getElementById("statusBadgeText");
  const statusDotEl = document.getElementById("statusDot");
  const tutorNameEl = document.getElementById("tutorName");
  const tutorHintEl = document.getElementById("tutorHint");
  const conversationLog = document.getElementById("conversationLog");
  const characterButtons = document.querySelectorAll(".speaking-character-btn");

  const hasTts = Boolean(window.speechSynthesis);
  const hasRecorder = Boolean(navigator.mediaDevices && window.MediaRecorder);

  let selectedCharacter = "Miles";
  let sessionActive = false;
  let sessionStartedAt = null;
  let sessionId = null;
  let isBusy = false;
  let history = [];
  let voices = [];
  let micStream = null;
  let mediaRecorder = null;
  let recordChunks = [];

  function setCallIcon(name) {
    callIcon.setAttribute("data-lucide", name);
    if (window.lucide) lucide.createIcons();
  }

  function escapeHtml(text) {
    return String(text)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function addBubble(role, text) {
    const div = document.createElement("div");
    div.className = "speaking-bubble speaking-bubble--" + (role === "user" ? "user" : "ai");
    div.innerHTML =
      '<span class="speaking-bubble__meta">' +
      (role === "user" ? "You" : selectedCharacter) +
      "</span>" +
      escapeHtml(text);
    conversationLog.appendChild(div);
    conversationLog.scrollTop = conversationLog.scrollHeight;
  }

  function showTextFallback(visible) {
    if (textFallback) textFallback.classList.toggle("hidden", !visible);
  }

  function showDoneButton(visible) {
    if (doneSpeakingBtn) doneSpeakingBtn.classList.toggle("hidden", !visible);
  }

  function setUi(state) {
    const states = {
      idle: { status: "Ready when you are", hint: "Tap the microphone to start.", badge: "Ready", dot: "", icon: "mic", live: false, busy: false, showDone: false },
      starting: { status: "Starting session…", hint: "Checking microphone…", badge: "Starting", dot: "is-connecting", icon: "loader-circle", live: false, busy: true, showDone: false },
      listening: { status: "Recording your answer", hint: "Speak now, then tap Done speaking.", badge: "Recording", dot: "is-live", icon: "mic", live: true, busy: false, showDone: true },
      thinking: { status: "Tutor is thinking…", hint: "Transcribing and preparing a reply…", badge: "Thinking", dot: "is-connecting", icon: "loader-circle", live: true, busy: true, showDone: false },
      speaking: { status: "Tutor is speaking", hint: "Listen — you'll record your answer next.", badge: "Speaking", dot: "is-live", icon: "volume-2", live: true, busy: true, showDone: false },
      error: { status: "Something went wrong", hint: "Tap the microphone to try again.", badge: "Error", dot: "is-error", icon: "mic", live: false, busy: false, showDone: false },
    };
    const s = states[state] || states.idle;
    statusEl.textContent = s.status;
    stepHintEl.textContent = s.hint;
    statusBadgeTextEl.textContent = s.badge;
    statusDotEl.className = "speaking-status-dot " + s.dot;
    setCallIcon(s.icon);
    callBtn.classList.toggle("is-recording", s.live);
    callBtn.classList.toggle("is-busy", s.busy);
    callBtn.disabled = s.busy && state !== "listening";
    showDoneButton(s.showDone);
    showTextFallback(sessionActive && !s.busy);
    if (liveTranscriptEl && state !== "listening") {
      liveTranscriptEl.classList.add("hidden");
      liveTranscriptEl.textContent = "";
    }
    characterButtons.forEach(function (btn) {
      btn.disabled = sessionActive || isBusy;
    });
  }

  function updateCharacterUi() {
    characterButtons.forEach(function (btn) {
      btn.classList.toggle("is-selected", btn.dataset.character === selectedCharacter);
      btn.disabled = sessionActive || isBusy;
    });
  }

  characterButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (sessionActive || isBusy) return;
      selectedCharacter = btn.dataset.character;
      tutorNameEl.textContent = selectedCharacter + " is ready when you are.";
      updateCharacterUi();
    });
  });

  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = function () {
      voices = window.speechSynthesis.getVoices();
    };
    voices = window.speechSynthesis.getVoices();
  }

  function pickVoice() {
    const english = voices.filter(function (v) {
      return v.lang && v.lang.toLowerCase().startsWith("en");
    });
    if (!english.length) return null;
    if (selectedCharacter === "Maya") {
      return english.find(function (v) {
        return /female|samantha|zira|jenny|aria|emma/i.test(v.name);
      }) || english[0];
    }
    return english.find(function (v) {
      return /male|david|guy|ryan|brian|andrew/i.test(v.name);
    }) || english[0];
  }

  function speak(text) {
    return new Promise(function (resolve) {
      if (!hasTts) {
        resolve();
        return;
      }
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      const voice = pickVoice();
      if (voice) utterance.voice = voice;
      utterance.lang = "en-US";
      utterance.rate = 0.95;
      utterance.onend = resolve;
      utterance.onerror = resolve;
      window.speechSynthesis.speak(utterance);
    });
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

  async function ensureMicrophone() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("Microphone not supported in this browser.");
    }
    if (micStream) return micStream;
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    return micStream;
  }

  function releaseMicrophone() {
    if (micStream) {
      micStream.getTracks().forEach(function (track) {
        track.stop();
      });
      micStream = null;
    }
  }

  function pickMimeType() {
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
    for (let i = 0; i < types.length; i++) {
      if (MediaRecorder.isTypeSupported(types[i])) return types[i];
    }
    return "";
  }

  function startRecording() {
    if (!micStream) return;
    recordChunks = [];
    mediaRecorder = new MediaRecorder(micStream, { mimeType: pickMimeType() });
    mediaRecorder.ondataavailable = function (event) {
      if (event.data.size > 0) recordChunks.push(event.data);
    };
    mediaRecorder.start();
    if (liveTranscriptEl) {
      liveTranscriptEl.classList.remove("hidden");
      liveTranscriptEl.textContent = "Recording… speak now";
    }
    setUi("listening");
  }

  function stopRecording() {
    return new Promise(function (resolve) {
      if (!mediaRecorder || mediaRecorder.state === "inactive") {
        resolve(null);
        return;
      }
      mediaRecorder.onstop = function () {
        const blob = new Blob(recordChunks, { type: mediaRecorder.mimeType || "audio/webm" });
        resolve(blob);
      };
      mediaRecorder.stop();
    });
  }

  async function blobToWav16k(blob) {
    const arrayBuffer = await blob.arrayBuffer();
    const audioCtx = new AudioContext();
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
    await audioCtx.close();

    const targetRate = 16000;
    const offline = new OfflineAudioContext(1, Math.ceil(audioBuffer.duration * targetRate), targetRate);
    const source = offline.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();
    const channel = rendered.getChannelData(0);

    const pcm = new Int16Array(channel.length);
    for (let i = 0; i < channel.length; i++) {
      const s = Math.max(-1, Math.min(1, channel[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }

    const wavBuffer = new ArrayBuffer(44 + pcm.length * 2);
    const view = new DataView(wavBuffer);
    function writeStr(offset, str) {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    }
    writeStr(0, "RIFF");
    view.setUint32(4, 36 + pcm.length * 2, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, targetRate, true);
    view.setUint32(28, targetRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, "data");
    view.setUint32(40, pcm.length * 2, true);
    let offset = 44;
    for (let i = 0; i < pcm.length; i++) {
      view.setInt16(offset, pcm[i], true);
      offset += 2;
    }
    return new Blob([wavBuffer], { type: "audio/wav" });
  }

  async function transcribeRecording(blob) {
    const wavBlob = await blobToWav16k(blob);
    const formData = new FormData();
    formData.append("audio", wavBlob, "answer.wav");
    const response = await fetch(transcribeUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Transcription failed");
    return data.transcript;
  }

  async function handleUserMessage(message) {
    isBusy = true;
    setUi("thinking");
    addBubble("user", message);
    history.push({ role: "user", content: message });

    try {
      const data = await apiPost(chatUrl, {
        character: selectedCharacter,
        message: message,
        session_id: sessionId,
      });
      const reply = data.reply;
      history.push({ role: "assistant", content: reply });
      addBubble("ai", reply);
      setUi("speaking");
      tutorNameEl.textContent = reply;
      await speak(reply);
      if (sessionActive) {
        isBusy = false;
        startRecording();
      }
    } catch (err) {
      isBusy = false;
      setUi("error");
      stepHintEl.textContent = err.message;
    }
  }

  async function finishRecording() {
    if (!sessionActive || isBusy) return;
    isBusy = true;
    setUi("thinking");
    stepHintEl.textContent = "Transcribing your speech (first time may download a small model)…";

    try {
      const blob = await stopRecording();
      if (!blob || blob.size < 1000) {
        throw new Error("Recording too short. Speak for at least a second.");
      }
      const transcript = await transcribeRecording(blob);
      isBusy = false;
      await handleUserMessage(transcript);
    } catch (err) {
      isBusy = false;
      stepHintEl.textContent = err.message + " You can type your answer below instead.";
      showTextFallback(true);
      if (sessionActive) {
        statusEl.textContent = "Try again or type below";
        startRecording();
      } else {
        setUi("error");
      }
    }
  }

  async function startSession() {
    if (!hasRecorder) {
      setUi("error");
      stepHintEl.textContent = "Recording is not supported. Use Chrome or Edge.";
      return;
    }

    isBusy = true;
    setUi("starting");
    updateCharacterUi();
    history = [];
    sessionId = null;
    conversationLog.innerHTML = "";

    try {
      await ensureMicrophone();
      const data = await apiPost(startUrl, { character: selectedCharacter });
      sessionId = data.session_id;
      const question = data.question;
      history.push({ role: "assistant", content: question });
      addBubble("ai", question);
      tutorNameEl.textContent = question;
      tutorHintEl.textContent = "After the tutor speaks, record your answer and tap Done speaking.";
      isBusy = false;
      setUi("speaking");
      await speak(question);
      if (sessionActive) startRecording();
    } catch (err) {
      isBusy = false;
      sessionActive = false;
      releaseMicrophone();
      setUi("error");
      stepHintEl.textContent = err.message || "Could not access the microphone.";
      updateCharacterUi();
    }
  }

  async function saveSession() {
    const userTurns = history.filter(function (item) {
      return item.role === "user" && item.content;
    });
    if (!userTurns.length || !endUrl || !sessionId) return;

    const durationSeconds = sessionStartedAt
      ? Math.round((Date.now() - sessionStartedAt) / 1000)
      : 0;

    try {
      const data = await apiPost(endUrl, {
        character: selectedCharacter,
        session_id: sessionId,
        duration_seconds: durationSeconds,
      });
      if (window.applyLearnerStats) {
        window.applyLearnerStats(data);
      }
    } catch (err) {
      console.warn("Could not save speaking session:", err.message);
    }
  }

  function endSession() {
    const hadSession = sessionActive && history.some(function (item) {
      return item.role === "user";
    });
    sessionActive = false;
    isBusy = false;
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      try {
        mediaRecorder.stop();
      } catch (_) {
        /* ignore */
      }
    }
    releaseMicrophone();
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    showTextFallback(false);
    showDoneButton(false);
    setUi("idle");
    tutorNameEl.textContent = selectedCharacter + " is ready when you are.";
    tutorHintEl.textContent = "Tap the microphone to start another session.";
    updateCharacterUi();
    if (hadSession) {
      saveSession();
    }
    sessionId = null;
    sessionStartedAt = null;
  }

  callBtn.addEventListener("click", function () {
    if (isBusy && !sessionActive) return;
    if (sessionActive) {
      endSession();
      return;
    }
    sessionActive = true;
    sessionStartedAt = Date.now();
    startSession();
  });

  if (doneSpeakingBtn) {
    doneSpeakingBtn.addEventListener("click", finishRecording);
  }

  if (sendTypedBtn && typedAnswer) {
    function sendTyped() {
      const text = typedAnswer.value.trim();
      if (!text || !sessionActive || isBusy) return;
      typedAnswer.value = "";
      if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
      }
      handleUserMessage(text);
    }
    sendTypedBtn.addEventListener("click", sendTyped);
    typedAnswer.addEventListener("keydown", function (event) {
      if (event.key === "Enter") sendTyped();
    });
  }

  window.endSpeakingCall = endSession;
  setUi("idle");
  updateCharacterUi();
})();
