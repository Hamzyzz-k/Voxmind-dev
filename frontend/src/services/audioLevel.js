/** Live audio level (0–1) for driving MagicRings.
 *
 * MagicRings animates on its own clock and has no audio input, so the rings are
 * fed a level read from a Web Audio AnalyserNode every frame. Two sources feed
 * it, one at a time:
 *   - the microphone, while the user is holding the mic button
 *   - the TTS playback element, while the assistant's reply is speaking
 *
 * A single AudioContext and Analyser are created lazily and reused; browsers cap
 * how many contexts a page may open, and creating one per utterance leaks them.
 */

let ctx = null;
let analyser = null;
let data = null;
let currentSource = null;

// An <audio> element can only ever be routed through createMediaElementSource
// once — a second call on the same element throws. Cache by element.
const elementSources = new WeakMap();

function getContext() {
  if (!ctx) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return null;
    ctx = new AudioCtx();
  }
  return ctx;
}

function getAnalyser() {
  const audioCtx = getContext();
  if (!audioCtx) return null;
  if (!analyser) {
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.75; // rings should glide, not jitter
    data = new Uint8Array(analyser.frequencyBinCount);
  }
  return analyser;
}

function disconnectSource() {
  if (currentSource) {
    try {
      currentSource.disconnect();
    } catch {
      // already torn down
    }
    currentSource = null;
  }
}

/** Routes the microphone stream into the analyser. */
export function connectStream(stream) {
  const audioCtx = getContext();
  const node = getAnalyser();
  if (!audioCtx || !node || !stream) return false;

  disconnectSource();
  currentSource = audioCtx.createMediaStreamSource(stream);
  currentSource.connect(node);
  // Deliberately NOT connected to destination — routing the mic to the speakers
  // would echo the user back to themselves.
  if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
  return true;
}

/** Routes a playing <audio> element into the analyser. */
export function connectAudioElement(el) {
  const audioCtx = getContext();
  const node = getAnalyser();
  if (!audioCtx || !node || !el) return false;

  disconnectSource();
  let source = elementSources.get(el);
  if (!source) {
    try {
      source = audioCtx.createMediaElementSource(el);
      elementSources.set(el, source);
    } catch {
      return false;
    }
  }
  source.connect(node);
  // Unlike the mic, this must also reach the speakers: once an element is
  // routed through Web Audio, its own output is muted unless reconnected.
  node.connect(audioCtx.destination);
  currentSource = source;
  if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
  return true;
}

export function disconnectAudio() {
  disconnectSource();
  if (analyser) {
    try {
      analyser.disconnect();
    } catch {
      // already disconnected
    }
  }
}

/** Current level, 0–1. Returns 0 when nothing is connected. */
export function readLevel() {
  if (!analyser || !data || !currentSource) return 0;
  analyser.getByteFrequencyData(data);

  let sum = 0;
  for (let i = 0; i < data.length; i++) sum += data[i];
  const mean = sum / data.length / 255;

  // Speech sits low in a linear 0–1 range, so lift it into a range that
  // produces visible ring movement without clipping at loud moments.
  return Math.min(1, mean * 2.2);
}
