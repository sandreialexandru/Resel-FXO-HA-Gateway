/*
 * Resel Intercom Card
 * Lovelace card for the Resel FXO HA Gateway integration.
 *
 *   type: custom:resel-intercom-card
 *
 * Works with card-mod: the root element is <ha-card> and every part has a class
 * (.header .status .meter .btn .answer .hangup .ptt .custom-grid .custom ...).
 * Entity ids below are defaults built from `entity_prefix`; override any of them
 * under `entities:`.
 */

(() => {
"use strict";
const DOMAIN = "resel_fxo_gateway";
const TARGET_RATE = 16000;
const FRAME_SAMPLES = 640; // 40 ms at 16 kHz
const BARS = 12;

const DEFAULT_LABELS = {
  title: "Intercom",
  idle: "Idle",
  ringing: "Ringing",
  connecting: "Connecting",
  listening: "In call",
  talking: "Talking",
  idle_text: "Nobody is calling",
  ringing_text: "Someone is calling from the panel",
  connecting_text: "Connecting to the line…",
  listening_text: "Listening to the line",
  talking_text: "You are heard at the panel",
  answer: "Answer",
  hangup: "Hang up",
  ptt_unavailable: "Talking is available during a call",
  ptt_hold: "Hold to talk",
  ptt_tap: "Tap to talk",
  ptt_talking_hold: "Talking… release to listen",
  ptt_talking_tap: "Talking… tap to listen",
  line_level: "Line level",
  mic_level: "Your microphone",
  level_idle: "line idle",
  level_ringing: "line muted while ringing",
  talk_pause_note: "Listening to the line is paused while you talk.",
  enable_sound: "Tap to enable sound",
  no_mic: "Microphone not available (needs HTTPS and permission)",
  ptt_failed: "The gateway did not switch to talk mode",
  link_down: "Audio link is down",
};

const DEFAULT_BUTTONS = [
  { name: "Open door", icon: "mdi:door-open", entity_key: "door_open" },
  { name: "Stair light", icon: "mdi:lightbulb-on-outline", entity_key: "stair_light" },
  { name: "Call panel", icon: "mdi:phone-outgoing", entity_key: "call_panel", disabled_when: ["in_call"] },
  { name: "Answer & open", icon: "mdi:phone-check", entity_key: "answer_open", disabled_when: ["in_call"] },
];

// Object ids of the default ESPHome entities (after the prefix).
const DEFAULT_ENTITY_SUFFIX = {
  state: "sensor.{p}stare",
  answer: "button.{p}raspunde",
  hangup: "button.{p}inchide",
  ptt: "switch.{p}ptt",
  level: "sensor.{p}nivel_microfon_rms",
  door_open: "button.{p}deschide_usa",
  stair_light: "button.{p}lumina_scara_008",
  call_panel: "button.{p}cheama_panoul_0",
  answer_open: "button.{p}raspunde_si_deschide_usa",
};

const CAPTURE_WORKLET = `
class ReselCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("resel-capture", ReselCapture);
`;

const STYLE = `
:host { display: block; }
ha-card { padding: 16px; box-sizing: border-box; }
.wrap { display: flex; flex-direction: column; gap: 14px; }
.header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.title { font-size: 20px; font-weight: 600; color: var(--primary-text-color); }
.chip {
  display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px;
  font-size: 14px; font-weight: 500; white-space: nowrap;
  background: var(--chip-bg, rgba(127,127,127,.15)); color: var(--chip-fg, var(--secondary-text-color));
}
.chip .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.status .main { font-size: 16px; font-weight: 500; color: var(--primary-text-color); }
.status .sub { font-size: 14px; color: var(--secondary-text-color); margin-top: 2px; }
.meter {
  background: var(--secondary-background-color, rgba(127,127,127,.1));
  border-radius: 12px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px;
}
.meter .row { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; color: var(--secondary-text-color); }
.meter .bars { display: flex; align-items: flex-end; gap: 4px; height: 36px; }
.meter .bar { flex: 1; height: 4px; border-radius: 2px; background: var(--divider-color, #888); transition: height .08s linear; }
.meter.live .bar { background: var(--bar-color, var(--success-color, #43a047)); }
.meter .note { font-size: 13px; color: var(--secondary-text-color); }
.meter .sound { align-self: flex-start; }
.pair, .custom-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.btn {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  border: 1px solid var(--divider-color, #888); border-radius: 14px;
  background: var(--card-background-color, transparent); color: var(--primary-text-color);
  font: inherit; font-weight: 500; font-size: 15px; height: 48px; padding: 0 12px; cursor: pointer;
  -webkit-tap-highlight-color: transparent; user-select: none; -webkit-user-select: none;
}
.btn:disabled {
  cursor: default; opacity: .7; border-style: dashed;
  background: var(--secondary-background-color, rgba(127,127,127,.12));
  color: var(--disabled-text-color, #8a8a8a); border-color: var(--divider-color, #888);
}
.custom:not(:disabled) {
  color: var(--primary-color, #03a9f4); border-color: var(--primary-color, #03a9f4);
  background: color-mix(in srgb, var(--primary-color, #03a9f4) 12%, transparent);
}
.btn ha-icon { --mdc-icon-size: 20px; flex: none; }
.btn span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.answer, .hangup { height: 52px; font-size: 16px; }
.answer:not(:disabled) { background: var(--success-color, #43a047); color: #fff; border-color: transparent; font-weight: 600; }
.hangup:not(:disabled) { background: var(--error-color, #db4437); color: #fff; border-color: transparent; font-weight: 600; }
.ptt {
  height: 96px; border-radius: 18px; flex-direction: column; gap: 6px; font-size: 16px;
  touch-action: none; -webkit-touch-callout: none;
}
.ptt ha-icon { --mdc-icon-size: 26px; }
.ptt .timer { font-size: 13px; font-weight: 500; opacity: .9; }
.ptt.ready { border-color: var(--success-color, #43a047); }
.ptt.ready ha-icon { color: var(--success-color, #43a047); }
.ptt.active { background: var(--error-color, #db4437); border-color: transparent; color: #fff; font-weight: 600; }
.ptt.active ha-icon { color: #fff; }
.toast { font-size: 13px; color: var(--error-color, #db4437); min-height: 0; }
.toast:empty { display: none; }
ha-card[data-state="ringing"] { --chip-bg: rgba(255,179,0,.18); --chip-fg: var(--warning-color, #ffa000); }
ha-card[data-state="connecting"] { --chip-bg: rgba(255,179,0,.18); --chip-fg: var(--warning-color, #ffa000); }
ha-card[data-state="listening"] { --chip-bg: rgba(67,160,71,.18); --chip-fg: var(--success-color, #43a047); }
ha-card[data-state="talking"] { --chip-bg: rgba(219,68,55,.18); --chip-fg: var(--error-color, #db4437); --bar-color: var(--error-color, #db4437); }
ha-card[data-state="unavailable"] { --chip-bg: rgba(127,127,127,.2); }
`;

function bytesToB64(bytes) {
  let s = "";
  const CH = 0x8000;
  for (let i = 0; i < bytes.length; i += CH) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  }
  return btoa(s);
}

function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

class ReselIntercomCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._cfg = null;
    this._built = false;
    // state
    this._mode = "idle"; // idle | ringing | connecting | listening | talking | unavailable
    this._talkRequested = false;
    this._streaming = false;
    this._talkStart = 0;
    this._linkUp = false;
    this._unsub = null;
    this._subscribing = false;
    this._toastTimer = null;
    this._reqTimer = null;
    this._levelTimer = null;
    this._history = new Array(BARS).fill(-90);
    this._lastAudioAt = 0;
    // audio
    this._ctx = null;
    this._pb = null; // playback graph
    this._nextTime = 0;
    this._mic = null; // capture graph
    this._frame = new Int16Array(FRAME_SAMPLES);
    this._frameLen = 0;
    this._resPos = 0;
  }

  // ---------------------------------------------------------------- config
  static getStubConfig() {
    return { type: "custom:resel-intercom-card" };
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    const prefix = config.entity_prefix || "resel_fxo_gateway_interfon_";
    const entities = {};
    for (const [k, tpl] of Object.entries(DEFAULT_ENTITY_SUFFIX)) {
      entities[k] = (config.entities && config.entities[k]) || tpl.replace("{p}", prefix);
    }
    const labels = Object.assign({}, DEFAULT_LABELS, config.labels || {});
    const buttons = (config.buttons || DEFAULT_BUTTONS).slice(0, 12).map((b) => {
      const nb = Object.assign({}, b);
      if (!nb.entity && nb.entity_key) nb.entity = entities[nb.entity_key];
      return nb;
    });
    this._cfg = {
      title: config.title ?? labels.title,
      entities,
      labels,
      buttons,
      ptt_mode: config.ptt_mode === "toggle" ? "toggle" : "hold",
      ptt_timeout: Number(config.ptt_timeout ?? 30),
      highpass_hz: Number(config.highpass_hz ?? 250),
      lowpass_hz: Number(config.lowpass_hz ?? 3400),
      gain: Number(config.gain ?? 2),
      mic_gain: Number(config.mic_gain ?? 1),
      show_header: config.show_header !== false,
      show_level: config.show_level !== false,
      show_timer: config.show_timer === true,
    };
    this._build();
    if (this._hass) this._update();
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, rows: "auto", min_columns: 6 };
  }

  // ---------------------------------------------------------------- DOM
  _build() {
    const L = this._cfg.labels;
    const root = this.shadowRoot;
    root.innerHTML = "";
    const style = document.createElement("style");
    style.textContent = STYLE;
    const card = document.createElement("ha-card");
    card.innerHTML = `
      <div class="wrap">
        <div class="header"><div class="title"></div><div class="chip"><span class="dot"></span><span class="chip-text"></span></div></div>
        <div class="status"><div class="main"></div><div class="sub"></div></div>
        <div class="meter">
          <div class="row"><span class="lvl-name"></span><span class="lvl-val"></span></div>
          <div class="bars"></div>
          <div class="note"></div>
          <button type="button" class="btn sound"><ha-icon icon="mdi:volume-high"></ha-icon><span></span></button>
        </div>
        <div class="pair">
          <button type="button" class="btn answer"><ha-icon icon="mdi:phone"></ha-icon><span></span></button>
          <button type="button" class="btn hangup"><ha-icon icon="mdi:phone-hangup"></ha-icon><span></span></button>
        </div>
        <button type="button" class="btn ptt"><ha-icon icon="mdi:microphone"></ha-icon><span class="ptt-text"></span><span class="timer"></span></button>
        <div class="toast"></div>
        <div class="custom-grid"></div>
      </div>`;
    root.append(style, card);
    this._el = {
      card,
      title: card.querySelector(".title"),
      header: card.querySelector(".header"),
      chip: card.querySelector(".chip-text"),
      main: card.querySelector(".status .main"),
      sub: card.querySelector(".status .sub"),
      meter: card.querySelector(".meter"),
      lvlName: card.querySelector(".lvl-name"),
      lvlVal: card.querySelector(".lvl-val"),
      bars: card.querySelector(".bars"),
      note: card.querySelector(".note"),
      sound: card.querySelector(".sound"),
      answer: card.querySelector(".answer"),
      hangup: card.querySelector(".hangup"),
      ptt: card.querySelector(".ptt"),
      pttText: card.querySelector(".ptt-text"),
      timer: card.querySelector(".timer"),
      toast: card.querySelector(".toast"),
      grid: card.querySelector(".custom-grid"),
    };
    const e = this._el;
    e.title.textContent = this._cfg.title;
    e.header.style.display = this._cfg.show_header ? "" : "none";
    e.meter.style.display = this._cfg.show_level ? "" : "none";
    e.answer.querySelector("span").textContent = L.answer;
    e.hangup.querySelector("span").textContent = L.hangup;
    e.sound.querySelector("span").textContent = L.enable_sound;
    this._bars = [];
    for (let i = 0; i < BARS; i++) {
      const b = document.createElement("div");
      b.className = "bar";
      e.bars.appendChild(b);
      this._bars.push(b);
    }

    // any touch of the card is a user gesture: unlock audio
    card.addEventListener("pointerdown", () => this._unlockAudio(), { capture: true });
    e.sound.addEventListener("click", () => this._unlockAudio());
    e.answer.addEventListener("click", () => this._press(this._cfg.entities.answer));
    e.hangup.addEventListener("click", () => this._press(this._cfg.entities.hangup));

    const ptt = e.ptt;
    ptt.addEventListener("contextmenu", (ev) => ev.preventDefault());
    ptt.addEventListener("pointerdown", (ev) => {
      if (ptt.disabled) return;
      ev.preventDefault();
      try { ptt.setPointerCapture(ev.pointerId); } catch (_) { /* ignore */ }
      if (this._cfg.ptt_mode === "hold") this._talkBegin();
      else if (this._talkRequested || this._streaming) this._talkEnd();
      else this._talkBegin();
    });
    const release = () => { if (this._cfg.ptt_mode === "hold") this._talkEnd(); };
    ptt.addEventListener("pointerup", release);
    ptt.addEventListener("pointercancel", release);
    ptt.addEventListener("lostpointercapture", release);

    // custom buttons
    e.grid.innerHTML = "";
    this._cbtns = this._cfg.buttons.map((b) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn custom";
      const ic = document.createElement("ha-icon");
      if (b.icon) ic.setAttribute("icon", b.icon);
      const sp = document.createElement("span");
      sp.textContent = b.name || "";
      btn.append(ic, sp);
      btn.addEventListener("click", () => this._runAction(b));
      e.grid.appendChild(btn);
      return { cfg: b, btn, label: sp, icon: ic };
    });
    this._built = true;
  }

  // ---------------------------------------------------------------- hass
  set hass(hass) {
    this._hass = hass;
    if (this._built) this._update();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (this._hass && this._built) this._update();
  }

  disconnectedCallback() {
    this._talkEnd();
    this._unsubscribe();
    this._releaseMic();
    this._stopLevelTimer();
  }

  _stateObj(key) {
    const id = this._cfg.entities[key];
    return id && this._hass ? this._hass.states[id] : undefined;
  }

  _computeMode() {
    const st = this._stateObj("state");
    if (!st || st.state === "unavailable" || st.state === "unknown") return "unavailable";
    const t = st.state.toLowerCase();
    // the ESP reports Romanian status strings: Suna / Conectare / In apel - ascult / In apel - vorbesc / Inactiv
    if (t.includes("vorbesc") || t.includes("talk")) return "talking";
    if (t.includes("ascult") || t.includes("in apel") || t.includes("in call") || t.includes("listen")) return "listening";
    if (t.includes("conect")) return "connecting";
    if (t.includes("suna") || t.includes("ring")) return "ringing";
    return "idle";
  }

  _update() {
    const L = this._cfg.labels;
    const e = this._el;
    const mode = this._computeMode();
    this._mode = mode;
    const inCall = mode === "listening" || mode === "talking";
    const pttState = this._stateObj("ptt");
    const pttOn = !!pttState && pttState.state === "on";

    // talk streaming follows the gateway's PTT switch
    if (this._talkRequested && pttOn && !this._streaming && inCall) this._startStream();
    if (this._streaming && !pttOn) {
      this._talkRequested = false;
      this._stopStream();
    }
    if (!inCall && (this._talkRequested || this._streaming)) this._talkEnd();

    // audio subscription + mic lifetime follow the call
    const wantAudio = inCall || mode === "connecting";
    if (wantAudio) this._subscribe();
    else {
      this._unsubscribe();
      this._releaseMic();
    }

    // header / status
    const talking = mode === "talking" || pttOn;
    e.card.dataset.state = talking && inCall ? "talking" : mode;
    const chipKey = talking && inCall ? "talking" : mode === "unavailable" ? "idle" : mode;
    e.chip.textContent = mode === "unavailable" ? "Unavailable" : L[chipKey];
    const textKey = (talking && inCall ? "talking" : mode === "unavailable" ? "idle" : mode) + "_text";
    e.main.textContent = mode === "unavailable" ? "Gateway unavailable" : L[textKey];
    const raw = this._stateObj("state");
    e.sub.textContent = raw ? raw.state : "";

    // buttons
    const avail = (k) => {
      const s = this._stateObj(k);
      return !!s && s.state !== "unavailable";
    };
    e.answer.disabled = !(mode === "ringing" && avail("answer"));
    e.hangup.disabled = !((inCall || mode === "connecting") && avail("hangup"));
    const micOk = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) && window.isSecureContext !== false;
    e.ptt.disabled = !(inCall && avail("ptt"));
    const active = this._talkRequested || this._streaming || (inCall && pttOn);
    e.ptt.classList.toggle("active", active && inCall);
    e.ptt.classList.toggle("ready", inCall && !active);
    const hold = this._cfg.ptt_mode === "hold";
    e.pttText.textContent = !inCall
      ? L.ptt_unavailable
      : active
      ? hold ? L.ptt_talking_hold : L.ptt_talking_tap
      : hold ? L.ptt_hold : L.ptt_tap;
    e.timer.textContent = "";
    e.ptt.querySelector("ha-icon").setAttribute("icon", active && inCall ? "mdi:microphone" : inCall ? "mdi:microphone" : "mdi:microphone-off");
    if (inCall && !micOk) this._flash(L.no_mic, 0);

    // custom buttons: unavailable entity -> disabled
    for (const c of this._cbtns) {
      const id = c.cfg.entity;
      const s = id && this._hass ? this._hass.states[id] : null;
      const dw = c.cfg.disabled_when ? [].concat(c.cfg.disabled_when) : [];
      // modes: idle, ringing, connecting, listening, talking, or "in_call" (= listening + talking)
      const blocked = dw.includes(mode) || (inCall && dw.includes("in_call"));
      c.btn.disabled = blocked || (!!id && !!this._hass && (!s || s.state === "unavailable"));
      const st = s ? s.state : "unavailable";
      c.btn.dataset.state = st; // card-mod hook: .custom[data-state="on"] { ... }
      const si = c.cfg.state_icons;
      const icon = (si && si[st]) || c.cfg.icon;
      if (icon && c.icon.getAttribute("icon") !== icon) c.icon.setAttribute("icon", icon);
      const col = c.cfg.state_colors && c.cfg.state_colors[st];
      c.btn.style.color = col || "";
      if (col) c.btn.style.borderColor = col; else c.btn.style.borderColor = "";
      if (!c.cfg.name && s) c.label.textContent = s.attributes.friendly_name || id;
    }

    // meter
    e.meter.classList.toggle("live", inCall);
    e.note.textContent = talking && inCall ? L.talk_pause_note : "";
    e.sound.style.display = inCall && this._ctx && this._ctx.state !== "running" ? "" : "none";
    if (!this._ctx && inCall) e.sound.style.display = "";
    if (inCall) this._startLevelTimer();
    else {
      this._stopLevelTimer();
      this._history.fill(-90);
      this._drawBars();
      e.lvlName.textContent = L.line_level;
      e.lvlVal.textContent = mode === "ringing" ? L.level_ringing : L.level_idle;
    }
  }

  // ---------------------------------------------------------------- actions
  _press(entityId) {
    if (entityId && this._hass) this._hass.callService("button", "press", { entity_id: entityId });
  }

  _runAction(b) {
    const hass = this._hass;
    if (!hass) return;
    let action = b.tap_action;
    if (!action && b.entity) {
      const dom = b.entity.split(".")[0];
      if (dom === "button" || dom === "input_button") action = { action: "perform-action", perform_action: `${dom}.press`, target: { entity_id: b.entity } };
      else if (dom === "script") action = { action: "perform-action", perform_action: "script.turn_on", target: { entity_id: b.entity } };
      else if (dom === "scene") action = { action: "perform-action", perform_action: "scene.turn_on", target: { entity_id: b.entity } };
      else if (["switch", "light", "input_boolean", "fan", "cover", "lock"].includes(dom)) action = { action: "toggle" };
      else action = { action: "more-info" };
    }
    if (!action) return;
    const type = action.action || "none";
    const entity = action.entity || b.entity;
    switch (type) {
      case "perform-action":
      case "call-service": {
        const svc = action.perform_action || action.service;
        if (!svc || !svc.includes(".")) return;
        const [d, s] = svc.split(".");
        const data = Object.assign({}, action.data || action.service_data || {});
        const call = hass.callService(d, s, data, action.target);
        if (call && call.catch) call.catch((err) => this._flash(String(err.message || err)));
        break;
      }
      case "toggle":
        if (entity) hass.callService("homeassistant", "toggle", { entity_id: entity });
        break;
      case "more-info":
        this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: entity } }));
        break;
      case "navigate":
        if (action.navigation_path) {
          history.pushState(null, "", action.navigation_path);
          window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
        }
        break;
      case "url":
        if (action.url_path) window.open(action.url_path, action.new_tab === false ? "_self" : "_blank");
        break;
      default:
        break;
    }
  }

  _flash(text, ms = 4000) {
    const t = this._el.toast;
    t.textContent = text;
    clearTimeout(this._toastTimer);
    if (ms) this._toastTimer = setTimeout(() => (t.textContent = ""), ms);
  }

  // ---------------------------------------------------------------- audio: context
  _ensureCtx() {
    if (!this._ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      this._ctx = new AC();
      this._ctx.onstatechange = () => this._update();
    }
    return this._ctx;
  }

  _unlockAudio() {
    const ctx = this._ensureCtx();
    if (ctx && ctx.state !== "running") ctx.resume().then(() => this._update()).catch(() => {});
  }

  _ensurePlayback() {
    if (this._pb) return this._pb;
    const ctx = this._ensureCtx();
    if (!ctx) return null;
    const mk = (type, f) => {
      const n = ctx.createBiquadFilter();
      n.type = type;
      n.frequency.value = f;
      n.Q.value = 0.707;
      return n;
    };
    const head = ctx.createGain();
    head.gain.value = this._cfg.gain;
    let tail = head;
    const hp = this._cfg.highpass_hz;
    if (hp > 0) {
      // two cascaded 2nd-order stages: 24 dB/oct, removes the 50 Hz mains hum on the line
      const a = mk("highpass", hp);
      const b = mk("highpass", hp);
      tail.connect(a);
      a.connect(b);
      tail = b;
    }
    if (this._cfg.lowpass_hz > 0) {
      const lp = mk("lowpass", this._cfg.lowpass_hz);
      tail.connect(lp);
      tail = lp;
    }
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    tail.connect(analyser);
    analyser.connect(ctx.destination);
    this._pb = { head, analyser, buf: new Float32Array(analyser.fftSize) };
    return this._pb;
  }

  // ---------------------------------------------------------------- audio: line -> speaker
  _onAudioMsg(msg) {
    if (!msg) return;
    if (msg.type === "status") {
      this._linkUp = !!msg.connected;
      if (!this._linkUp && this._mode !== "idle") this._flash(this._cfg.labels.link_down, 3000);
      return;
    }
    if (msg.type !== "audio") return;
    this._lastAudioAt = performance.now();
    const ctx = this._ctx;
    if (!ctx || ctx.state !== "running") return;
    if (this._mode === "talking" || this._talkRequested || this._streaming) return;
    const pb = this._ensurePlayback();
    if (!pb) return;
    const bytes = b64ToBytes(msg.data);
    const n = bytes.length >> 1;
    if (!n) return;
    const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, n);
    const buf = ctx.createBuffer(1, n, TARGET_RATE);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < n; i++) ch[i] = pcm[i] / 32768;
    const now = ctx.currentTime;
    if (this._nextTime < now + 0.02) this._nextTime = now + 0.12; // (re)start with a small jitter buffer
    if (this._nextTime > now + 0.8) return; // too far behind: drop to keep latency low
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(pb.head);
    src.start(this._nextTime);
    this._nextTime += buf.duration;
  }

  async _subscribe() {
    if (this._unsub || this._subscribing || !this._hass) return;
    this._subscribing = true;
    try {
      const unsub = await this._hass.connection.subscribeMessage((m) => this._onAudioMsg(m), {
        type: `${DOMAIN}/subscribe_audio`,
      });
      if (this._mode === "idle" || this._mode === "ringing" || this._mode === "unavailable" || !this.isConnected) unsub();
      else this._unsub = unsub;
    } catch (err) {
      this._flash(`Audio: ${err && err.message ? err.message : err}`);
    } finally {
      this._subscribing = false;
    }
  }

  _unsubscribe() {
    if (this._unsub) {
      const u = this._unsub;
      this._unsub = null;
      try { u(); } catch (_) { /* ignore */ }
    }
    this._linkUp = false;
    this._nextTime = 0;
  }

  // ---------------------------------------------------------------- audio: microphone -> panel
  async _ensureMic() {
    if (this._mic) return this._mic;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error("no getUserMedia");
    const ctx = this._ensureCtx();
    if (!ctx) throw new Error("no AudioContext");
    if (ctx.state !== "running") await ctx.resume();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const source = ctx.createMediaStreamSource(stream);
    const lp = ctx.createBiquadFilter(); // anti-alias before decimating to 16 kHz
    lp.type = "lowpass";
    lp.frequency.value = Math.min(3600, TARGET_RATE / 2 - 400);
    const gain = ctx.createGain();
    gain.gain.value = this._cfg.mic_gain;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(lp);
    lp.connect(gain);
    gain.connect(analyser);
    const mute = ctx.createGain(); // keeps the capture node pulled without playing anything
    mute.gain.value = 0;
    mute.connect(ctx.destination);
    const mic = { stream, source, lp, gain, analyser, mute, buf: new Float32Array(analyser.fftSize), node: null };

    let node = null;
    if (ctx.audioWorklet && window.Blob && URL.createObjectURL) {
      try {
        const url = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: "application/javascript" }));
        await ctx.audioWorklet.addModule(url);
        URL.revokeObjectURL(url);
        node = new AudioWorkletNode(ctx, "resel-capture", { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
        node.port.onmessage = (ev) => this._onCapture(ev.data);
      } catch (_) {
        node = null;
      }
    }
    if (!node) {
      node = ctx.createScriptProcessor(2048, 1, 1);
      node.onaudioprocess = (ev) => this._onCapture(ev.inputBuffer.getChannelData(0));
    }
    gain.connect(node);
    node.connect(mute);
    mic.node = node;
    this._mic = mic;
    return mic;
  }

  _releaseMic() {
    const mic = this._mic;
    if (!mic) return;
    this._mic = null;
    try { mic.stream.getTracks().forEach((t) => t.stop()); } catch (_) { /* ignore */ }
    try { if (mic.node && mic.node.port) mic.node.port.onmessage = null; } catch (_) { /* ignore */ }
    for (const n of [mic.node, mic.source, mic.lp, mic.gain, mic.analyser, mic.mute]) {
      try { if (n) n.disconnect(); } catch (_) { /* ignore */ }
    }
  }

  _onCapture(input) {
    if (!this._streaming || !this._ctx) return;
    const ratio = this._ctx.sampleRate / TARGET_RATE;
    let pos = this._resPos;
    while (pos < input.length - 1) {
      const i = Math.floor(pos);
      const f = pos - i;
      let v = input[i] * (1 - f) + input[i + 1] * f;
      v = v > 1 ? 1 : v < -1 ? -1 : v;
      this._frame[this._frameLen++] = v < 0 ? v * 32768 : v * 32767;
      if (this._frameLen === FRAME_SAMPLES) this._flushFrame();
      pos += ratio;
    }
    this._resPos = Math.max(0, pos - (input.length - 1)); // carry fractional position across chunks
  }

  _flushFrame() {
    const bytes = new Uint8Array(this._frame.buffer.slice(0, this._frameLen * 2));
    this._frameLen = 0;
    if (!this._hass) return;
    this._hass
      .callWS({ type: `${DOMAIN}/send_audio`, data: bytesToB64(bytes) })
      .catch(() => {});
  }

  // ---------------------------------------------------------------- PTT
  async _talkBegin() {
    if (this._talkRequested || this._streaming) return;
    const L = this._cfg.labels;
    const ptt = this._cfg.entities.ptt;
    this._talkRequested = true;
    this._talkStart = Date.now();
    this._update();
    try {
      await this._ensureMic();
    } catch (err) {
      this._talkRequested = false;
      this._flash(L.no_mic);
      this._update();
      return;
    }
    if (!this._talkRequested) return; // released while the permission prompt was open
    this._hass.callService("switch", "turn_on", { entity_id: ptt });
    clearTimeout(this._reqTimer);
    this._reqTimer = setTimeout(() => {
      if (this._talkRequested && !this._streaming) {
        this._talkEnd();
        this._flash(L.ptt_failed);
      }
    }, 3000);
  }

  _talkEnd() {
    if (!this._talkRequested && !this._streaming) return;
    clearTimeout(this._reqTimer);
    this._talkRequested = false;
    this._stopStream();
    if (this._hass) this._hass.callService("switch", "turn_off", { entity_id: this._cfg.entities.ptt });
    if (this._built) this._update();
  }

  _startStream() {
    clearTimeout(this._reqTimer);
    this._frameLen = 0;
    this._resPos = 0;
    this._streaming = true;
    this._talkStart = Date.now();
    this._startLevelTimer();
  }

  _stopStream() {
    if (!this._streaming) return;
    this._streaming = false;
    this._frameLen = 0;
    this._nextTime = 0; // restart playback buffer when listening resumes
  }

  // ---------------------------------------------------------------- level meter
  _startLevelTimer() {
    if (this._levelTimer) return;
    this._levelTimer = setInterval(() => this._tickLevel(), 80);
  }

  _stopLevelTimer() {
    clearInterval(this._levelTimer);
    this._levelTimer = null;
  }

  _rmsDb(analyser, buf) {
    analyser.getFloatTimeDomainData(buf);
    let s = 0;
    for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i];
    const rms = Math.sqrt(s / buf.length);
    return rms > 0 ? Math.max(-90, 20 * Math.log10(rms)) : -90;
  }

  _tickLevel() {
    const L = this._cfg.labels;
    const e = this._el;
    const talking = this._streaming || this._talkRequested;
    let db = -90;
    let name = L.line_level;
    if (talking && this._mic) {
      db = this._rmsDb(this._mic.analyser, this._mic.buf);
      name = L.mic_level;
    } else if (this._pb && this._ctx && this._ctx.state === "running" && performance.now() - this._lastAudioAt < 600) {
      db = this._rmsDb(this._pb.analyser, this._pb.buf);
    } else {
      const s = this._stateObj("level");
      const v = s ? parseFloat(s.state) : NaN;
      if (!Number.isNaN(v)) db = v;
    }
    this._history.push(db);
    this._history.shift();
    this._drawBars();
    e.lvlName.textContent = name;
    e.lvlVal.textContent = db <= -90 ? "—" : `${Math.round(db)} dBFS`;
    if (this._cfg.show_timer && talking && this._streaming && this._cfg.ptt_timeout > 0) {
      const sec = Math.floor((Date.now() - this._talkStart) / 1000);
      const fmt = (x) => `${Math.floor(x / 60)}:${String(x % 60).padStart(2, "0")}`;
      e.timer.textContent = `${fmt(sec)} / ${fmt(this._cfg.ptt_timeout)}`;
    } else {
      e.timer.textContent = "";
    }
  }

  _drawBars() {
    for (let i = 0; i < BARS; i++) {
      const db = this._history[i];
      const h = 4 + Math.round(Math.min(1, Math.max(0, (db + 80) / 60)) * 32);
      this._bars[i].style.height = `${h}px`;
    }
  }
}

if (!customElements.get("resel-intercom-card")) {
  customElements.define("resel-intercom-card", ReselIntercomCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "resel-intercom-card")) {
  window.customCards.push({
    type: "resel-intercom-card",
    name: "Resel Intercom",
    description: "Answer, talk (push-to-talk), open the door and custom buttons for the Resel building intercom.",
    preview: false,
  });
}

})();
