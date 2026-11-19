/* Grama Sahayak web client. No build step, no dependencies.
   Voice in: server Whisper if available, else the browser Web Speech API. Voice out: browser voice, else server TTS.
   All server text is inserted with textContent (never innerHTML), so answers cannot inject markup. */
"use strict";
const $ = s => document.querySelector(s);
const h = (tag, props = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) k === "class" ? (e.className = v) : k.startsWith("on") ? e.addEventListener(k.slice(2), v) : e.setAttribute(k, v);
  kids.flat(Infinity).forEach(c => c != null && e.append(c.nodeType ? c : document.createTextNode(c)));
  return e;
};

const UI = {
  kn: { tagline: "ಧ್ವನಿಯಲ್ಲಿ ಕೇಳಿ, ಯೋಜನೆಗಳ ಅರ್ಹತೆ ತಿಳಿಯಿರಿ", ph: "ಇಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ…", listening: "ಕೇಳುತ್ತಿದ್ದೇನೆ… ಮಾತನಾಡಿ", thinking: "ಯೋಚಿಸುತ್ತಿದ್ದೇನೆ…",
    yes: "ಹೌದು, ಸರಿ", no: "ಇಲ್ಲ, ತಪ್ಪು", confirm: "ದಾಖಲೆಯಿಂದ ಓದಿದ್ದು. ಸರಿಯೇ?", profile: "ನಿಮ್ಮ ಬಗ್ಗೆ ನನಗೆ ಗೊತ್ತಿರುವುದು", forget: "ಎಲ್ಲವನ್ನೂ ಅಳಿಸಿ",
    trace: "ನಾನು ಹೇಗೆ ಉತ್ತರಿಸಿದೆ (ಏಜೆಂಟ್‌ಗಳು)", noMic: "ಈ ಬ್ರೌಸರ್‌ನಲ್ಲಿ ಧ್ವನಿ ಇಲ್ಲ. ದಯವಿಟ್ಟು ಟೈಪ್ ಮಾಡಿ.", noVoice: "ಈ ಫೋನ್‌ನಲ್ಲಿ ಕನ್ನಡ ಧ್ವನಿ ಇಲ್ಲ; ಉತ್ತರವನ್ನು ಓದಿ.",
    err: "ಏನೋ ತೊಂದರೆಯಾಯಿತು. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.", docs: "ತರಬೇಕಾದ ದಾಖಲೆಗಳು", call: "ಕರೆ", sms: "ಎಸ್‌ಎಂಎಸ್", src: "ಮೂಲ", yesQ: "ಹೌದು", noQ: "ಇಲ್ಲ", skipQ: "ಗೊತ್ತಿಲ್ಲ",
    expired: "ಅವಧಿ ಮುಗಿದಿದೆ, ಹೊಸದಾಗಿ ಪ್ರಾರಂಭಿಸುತ್ತಿದ್ದೇನೆ…", tulu: "ತುಳು ಧ್ವನಿ ಸೀಮಿತ: ಕನ್ನಡದಲ್ಲಿ ಕೇಳಿ ಕನ್ನಡದಲ್ಲಿ ಉತ್ತರಿಸುತ್ತೇನೆ." },
  en: { tagline: "Ask by voice. Know which schemes you qualify for.", ph: "Type here…", listening: "Listening… speak now", thinking: "Thinking…",
    yes: "Yes, correct", no: "No, wrong", confirm: "Read from your document. Is it right?", profile: "What I know about you", forget: "Forget everything",
    trace: "How I answered (agents)", noMic: "Voice is not available in this browser. Please type.", noVoice: "No voice for this language on this phone; please read the answer.",
    err: "Something went wrong. Please try again.", docs: "Documents to bring", call: "Call", sms: "SMS", src: "Source", yesQ: "Yes", noQ: "No", skipQ: "I don't know",
    expired: "Session expired, starting a new one…", tulu: "Tulu voice is limited: I listen and answer in Kannada." },
};
UI.tcy = UI.kn;
const LOCALE = { kn: "kn-IN", tcy: "kn-IN", en: "en-IN" };
const CHOICES = { ration_card: [["bpl", "BPL / ಬಿಪಿಎಲ್"], ["apl", "APL / ಎಪಿಎಲ್"], ["aay", "Antyodaya / ಅಂತ್ಯೋದಯ"], ["none", "None / ಇಲ್ಲ"]],
  gender: [["female", "ಮಹಿಳೆ / Woman"], ["male", "ಪುರುಷ / Man"]] };
