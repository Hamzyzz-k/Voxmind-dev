export const LANG_BCP47 = { en: "en-IN", hi: "hi-IN", kn: "kn-IN", ta: "ta-IN" };

export const LANG_LABELS = { en: "English", hi: "Hindi", kn: "Kannada", ta: "Tamil" };

export function isWebSpeechSupported() {
  return typeof window !== "undefined" && Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
}

/** Recognition errors that mean Web Speech genuinely cannot run here, so it's
 * worth switching to the record-and-upload fallback. Everything else
 * ("no-speech", "aborted", "network") is a normal outcome of a single attempt —
 * falling back on those just starts a recorder the user isn't holding any more,
 * which captures nothing and looks like the mic is dead. */
const FATAL_RECOGNITION_ERRORS = new Set(["not-allowed", "service-not-allowed", "audio-capture"]);

export function isFatalRecognitionError(error) {
  return FATAL_RECOGNITION_ERRORS.has(error);
}

/** Human-readable explanation for a recognition error. */
export function describeRecognitionError(error) {
  switch (error) {
    case "no-speech":
      return "Didn't catch that — hold the mic and speak clearly.";
    case "audio-capture":
      return "No microphone found.";
    case "not-allowed":
    case "service-not-allowed":
      return "Microphone access is blocked. Allow it in your browser's address bar.";
    case "network":
      return "Speech recognition needs a network connection.";
    case "aborted":
      return "Hold the mic and speak.";
    default:
      return "Couldn't understand that. Please try again.";
  }
}

/** Starts a one-shot Web Speech API recognition session. Returns the
 * recognition instance so the caller can `.stop()`/`.abort()` it (e.g. on
 * mic-button release), or null if it couldn't start at all.
 * Browser support for Kannada/Tamil varies by platform. */
export function startWebSpeechRecognition(lang, { onResult, onError, onEnd }) {
  const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new SpeechRecognitionImpl();
  recognition.lang = LANG_BCP47[lang] || "en-IN";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.continuous = false;

  let gotResult = false;
  recognition.onresult = (event) => {
    const transcript = event.results[0]?.[0]?.transcript;
    if (transcript) {
      gotResult = true;
      onResult(transcript);
    }
  };
  recognition.onerror = (event) => onError?.(event.error);
  recognition.onend = () => onEnd?.(gotResult);

  try {
    recognition.start();
  } catch (err) {
    // start() throws InvalidStateError if a previous session is still winding
    // down. Report it rather than leaving the UI stuck on "Listening…".
    onError?.(err?.name === "InvalidStateError" ? "aborted" : "unknown");
    return null;
  }
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
    // MediaRecorder.stream is not implemented everywhere; attach it explicitly
    // so callers can route it into the audio analyser.
    if (!recorder.stream) recorder.stream = stream;
    return recorder;
  } catch (err) {
    onError?.(err);
    return null;
  }
}
