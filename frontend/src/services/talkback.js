/** TalkBack — an in-app screen reader for VoxMind, independent of whatever
 * assistive tech (or none) the visitor already has running.
 *
 * A blind visitor may already run NVDA, JAWS or VoiceOver — but plenty won't:
 * a shared library computer, a machine they don't control, a first-time
 * visitor who's never set one up. This works the same for everyone regardless
 * of what's already installed, and it never activates unless explicitly
 * turned on, so it can never surprise someone who already has their own
 * screen reader running.
 *
 * Behaviour, once enabled:
 *   - Touching (clicking/tapping) an action element speaks its label and
 *     "arms" it. The touch is swallowed — nothing actually happens yet.
 *   - Touching that *same* element again within the confirm window lets the
 *     action through for real. Touching a *different* element re-arms on the
 *     new one and drops the old arming.
 *   - Alt+A toggles TalkBack on/off from anywhere, confirmed with a short
 *     spoken cue, and the preference survives reloads.
 *
 * Deliberately a plain module bootstrapped once from main.jsx, not a React
 * effect. This codebase has already hit two separate StrictMode
 * mount->cleanup->mount bugs (OptionWheel, CameraView) from state that lived
 * where a second effect invocation could see and corrupt it. A capture-phase
 * document listener has nothing for that to bite — it isn't tied to any
 * component's lifecycle at all.
 *
 * Scope, stated plainly: only elements whose primary interaction is
 * "click to perform an action" get the touch-then-confirm treatment — button,
 * link, submit/checkbox/radio input, [role="button"], select. Free-text
 * inputs and textareas are exempt on purpose; requiring a second touch just
 * to focus a field would make typing impossible, and confirmation exists to
 * guard against accidentally *triggering* something, not against focusing
 * somewhere to type. OptionWheel's history items (role="option", not
 * "button") are also out of scope — that component already has its own
 * fragile custom click handling (see HistoryPanel.jsx), and layering a second
 * interception on top of it risked fighting it rather than complementing it.
 */

import { ensureVoicesLoaded, findVoiceForLang, isSpeechSynthesisSupported, stopBrowserVoice } from "./speech";

const STORAGE_KEY = "voxmind_talkback_enabled";
const SESSION_HINT_KEY = "voxmind_talkback_hint_shown";
const CONFIRM_WINDOW_MS = 3000;
const TOGGLE_KEY = "a"; // Alt+A

// Fired on every state change, from either the keyboard shortcut or the
// visible toggle button (TalkBackToggle.jsx). This module deliberately holds
// its own state in a closure variable rather than React state — see the file
// docstring — so a DOM event, not a shared store, is what lets a React
// component outside this module stay in sync with a change made from the
// *other* entry point (Alt+A while the button is on screen, or the button
// while a keyboard user has already turned it on).
export const TALKBACK_CHANGE_EVENT = "voxmind-talkback-change";

const INTERACTIVE_SELECTOR =
  'button, a[href], [role="button"], input[type="submit"], input[type="button"], ' +
  'input[type="checkbox"], input[type="radio"], select';

// `?talkbackdebug=1` mirrors every announcement into a DOM element instead of
// (or alongside) speaking it, and exposes state on `window.__talkback` — this
// project's development environment has no audio hardware, so there is no
// other way to confirm this actually works short of a human listening. Same
// pattern as speech.js's `?micdebug=1`.
const DEBUG =
  typeof window !== "undefined" && new URLSearchParams(window.location.search).has("talkbackdebug");

let enabled = false;
let armedEl = null;
let armedAt = 0;
let initialized = false;
let liveRegion = null;

function readStoredPreference() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false; // storage blocked (private browsing, etc.) — default off
  }
}

function storePreference(value) {
  try {
    localStorage.setItem(STORAGE_KEY, value ? "1" : "0");
  } catch {
    // Nothing to do — the session still works, it just won't remember.
  }
}

/** A visually-hidden `aria-live` region that mirrors every announcement as
 * text. Two independent reasons to have it, not one:
 *   1. If speechSynthesis has no voice for the active language (the existing
 *      Kannada/Tamil gap on Windows — see speech.js), a real screen reader
 *      the user already has running still picks up the text change.
 *   2. It's how this feature can be verified at all from a development
 *      environment with no speakers.
 */
function ensureLiveRegion() {
  if (liveRegion) return liveRegion;
  liveRegion = document.createElement("div");
  liveRegion.setAttribute("aria-live", "assertive");
  liveRegion.setAttribute("role", "status");
  liveRegion.id = "talkback-live-region";
  Object.assign(liveRegion.style, {
    position: "absolute",
    width: "1px",
    height: "1px",
    padding: "0",
    margin: "-1px",
    overflow: "hidden",
    clip: "rect(0, 0, 0, 0)",
    whiteSpace: "nowrap",
    border: "0",
  });
  document.body.appendChild(liveRegion);
  return liveRegion;
}