const SOURCES = { document: "📄", speech: "🎤", button: "👆" };

const st = { lang: localStorage.getItem("gs_lang") || "kn", sid: null, caps: {}, speak: localStorage.getItem("gs_speak") !== "0",
  busy: false, rec: null, voices: [], pendingConfirm: null };
const T = () => UI[st.lang];

/* ---------- api ---------- */
async function api(path, body, isForm) {
  const r = await fetch("/api/" + path, { method: "POST", headers: isForm ? {} : { "Content-Type": "application/json" }, body: isForm ? body : JSON.stringify(body) });
  if (r.status === 404) { const e = new Error("expired"); e.expired = true; throw e; }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
async function newSession() {
  const s = await api("session", { lang: st.lang });
  st.sid = s.session_id;
  return s;
}
async function withSession(fn) {
  try { return await fn(); }
  catch (e) { if (!e.expired) throw e; banner(T().expired); await newSession(); return fn(); }
}

/* ---------- ui helpers ---------- */
function banner(t) { const b = $("#banner"); b.textContent = t || ""; b.hidden = !t; }
function scrollEnd() { window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }); }
function applyLang() {
  document.documentElement.lang = st.lang === "en" ? "en" : "kn";
  document.querySelectorAll(".langs .chip").forEach(c => c.classList.toggle("on", c.dataset.lang === st.lang));
  const t = T();
  $("#tagline").textContent = t.tagline; $("#text").placeholder = t.ph; $("#confirmTitle").textContent = t.confirm;
  $("#confirmYes").textContent = t.yes; $("#confirmNo").textContent = t.no;
  $("#profileTitle").textContent = t.profile; $("#forgetBtn").textContent = t.forget; $("#traceTitle").textContent = t.trace;
  banner(st.lang === "tcy" ? t.tulu : "");
}
function userBubble(t) { $("#log").append(h("div", { class: "msg user" }, t)); scrollEnd(); }
function typing() { const e = h("div", { class: "msg bot typing" }, T().thinking); $("#log").append(e); scrollEnd(); return e; }

