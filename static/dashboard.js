(() => {
  const orb = document.getElementById("orb-stage");
  const stateTitle = document.getElementById("state-title");
  const stateCaption = document.getElementById("state-caption");
  const transcript = document.getElementById("transcript");
  const form = document.getElementById("command-form");
  const input = document.getElementById("command-input");
  const sendButton = document.getElementById("send-button");
  const micLabel = document.getElementById("mic-label");
  const micStatus = document.getElementById("mic-status");
  const aiStatus = document.getElementById("ai-status");
  const audioStatus = document.getElementById("audio-status");
  const voiceToggle = document.getElementById("voice-toggle");
  const connectionLabel = document.getElementById("connection-label");
  const weatherContent = document.getElementById("weather-content");
  const weatherLocation = document.getElementById("weather-location");
  const weatherUpdated = document.getElementById("weather-updated");
  const newsContent = document.getElementById("news-content");
  const newsCount = document.getElementById("news-count");
  const newsUpdated = document.getElementById("news-updated");
  const refreshInfo = document.getElementById("refresh-info");
  const bars = [...document.querySelectorAll(".visualizer i")];
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = SpeechRecognition ? new SpeechRecognition() : null;
  let voiceEnabled = true;
  let busy = false;
  let listening = false;
  let speaking = false;
  let waitingForWakeWord = true;
  let recognitionEnabled = Boolean(recognition);
  let restartTimer = null;
  let recognitionRetryDelay = 400;
  let acknowledgementTimer = null;

  if (recognition) {
    recognition.lang = "en-IN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
  }

  function setState(state, title, caption) {
    orb.className = `orb-stage state-${state}`;
    stateTitle.textContent = title;
    stateCaption.textContent = caption;
    aiStatus.textContent = state === "thinking" ? "PROCESSING" : "READY";
  }

  function showListeningState() {
    if (!recognitionEnabled) return;
    if (waitingForWakeWord) {
      setState("listening", "Wake word active", "Say “Jarvis” to start a conversation.");
      micLabel.textContent = "SAY “JARVIS”";
    } else {
      setState("listening", "I'm listening", "Ask a question, or say “go to sleep” to standby.");
      micLabel.textContent = "JARVIS IS LISTENING";
    }
    micStatus.textContent = listening ? "LISTENING" : "RECONNECTING";
    document.getElementById("wake-indicator").classList.toggle("listening", listening);
  }

  function addMessage(role, text) {
    const item = document.createElement("article");
    item.className = `message ${role}`;
    const label = document.createElement("span");
    label.className = "message-role";
    label.textContent = role === "user" ? "YOU" : "JARVIS";
    const content = document.createElement("p");
    content.textContent = text;
    item.append(label, content);
    transcript.append(item);
    transcript.scrollTop = transcript.scrollHeight;
  }

  function addTextElement(parent, tag, className, text) {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = text;
    parent.append(element);
    return element;
  }

  function formatWeatherTime(value, offsetSeconds) {
    if (!value) return "";
    const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
    const date = new Date(hasTimezone ? value : `${value}Z`);
    return Number.isNaN(date.getTime())
      ? ""
      : new Intl.DateTimeFormat("en-IN", {
          hour: "numeric",
          minute: "2-digit",
          timeZone: "UTC"
        }).format(new Date(date.getTime() + (offsetSeconds || 0) * 1000));
  }

  function renderWeather(weather) {
    weatherContent.replaceChildren();
    if (!weather.available) {
      addTextElement(weatherContent, "p", "intel-message", weather.error);
      weatherUpdated.textContent = "LIVE WEATHER · UNAVAILABLE";
      return;
    }

    weatherLocation.textContent = weather.location || "Configured location";
    const summary = document.createElement("div");
    summary.className = "weather-summary";
    addTextElement(summary, "strong", "weather-temperature", `${Math.round(weather.temperature)}°C`);
    const detail = document.createElement("div");
    addTextElement(detail, "span", "weather-condition", weather.condition);
    addTextElement(detail, "span", "weather-feels", `Feels like ${Math.round(weather.feels_like)}°C`);
    summary.append(detail);
    weatherContent.append(summary);

    const metrics = document.createElement("div");
    metrics.className = "weather-metrics";
    const weatherMetrics = [
      ["HUMIDITY", `${weather.humidity}%`],
      ["WIND", `${weather.wind_speed} km/h`]
    ];
    if (weather.pressure !== null && weather.pressure !== undefined) {
      weatherMetrics.push(["PRESSURE", `${weather.pressure} hPa`]);
    }
    if (weather.visibility !== null && weather.visibility !== undefined) {
      weatherMetrics.push(["VISIBILITY", `${weather.visibility} km`]);
    }
    if (weather.cloud_cover !== null && weather.cloud_cover !== undefined) {
      weatherMetrics.push(["CLOUD COVER", `${weather.cloud_cover}%`]);
    }
    weatherMetrics.forEach(([label, value]) => {
      const metric = document.createElement("div");
      addTextElement(metric, "span", "metric-label", label);
      addTextElement(metric, "strong", "metric-value", value);
      metrics.append(metric);
    });
    weatherContent.append(metrics);
    weatherUpdated.textContent = `OBSERVED ${formatWeatherTime(weather.observed_at, weather.timezone_offset)} LOCAL TIME · ${weather.source || "LIVE WEATHER"}`;
  }

  function renderHeadlines(headlines) {
    newsContent.replaceChildren();
    if (!headlines.available) {
      addTextElement(newsContent, "p", "intel-message", headlines.error);
      newsCount.textContent = "OFFLINE";
      newsUpdated.textContent = "INDIA · NEWSAPI";
      return;
    }
    if (!headlines.articles.length) {
      addTextElement(newsContent, "p", "intel-message", "No India headlines were returned.");
      newsCount.textContent = "0 STORIES";
      return;
    }

    newsCount.textContent = `${headlines.articles.length} STORIES`;
    headlines.articles.forEach((article) => {
      const item = document.createElement("article");
      item.className = "news-item";
      const link = document.createElement("a");
      link.className = "news-title";
      link.href = article.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = article.title;
      item.append(link);
      if (article.description) {
        addTextElement(item, "p", "news-description", article.description);
      }
      addTextElement(
        item,
        "span",
        "news-source",
        `${article.source}${article.published_at ? ` · ${formatHeadlineTime(article.published_at)}` : ""}`
      );
      newsContent.append(item);
    });
    newsUpdated.textContent = `${headlines.source || "NEWS"} · INDIA · UPDATED ${new Intl.DateTimeFormat("en-IN", {
      hour: "numeric",
      minute: "2-digit",
      timeZone: "Asia/Kolkata"
    }).format(new Date())} IST`;
  }

  function formatHeadlineTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? ""
      : new Intl.DateTimeFormat("en-IN", {
          day: "numeric",
          month: "short",
          hour: "numeric",
          minute: "2-digit",
          timeZone: "Asia/Kolkata"
        }).format(date);
  }

  async function loadDashboardInfo() {
    refreshInfo.disabled = true;
    try {
      const response = await fetch("/api/dashboard-info");
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
      renderWeather(result.weather);
      renderHeadlines(result.headlines);
    } catch (error) {
      renderWeather({ available: false, error: "Weather data could not be loaded. Check your connection and refresh." });
      renderHeadlines({ available: false, error: "Headlines could not be loaded. Check your connection and refresh." });
      console.error("Dashboard information request failed:", error);
    } finally {
      refreshInfo.disabled = false;
    }
  }

  function speakReply(text) {
    if (!voiceEnabled || !("speechSynthesis" in window)) {
      audioStatus.textContent = voiceEnabled ? "UNAVAILABLE" : "MUTED";
      speaking = false;
      showListeningState();
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;
    speaking = true;
    utterance.onstart = () => {
      audioStatus.textContent = "SPEAKING";
      setState("speaking", "Speaking", "Jarvis is responding to you.");
    };
    utterance.onend = () => {
      speaking = false;
      audioStatus.textContent = "ON";
      showListeningState();
      startListening();
    };
    utterance.onerror = (event) => {
      speaking = false;
      audioStatus.textContent = "ERROR";
      setState("idle", "Audio unavailable", "Check your browser and Windows audio output settings.");
      console.error("Browser speech synthesis failed:", event.error);
      startListening();
    };
    window.speechSynthesis.speak(utterance);
  }

  async function submitCommand(text, spoken = false) {
    const command = text.trim();
    if (!command || busy) return;
    busy = true;
    sendButton.disabled = true;
    waitingForWakeWord = false;
    if (listening && recognition) recognition.stop();
    addMessage("user", command);
    setState("thinking", "Thinking", "Working on your request...");
    if (spoken) {
      acknowledgementTimer = window.setTimeout(() => {
        if (busy && voiceEnabled) speakReply("One moment. I'm working on that.");
      }, 1100);
    }
    try {
      const response = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: command })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
      const reply = result.reply || "I don't have a response for that.";
      addMessage("assistant", reply);
      if (result.action_url) window.open(result.action_url, "_blank", "noopener,noreferrer");
      if (result.continue === false) waitingForWakeWord = true;
      speakReply(reply);
      if (result.continue === false) {
        connectionLabel.textContent = "SYSTEM ONLINE";
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "The request failed.";
      addMessage("assistant", message);
      setState("idle", "Request failed", "Check the local Jarvis server and try again.");
      console.error("Jarvis request failed:", error);
    } finally {
      window.clearTimeout(acknowledgementTimer);
      busy = false;
      sendButton.disabled = false;
      if (!speaking) startListening();
    }
  }

  function enterStandby() {
    waitingForWakeWord = true;
    addMessage("assistant", "Going to standby. Say “Jarvis” when you need me.");
    speakReply("Going to standby. Say Jarvis when you need me.");
  }

  function handleRecognizedSpeech(phrase) {
    if (busy || speaking) return;
    const text = phrase.trim();
    if (!text) return;

    if (waitingForWakeWord) {
      const wakeMatch = /\bjarvis\b/i.exec(text);
      if (!wakeMatch) return;
      if (listening && recognition) recognition.stop();
      waitingForWakeWord = false;
      const followup = text.slice(wakeMatch.index + wakeMatch[0].length).replace(/^[\s,.:;-]+/, "").trim();
      if (followup) {
        submitCommand(followup, true);
      } else {
        addMessage("assistant", "I'm awake. What can I help you with?");
        speakReply("I'm awake. What can I help you with?");
      }
      return;
    }

    if (/\b(?:jarvis[\s,]+)?(?:go[\s,]+to[\s,]+sleep|stand[\s-]?by)\b/i.test(text)) {
      if (listening && recognition) recognition.stop();
      addMessage("user", text);
      enterStandby();
      return;
    }
    if (listening && recognition) recognition.stop();
    submitCommand(text, true);
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value;
    input.value = "";
    submitCommand(text);
  });

  if (recognition) {
    recognition.onresult = (event) => {
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const phrase = result[0].transcript.trim();
        if (result.isFinal) {
          recognitionRetryDelay = 400;
          handleRecognizedSpeech(phrase);
        } else if (phrase) {
          const preview = waitingForWakeWord
            ? (/\bjarv/i.test(phrase) ? `Heard: ${phrase}` : "Listening for “Jarvis”.")
            : `Hearing: ${phrase}`;
          stateCaption.textContent = preview;
        }
      }
    };
    recognition.onerror = (event) => {
      if (event.error === "no-speech" || event.error === "aborted") return;
      if (event.error === "network") {
        recognitionRetryDelay = Math.min(
          Math.max(recognitionRetryDelay * 2, 1500),
          8000
        );
        micStatus.textContent = "RECONNECTING";
        micLabel.textContent = "RETRYING VOICE INPUT";
        setState("idle", "Voice service reconnecting", "Check your internet connection. Jarvis will retry automatically.");
        return;
      }
      recognitionEnabled = false;
      listening = false;
      document.getElementById("wake-indicator").classList.add("error");
      micStatus.textContent = event.error === "not-allowed" || event.error === "service-not-allowed"
        ? "PERMISSION NEEDED"
        : "UNAVAILABLE";
      micLabel.textContent = "VOICE INPUT UNAVAILABLE";
      setState("idle", "Microphone unavailable", "Allow microphone access and refresh, or type a message.");
      addMessage("assistant", `Voice input error: ${event.error}. Allow microphone access in your browser and refresh, or type a message.`);
    };
    recognition.onend = () => {
      listening = false;
      document.getElementById("wake-indicator").classList.remove("listening");
      if (!busy && !speaking) {
        showListeningState();
        window.clearTimeout(restartTimer);
        restartTimer = window.setTimeout(() => {
          startListening();
        }, recognitionRetryDelay);
      }
    };
  } else {
    recognitionEnabled = false;
    micStatus.textContent = "UNSUPPORTED";
    micLabel.textContent = "VOICE INPUT UNAVAILABLE";
    setState("idle", "Voice input unavailable", "Use Chrome or Edge, or type a message.");
  }

  function startListening() {
    if (!recognition || !recognitionEnabled || listening || busy || speaking || document.hidden) return;
    window.clearTimeout(restartTimer);
    try {
      recognition.start();
      listening = true;
      showListeningState();
    } catch (error) {
      if (error instanceof DOMException && error.name === "InvalidStateError") {
        restartTimer = window.setTimeout(startListening, 400);
        return;
      }
      console.error("Could not start wake-word recognition:", error);
      restartTimer = window.setTimeout(startListening, 1500);
    }
  }

  voiceToggle.addEventListener("click", () => {
    voiceEnabled = !voiceEnabled;
    voiceToggle.setAttribute("aria-pressed", String(voiceEnabled));
    voiceToggle.querySelector("span:last-child").textContent = voiceEnabled ? "VOICE ON" : "VOICE OFF";
    audioStatus.textContent = voiceEnabled ? "ON" : "MUTED";
    if (!voiceEnabled && "speechSynthesis" in window) window.speechSynthesis.cancel();
  });

  refreshInfo.addEventListener("click", loadDashboardInfo);

  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("click", () => submitCommand(button.dataset.command || ""));
  });

  bars.forEach((bar, index) => {
    bar.style.height = `${3 + ((index * 7) % 5)}px`;
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) startListening();
  });
  if (recognition) {
    setState("listening", "Wake word active", "Allow microphone access, then say “Jarvis”.");
    startListening();
  }
  loadDashboardInfo();
  window.setInterval(loadDashboardInfo, 15 * 60 * 1000);
})();
