export const LANG_BCP47 = { en: "en-IN", hi: "hi-IN", kn: "kn-IN", ta: "ta-IN" };

export const LANG_LABELS = { en: "English", hi: "Hindi", kn: "Kannada", ta: "Tamil" };

export function isWebSpeechSupported() {
  return typeof window !== "undefined" && Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
}

/** Starts a one-shot Web Speech API recognition session. Returns the
 * recognition instance so the caller can `.stop()`/`.abort()` it (e.g. on
 * mic-button release). Browser support for Kannada/Tamil varies by
 * platform — callers should fall back to `recordAudioBlob` on error. */
export function startWebSpeechRecognition(lang, { onResult, onError, onEnd }) {
  const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new SpeechRecognitionImpl();
  recognition.lang = LANG_BCP47[lang] || "en-IN";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.continuous = false;

  recognition.onresult = (event) => {
    const transcript = event.results[0]?.[0]?.transcript;
    if (transcript) onResult(transcript);
  };
  recognition.onerror = (event) => onError(event.error);
  recognition.onend = () => onEnd?.();

  recognition.start();
  return recognition;
}

export function isSpeechSynthesisSupported() {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** Finds an installed voice matching a language, or null if the OS/browser
 * has none. `speechSynthesis.speak()` silently does nothing when no voice
 * matches the requested lang — it doesn't throw and doesn't fire onerror —
 * so callers must check this first rather than assume speech happened.
 * Windows in particular ships English (and often Hindi) voices but not
 * Kannada or Tamil unless the user installs those language packs. */
export function findVoiceForLang(lang) {
  if (!isSpeechSynthesisSupported()) return null;
  const target = (LANG_BCP47[lang] || "en-IN").toLowerCase();
  const base = target.split("-")[0];
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang.toLowerCase() === target) ||
    voices.find((v) => v.lang.toLowerCase().startsWith(`${base}-`)) ||
    voices.find((v) => v.lang.toLowerCase() === base) ||
    null
  );
}

/** Speaks text with the browser's own voice — used when the backend has no
 * audio to return (ElevenLabs errored, ran out of free-tier credits, or the
 * user muted TTS). There is no server-side TTS fallback by design.
 *
 * Returns a status string rather than a boolean so the caller can tell the
 * user *why* nothing was spoken instead of failing silently:
 *   "speaking"      — an utterance was started
 *   "unsupported"   — this browser has no speechSynthesis at all
 *   "no-voice"      — no installed voice covers this language
 */
export async function speakWithBrowserVoice(text, lang, { onEnd } = {}) {
  if (!isSpeechSynthesisSupported()) return "unsupported";

  // Voices load asynchronously — getVoices() is often empty for the first
  // moments after page load. Without this await we'd wrongly report
  // "no-voice" for a language the browser actually supports.
  await ensureVoicesLoaded();

  const voice = findVoiceForLang(lang);
  if (!voice) return "no-voice";

  window.speechSynthesis.cancel(); // don't let utterances pile up/overlap
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.voice = voice;
  utterance.lang = voice.lang;
  if (onEnd) {
    utterance.onend = onEnd;
    utterance.onerror = onEnd;
  }
  window.speechSynthesis.speak(utterance);
  return "speaking";
}

export function stopBrowserVoice() {
  if (isSpeechSynthesisSupported()) window.speechSynthesis.cancel();
}

/** Voice lists load asynchronously in most browsers — getVoices() is often
 * empty on first call. Resolves once they're populated (or after a timeout). */
export function ensureVoicesLoaded() {
  return new Promise((resolve) => {
    if (!isSpeechSynthesisSupported()) return resolve([]);
    const existing = window.speechSynthesis.getVoices();
    if (existing.length) return resolve(existing);
    const timer = setTimeout(() => resolve(window.speechSynthesis.getVoices()), 2000);
    window.speechSynthesis.onvoiceschanged = () => {
      clearTimeout(timer);
      resolve(window.speechSynthesis.getVoices());
    };
  });
}

/** MediaRecorder-based fallback for browsers/languages the Web Speech API
 * doesn't handle. Records until the caller calls `.stop()` on the returned
 * recorder, then `onStop(blob)` fires with the captured audio. */
export async function recordAudioBlob({ onStop, onError }) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks = [];

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      onStop(blob);
    };

    recorder.start();
    return recorder;
  } catch (err) {
    onError?.(err);
    return null;
  }
}