function renderCard(c) {
  const T_ = T();
  const el = h("div", { class: "card " + (c.verdict || "INFO") }, h("h3", {}, c.name));
  if (c.verdict) el.append(h("div", { class: "badge" }, ({ ELIGIBLE: "✅", LIKELY: "🟡", NOT_ELIGIBLE: "⛔", NEED_INFO: "❔" })[c.verdict], " ", c.verdict_label));
  if (c.reasons?.length && c.verdict !== "NEED_INFO") el.append(h("ul", { class: "reasons" }, c.reasons.map(r => h("li", { class: r.status }, r.text))));
  if (c.hint) el.append(h("p", {}, c.hint));
  if (c.benefit) el.append(h("div", { class: "benefit" }, c.benefit));
  if (c.documents?.length) el.append(h("strong", {}, "📋 " + T_.docs), h("ul", { class: "checklist" }, c.documents.map(d => h("li", {}, h("label", {}, h("input", { type: "checkbox" }), d.name)))));
  if (c.apply) el.append(h("p", {}, c.apply));
  if (c.sources?.length) el.append(h("div", { class: "src" }, T_.src + ": ", c.sources.slice(0, 3).map((s, i) => [i ? " · " : "", h("a", { href: s.url, target: "_blank", rel: "noopener noreferrer" }, s.chunk_id.replace("#", " › "))])));
  return el;
}
function renderHelp(list) {
  if (!list?.length) return null;
  return h("div", { class: "help" }, list.map(x => h("a", { href: (x.sms ? "sms:" : "tel:") + x.number }, (x.sms ? "✉️ " : "📞 ") + x.number, h("small", {}, " " + x.name))));
}
function renderQuick(q) {
  const box = $("#quick"); box.replaceChildren(); box.hidden = !q;
  if (!q) return;
  const send = (txt) => ask(txt);
  if (q.kind === "bool") box.append(h("button", { class: "btn", onclick: () => send(st.lang === "en" ? "yes" : "ಹೌದು") }, "✔ " + T().yesQ), h("button", { class: "btn", onclick: () => send(st.lang === "en" ? "no" : "ಇಲ್ಲ") }, "✖ " + T().noQ));
  else if (CHOICES[q.key]) CHOICES[q.key].forEach(([v, l]) => box.append(h("button", { class: "btn", onclick: () => send(v === "none" ? "none" : v) }, l)));
  box.append(h("button", { class: "btn small", onclick: () => send(st.lang === "en" ? "skip" : "ಗೊತ್ತಿಲ್ಲ") }, T().skipQ));
}
function renderProfile(p) {
  const box = $("#profileBox"); box.hidden = !p?.length;
  $("#profile").replaceChildren(...(p || []).map(x => h("span", { class: "pchip" }, (SOURCES[x.source] || "") + " " + x.label + ": " + x.display)));
}
function renderTrace(tr) {
  const box = $("#traceBox"); box.hidden = !tr?.length;
  $("#trace").replaceChildren(...(tr || []).map(s => h("li", { class: (s.kind === "safety" ? "safety " : s.kind === "loop" ? "loop " : "") + (s.ok ? "" : "bad") },
    (s.kind === "safety" ? "🛡 " : s.kind === "loop" ? "↩ " : "") + s.agent + " ", h("code", {}, (s.ms ? s.ms + "ms · " : "") + s.summary))));
}
function renderConfirm(conf) {
  st.pendingConfirm = conf; const p = $("#confirmPanel"); p.hidden = !conf;
  if (!conf) return;
  $("#confirmTitle").textContent = T().confirm + " (" + conf.doc_name + (conf.aadhaar ? " · " + conf.aadhaar : "") + ")";
  const box = $("#confirmFields"); box.replaceChildren();
  conf.fields.forEach(f => {
    const choices = CHOICES[f.key];
    const type = typeof f.value;
    let input;
    if (choices) { input = h("select", { "data-key": f.key }, choices.map(([v, l]) => h("option", { value: v, ...(v === f.value ? { selected: "" } : {}) }, l))); }
    else if (type === "boolean") input = h("select", { "data-key": f.key, "data-bool": "1" }, h("option", { value: "true", ...(f.value ? { selected: "" } : {}) }, T().yesQ), h("option", { value: "false", ...(!f.value ? { selected: "" } : {}) }, T().noQ));
    else input = h("input", { "data-key": f.key, value: f.value, inputmode: "decimal" });
    box.append(h("div", { class: "frow" + (f.low_confidence ? " low" : "") }, h("label", {}, f.label + (f.low_confidence ? " ⚠" : "")), input));
  });
}
function show(r) {
  const bot = h("div", { class: "msg bot" + (r.abstained ? " abstain" : "") }, r.display ?? r.text);
  r.cards?.filter(c => c.verdict !== "NEED_INFO").forEach(c => bot.append(renderCard(c)));
  const help = renderHelp(r.helplines); if (help) bot.append(help);
  $("#log").append(bot);
  renderQuick(r.question); renderProfile(r.profile); renderTrace(r.trace); renderConfirm(r.confirm);
  scrollEnd();
  if (r.speech) say(r.speech, r.reply_lang);
}
/* the on-screen text is rich; the spoken text is `speech` (no citations) */

/* ---------- speech out ---------- */
function loadVoices() { st.voices = speechSynthesis?.getVoices?.() || []; }
if ("speechSynthesis" in window) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; }
let audioEl = null;
async function say(text, lang) {
  if (!st.speak) return;
  const loc = lang === "en" ? "en-IN" : "kn-IN";
  try { speechSynthesis?.cancel?.(); audioEl?.pause(); } catch {}
  const voice = st.voices.find(v => v.lang.replace("_", "-").toLowerCase().startsWith(loc.slice(0, 2).toLowerCase()) && (lang !== "en" || v.lang.toLowerCase().includes("in")))
    || st.voices.find(v => v.lang.toLowerCase().startsWith(loc.slice(0, 2)));
  if (voice && "speechSynthesis" in window) {
    const u = new SpeechSynthesisUtterance(text); u.voice = voice; u.lang = voice.lang; u.rate = 0.92; speechSynthesis.speak(u); return;
  }
  if (st.caps.server_tts) {
    try {
      const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: text.slice(0, 700), lang: st.lang }) });
      if (r.ok) { audioEl = new Audio(URL.createObjectURL(await r.blob())); audioEl.play(); return; }
    } catch {}
  }
  banner(T().noVoice);
}

