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

/** Speaks text with the browser's own voice — used when the backend has no
 * audio to return (ElevenLabs errored or its free-tier credits ran out).
 * There is no server-side TTS fallback by design; this is the only one.
 * Returns true if speech was actually kicked off, false if the browser
 * doesn't support speechSynthesis at all. */
export function speakWithBrowserVoice(text, lang) {
  if (!isSpeechSynthesisSupported()) return false;
  window.speechSynthesis.cancel(); // don't let utterances pile up/overlap
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = LANG_BCP47[lang] || "en-IN";
  window.speechSynthesis.speak(utterance);
  return true;
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