async function speak(text) {
  window.__talkback = { ...(window.__talkback || {}), lastSpoken: text, enabled };

  const region = ensureLiveRegion();
  // Cleared first: some screen readers only announce an aria-live region on
  // an actual text *change*, so setting the same string twice in a row (e.g.
  // re-touching the same button after it timed out) would otherwise go
  // silent the second time.
  region.textContent = "";
  region.textContent = text;

  if (DEBUG) console.log("[talkback]", text);
  if (!isSpeechSynthesisSupported()) return;

  stopBrowserVoice(); // don't let announcements stack up over each other
  await ensureVoicesLoaded();
  const utterance = new SpeechSynthesisUtterance(text);
  const voice = findVoiceForLang("en");
  if (voice) utterance.voice = voice;
  window.speechSynthesis.speak(utterance);
}

function getAccessibleLabel(el) {
  const ariaLabel = el.getAttribute("aria-label");
  if (ariaLabel?.trim()) return ariaLabel.trim();

  const labelledBy = el.getAttribute("aria-labelledby");
  if (labelledBy) {
    const text = labelledBy
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent?.trim())
      .filter(Boolean)
      .join(" ");
    if (text) return text;
  }

  const title = el.getAttribute("title");
  if (title?.trim()) return title.trim();

  const imgAlt = el.querySelector("img[alt]")?.getAttribute("alt");
  if (imgAlt?.trim()) return imgAlt.trim();

  const text = el.textContent?.replace(/\s+/g, " ").trim();
  if (text) return text;

  return el.tagName === "A" ? "link" : "button";
}

function handleClickCapture(event) {
  if (!enabled) return;

  const target = event.target.closest?.(INTERACTIVE_SELECTOR);
  if (!target) return; // not an action element — let it behave normally

  const now = Date.now();
  if (armedEl === target && now - armedAt < CONFIRM_WINDOW_MS) {
    // Second touch on the same element within the window — let it through.
    armedEl = null;
    return;
  }

  // First touch (or a different element, or the window lapsed): intercept,
  // announce, arm. Capture phase + both of these together is what makes the
  // interception total — nothing downstream, including the element's own
  // onClick, ever sees this event.
  event.preventDefault();
  event.stopPropagation();
  armedEl = target;
  armedAt = now;
  speak(getAccessibleLabel(target));
}

function handleKeyDown(event) {
  if (event.altKey && event.key.toLowerCase() === TOGGLE_KEY) {
    event.preventDefault();
    setEnabled(!enabled);
  }
}

function setEnabled(next) {
  enabled = next;
  armedEl = null;
  storePreference(enabled);
  window.__talkback = { ...(window.__talkback || {}), enabled };
  speak(enabled ? "Talk Back on." : "Talk Back off.");
  window.dispatchEvent(new CustomEvent(TALKBACK_CHANGE_EVENT, { detail: { enabled } }));
}

/** Reads current state without subscribing to it. Safe to call before
 * `initTalkBack()` runs (e.g. a component mounted above it in the tree) — the
 * stored preference is read directly rather than trusting the module's
 * possibly-not-yet-initialized `enabled` variable, so the toggle button never
 * flashes the wrong initial state on first paint. */
export function isTalkBackEnabled() {
  return initialized ? enabled : readStoredPreference();
}

/** The visible toggle button's click handler. Routed through the same
 * `setEnabled` as Alt+A rather than duplicating its side effects (storage,
 * the spoken confirmation, the change event) in a second place. */
export function toggleTalkBack() {
  setEnabled(!isTalkBackEnabled());
}

/** Runs once per browser tab, not once per route. A blind visitor cannot
 * discover a feature whose only entry point is a button they can't yet find
 * — so the shortcut is announced automatically, but only the first time in
 * this session, never on every internal page change (Auth -> OTP ->
 * Entering -> Home would otherwise repeat it four times in under a minute).
 * If TalkBack is already on from a previous session, there's no need to
 * explain how to turn it on — just confirm it's already on. */
function announceOnLoad() {
  let alreadyShown = false;
  try {
    alreadyShown = sessionStorage.getItem(SESSION_HINT_KEY) === "1";
  } catch {
    // storage blocked — fall through and announce once for this call
  }
  if (alreadyShown) return;

  try {
    sessionStorage.setItem(SESSION_HINT_KEY, "1");
  } catch {
    // Can't persist the flag, but still only announce this one time — the
    // in-memory `alreadyShown` check above already prevented same-tick reruns.
  }

  if (enabled) {
    speak("Talk Back on.");
  } else {
    speak("VoxMind. Press Alt A to turn on Talk Back.");
  }
}

export function initTalkBack() {
  if (initialized) return; // safe no-op if ever called more than once
  initialized = true;

  enabled = readStoredPreference();
  window.__talkback = { enabled, lastSpoken: null };

  document.addEventListener("click", handleClickCapture, { capture: true });
  window.addEventListener("keydown", handleKeyDown);

  announceOnLoad();
}