/* ---------- actions ---------- */
async function ask(text) {
  text = (text || "").trim(); if (!text || st.busy) return;
  st.busy = true; userBubble(text); $("#text").value = ""; const t = typing();
  try { show(await withSession(() => api("ask", { session_id: st.sid, text, lang: st.lang }))); }
  catch (e) { $("#log").append(h("div", { class: "msg bot abstain" }, T().err)); }
  finally { t.remove(); st.busy = false; }
}
async function sendImage(file) {
  if (!file || st.busy) return;
  st.busy = true; userBubble("📷 " + file.name); const t = typing();
  try {
    const fd = () => { const f = new FormData(); f.append("image", file); f.append("session_id", st.sid); f.append("lang", st.lang); return f; };
    show(await withSession(() => api("vision", fd(), true)));
  } catch (e) { $("#log").append(h("div", { class: "msg bot abstain" }, T().err)); }
  finally { t.remove(); st.busy = false; }
}
async function confirmDoc(accept) {
  const corrections = {};
  document.querySelectorAll("#confirmFields [data-key]").forEach(el => {
    let v = el.value; if (el.dataset.bool) v = v === "true"; else if (!isNaN(+v) && v !== "" && !CHOICES[el.dataset.key]) v = +v;
    corrections[el.dataset.key] = v;
  });
  $("#confirmPanel").hidden = true; const t = typing();
  try { show(await withSession(() => api("confirm", { session_id: st.sid, accept, corrections }))); }
  catch (e) { $("#log").append(h("div", { class: "msg bot abstain" }, T().err)); } finally { t.remove(); }
}

/* ---------- speech in ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
function setMic(on) { $("#mic").setAttribute("aria-pressed", on); $("#micIcon").textContent = on ? "⏹" : "🎤"; if (on) banner(T().listening); else banner(st.lang === "tcy" ? T().tulu : ""); }
async function toggleMic() {
  if (st.rec) { st.rec.stop(); return; }
  try { speechSynthesis?.cancel?.(); } catch {}
  if (st.caps.server_stt && navigator.mediaDevices?.getUserMedia) return recordToServer();
  if (!SR) { banner(T().noMic); return; }
  const r = new SR(); r.lang = LOCALE[st.lang]; r.interimResults = false; r.maxAlternatives = 1; st.rec = r;
  r.onresult = e => ask(e.results[0][0].transcript);
  r.onerror = () => { }; r.onend = () => { st.rec = null; setMic(false); };
  setMic(true); r.start();
}
async function recordToServer() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true }); const chunks = [];
  const mr = new MediaRecorder(stream); st.rec = { stop: () => mr.stop() };
  mr.ondataavailable = e => chunks.push(e.data);
  mr.onstop = async () => {
    stream.getTracks().forEach(t => t.stop()); st.rec = null; setMic(false);
    const fd = new FormData(); fd.append("audio", new Blob(chunks, { type: mr.mimeType }), "a.webm"); fd.append("lang", st.lang);
    try { const r = await api("transcribe", fd, true); ask(r.text); } catch { banner(T().err); }
  };
  setMic(true); mr.start(); setTimeout(() => mr.state === "recording" && mr.stop(), 12000);
}

/* ---------- boot ---------- */
async function boot() {
  applyLang();
  try { const hl = await (await fetch("/api/health")).json(); st.caps = hl.capabilities; } catch { }
  const s = await newSession(); if (s.note) banner(s.note);
  $("#log").append(h("div", { class: "msg bot" }, s.greeting));
  say(s.greeting, st.lang === "en" ? "en" : "kn");
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => { });
}
document.querySelectorAll(".langs .chip").forEach(b => b.addEventListener("click", async () => {
  st.lang = b.dataset.lang; localStorage.setItem("gs_lang", st.lang); applyLang();
  try { const s = await newSession(); $("#log").append(h("div", { class: "msg bot" }, s.greeting)); renderQuick(null); renderConfirm(null); renderProfile([]); say(s.greeting, st.lang === "en" ? "en" : "kn"); } catch { }
}));
$("#form").addEventListener("submit", e => { e.preventDefault(); ask($("#text").value); });
$("#mic").addEventListener("click", toggleMic);
$("#cam").addEventListener("click", () => $("#file").click());
$("#file").addEventListener("change", e => { sendImage(e.target.files[0]); e.target.value = ""; });
$("#confirmYes").addEventListener("click", () => confirmDoc(true));
$("#confirmNo").addEventListener("click", () => confirmDoc(false));
$("#forgetBtn").addEventListener("click", async () => { show(await withSession(() => api("forget", { session_id: st.sid }))); });
$("#speakToggle").addEventListener("click", e => { st.speak = !st.speak; localStorage.setItem("gs_speak", st.speak ? "1" : "0"); e.currentTarget.setAttribute("aria-pressed", st.speak); e.currentTarget.textContent = st.speak ? "🔊" : "🔇"; if (!st.speak) speechSynthesis?.cancel?.(); });
$("#speakToggle").textContent = st.speak ? "🔊" : "🔇";
boot();
