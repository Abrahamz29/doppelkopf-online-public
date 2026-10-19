export default function mount({data, setTriggerValue}) {
  const storageKey = "doko-diagnostics-v1";
  let recorder = window.__dokoDiagnostics;
  if (!recorder) {
    let saved = [];
    try { saved = JSON.parse(sessionStorage.getItem(storageKey) || "[]"); }
    catch (_) { /* Storage may be unavailable; recording continues in memory. */ }
    const now = Date.now();
    recorder = {
      events: Array.isArray(saved) ? saved.filter(e =>
        e && typeof e.at === "string" && now - Date.parse(e.at) < 86400000
      ).slice(-40) : [],
      run: "", blankSince: 0, blankReported: false, lastSend: 0,
      pending: false, rendered: "", send: null,
    };
    window.__dokoDiagnostics = recorder;
    recorder.persist = () => {
      try { sessionStorage.setItem(storageKey, JSON.stringify(recorder.events)); }
      catch (_) { /* Bounded in-memory fallback for blocked/full storage. */ }
    };
    recorder.add = (event, extra = {}) => {
      recorder.events.push({id: crypto.randomUUID(), at: new Date().toISOString(),
        event, run: recorder.run, ...extra});
      recorder.events = recorder.events.slice(-40);
      recorder.persist();
      if (["error", "rejection", "offline", "blank", "transport"].includes(event)) {
        recorder.pending = true;
      }
    };
    window.addEventListener("error", e => recorder.add("error", {
      line: e.lineno || 0, column: e.colno || 0,
      error_type: ["Error", "TypeError", "ReferenceError", "SyntaxError", "RangeError"]
        .includes(e.error?.name) ? e.error.name : "Error",
    }));
    window.addEventListener("unhandledrejection", () => recorder.add("rejection"));
    window.addEventListener("offline", () => recorder.add("offline"));
    window.addEventListener("online", () => recorder.add("online"));
    // Streamlit reports WebSocket failures to the console, not window.onerror.
    // Retain only a fixed category; never copy console arguments or credentials.
    for (const level of ["error", "warn"]) {
      const original = console[level].bind(console);
      console[level] = (...args) => {
        original(...args);
        if (args.some(arg => typeof arg === "string" &&
          /Cannot send rerun|WebSocket onclose|server is not responding/.test(arg))) {
          if (Date.now() - (recorder.lastTransport || 0) >= 10000) {
            recorder.lastTransport = Date.now();
            recorder.add("transport");
          }
        }
      };
    }
    document.addEventListener("click", e => {
      // Composed path includes buttons inside the keypad's shadow root.
      if (e.composedPath().some(el => el?.dataset?.action === "submit" ||
        el?.classList && [...el.classList].some(c =>
          c.startsWith("st-key-manual-save-round-") ||
          c.startsWith("st-key-dashboard-manual-save-round-")))) recorder.add("submit");
    }, true);
    setInterval(() => {
      const active = /\/(live_game|live_dashboard)\/?$/.test(location.pathname);
      if (!active || document.visibilityState !== "visible") {
        recorder.blankSince = 0;
        return;
      }
      const main = document.querySelector('[data-testid="stMainBlockContainer"]');
      const elements = main ? [...main.querySelectorAll(
        '[data-testid="stMetric"], [data-testid="stTabs"], button, .score-card, .dashboard-score-card'
      )].filter(el => el.getClientRects().length > 0).length : 0;
      const marker = main?.querySelector('[data-doko-render]')?.dataset.dokoRender;
      if (marker && marker !== recorder.rendered) {
        recorder.rendered = marker;
        recorder.add("rendered", {elements});
      }
      if (elements === 0) {
        recorder.blankSince ||= Date.now();
        if (!recorder.blankReported && Date.now() - recorder.blankSince >= 8000) {
          recorder.add("blank", {elements});
          recorder.blankReported = true;
        }
      } else {
        if (recorder.blankReported) recorder.add("restored", {elements});
        recorder.blankSince = 0;
        recorder.blankReported = false;
      }
      // Upload only incidents; never interrupt the normal save/render cycle.
      if (recorder.pending && navigator.onLine && recorder.send && elements > 0 &&
          marker === recorder.run && Date.now() - recorder.lastSend >= 60000) {
        recorder.lastSend = Date.now();
        try { recorder.send("report", recorder.events); }
        catch (_) { /* Retry after reconnect/remount; do not affect the app. */ }
      }
    }, 2000);
    recorder.pending = recorder.events.some(e =>
      ["error", "rejection", "offline", "blank", "transport"].includes(e.event));
  }
  recorder.run = data.run;
  recorder.send = setTriggerValue;
  const ack = new Set(data.ack || []);
  if (ack.size) {
    recorder.events = recorder.events.filter(e => !ack.has(e.id));
    recorder.pending = recorder.events.some(e =>
      ["error", "rejection", "offline", "blank", "transport"].includes(e.event));
    recorder.persist();
  }
  if (recorder.mountedRun !== data.run) {
    recorder.mountedRun = data.run;
    recorder.add("mounted");
  }
}
