// API playground: builds a real request from the form and shows the response.
(function () {
  const $ = (id) => document.getElementById(id);

  const form = $("pgForm");
  const endpoint = $("pgEndpoint");
  const query = $("pgQuery");
  const limit = $("pgLimit");
  const idInput = $("pgId");
  const idHint = $("pgIdHint");
  const urlEl = $("pgUrl");
  const statusEl = $("pgStatus");
  const out = $("pgResponse");
  const sendBtn = $("pgSend");
  const audioWrap = $("pgAudioWrap");
  const audio = $("pgAudio");

  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

  function highlight(json) {
    return esc(json).replace(
      /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)/g,
      (m, str, colon, lit, num) => {
        if (str) return colon ? `<span class="n">${str}</span>${colon}` : `<span class="s">${str}</span>`;
        if (lit || num) return `<span class="k">${m}</span>`;
        return m;
      }
    );
  }

  // Path (relative to the site) for the current form values.
  function buildPath() {
    const type = endpoint.value;
    const id = encodeURIComponent(idInput.value.trim() || "{id}");
    if (type === "search") {
      const params = new URLSearchParams({ query: query.value.trim(), limit: limit.value || "10" });
      return `/api/v1/songs?${params}`;
    }
    if (type === "resolve") return `/api/v1/resolve?${new URLSearchParams({ query: query.value.trim() })}`;
    if (type === "song") return `/api/v1/songs/${id}`;
    return `/api/v1/songs/${id}/stream`;
  }

  function sync() {
    const type = endpoint.value;
    document.querySelectorAll(".field[data-for]").forEach((field) => {
      field.hidden = !field.dataset.for.split(" ").includes(type);
    });
    urlEl.textContent = location.origin + buildPath();
    sendBtn.textContent = type === "stream" ? "Load audio" : "Send request";
  }

  function setStatus(text, kind) {
    statusEl.textContent = text;
    statusEl.dataset.kind = kind || "";
  }

  async function send(event) {
    event.preventDefault();
    const type = endpoint.value;
    const path = buildPath();

    if ((type === "song" || type === "stream") && !idInput.value.trim()) {
      setStatus("Add an id first", "error");
      idInput.focus();
      return;
    }
    if ((type === "search" || type === "resolve") && !query.value.trim()) {
      setStatus("Add a query first", "error");
      query.focus();
      return;
    }

    audio.pause();
    audioWrap.hidden = true;
    sendBtn.disabled = true;
    setStatus("Sending...", "");

    // Streams are audio, not JSON: hand the URL to the audio element.
    if (type === "stream") {
      audio.src = path;
      audioWrap.hidden = false;
      out.textContent = "The audio stream is loaded in the player above.";
      setStatus("Streaming", "ok");
      audio.play().catch(() => setStatus("Press play to start the stream", "ok"));
      sendBtn.disabled = false;
      return;
    }

    const started = performance.now();
    try {
      const res = await fetch(path);
      const ms = Math.round(performance.now() - started);
      const text = await res.text();

      let body = text;
      let data = null;
      try {
        data = JSON.parse(text);
        body = JSON.stringify(data, null, 2);
      } catch {
        /* not JSON - show as is */
      }

      out.innerHTML = highlight(body);
      const left = res.headers.get("X-RateLimit-Remaining");
      setStatus(`${res.status} ${res.statusText || ""} · ${ms} ms${left ? ` · ${left} requests left` : ""}`.replace("  ", " "), res.ok ? "ok" : "error");

      // Carry the first song id over to the id field.
      const first = data && (data.results?.[0] || data.song || data.data);
      if (first?.id) {
        idInput.value = first.id;
        idHint.textContent = `Filled from the last response: ${first.title}`;
        sync();
      }
    } catch {
      out.textContent = "The request didn't go through. Check your connection and try again.";
      setStatus("Network error", "error");
    } finally {
      sendBtn.disabled = false;
    }
  }

  [endpoint, query, limit, idInput].forEach((el) => el.addEventListener("input", sync));
  form.addEventListener("submit", send);
  sync();
})();
