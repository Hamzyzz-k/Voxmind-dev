/** The simulator's device-side calls.
 *
 * Everything here deliberately speaks to the backend exactly as the physical
 * glasses would: `Authorization: Device <token>`, a multipart body carrying a
 * JPEG and an audio clip, and a response body of raw PCM. It does not use a
 * softer browser-only path, because the whole point of the simulation is to
 * demonstrate the real pipeline — if this went through /chat/ask instead, the
 * demo would prove nothing about the device.
 *
 * That is also why the browser has to decode PCM by hand below. The endpoint
 * returns headerless 16-bit audio because an ESP32 pushes those bytes
 * straight into an I2S amplifier with no decoding budget. A browser would
 * much prefer an MP3, but changing the endpoint to suit the browser would
 * mean the simulator was no longer exercising the device's contract.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// The device streams 16-bit signed mono at 16kHz. Also stated in the
// X-Sample-Rate response header, which is read back and preferred when
// present, so a future firmware change to 22.05kHz does not silently play
// everything at the wrong pitch.
const DEFAULT_SAMPLE_RATE = 16000;

export class DeviceRequestError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "DeviceRequestError";
    this.status = status;
  }
}

async function readError(response, fallback) {
  try {
    const body = await response.json();
    return body.detail || fallback;
  } catch {
    return fallback;
  }
}

/** Grabs one still from a playing <video> as a JPEG blob.
 *
 * Quality 0.7 at the video's own resolution keeps a frame near the ~15KB the
 * real camera produces, which matters because the backend rejects oversized
 * frames outright (device_runtime.MAX_FRAME_BYTES).
 */
export function captureFrame(video) {
  if (!video || !video.videoWidth) return Promise.resolve(null);
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.7));
}

/** Sends a photo and/or a spoken question, and returns the spoken answer.
 *
 * Mirrors the device contract exactly: silence with a photo is a valid
 * request meaning "describe what is ahead".
 */
export async function deviceAsk({ token, imageBlob, audioBlob, lang = "en", signal }) {
  const form = new FormData();
  form.append("lang", lang);
  if (imageBlob) form.append("image", imageBlob, "frame.jpg");
  if (audioBlob) form.append("audio", audioBlob, "question.webm");

  const response = await fetch(`${BASE_URL}/iot/ask`, {
    method: "POST",
    headers: { Authorization: `Device ${token}` },
    body: form,
    signal,
  });

  if (!response.ok) {
    throw new DeviceRequestError(
      await readError(response, `Device request failed (${response.status})`),
      response.status,
    );
  }

  // Percent-encoded on the way out, because HTTP headers are latin-1 and
  // these carry Hindi, Kannada and Tamil.
  const decodeHeader = (name) => {
    const raw = response.headers.get(name);
    if (!raw) return "";
    try {
      return decodeURIComponent(raw);
    } catch {
      return raw;
    }
  };

  return {
    pcm: await response.arrayBuffer(),
    replyText: decodeHeader("X-Reply-Text"),
    transcript: decodeHeader("X-Transcript"),
    voice: response.headers.get("X-Voice") || "unknown",
    sampleRate: Number(response.headers.get("X-Sample-Rate")) || DEFAULT_SAMPLE_RATE,
  };
}

/** Uploads a frame the way the glasses do, which also counts as a heartbeat.
 *
 * Only used to make the device show as online in the devices panel while the
 * simulation runs — the ask path sends its own photo and does not depend on
 * this.
 */
export async function pushFrame(token, blob, { signal } = {}) {
  const response = await fetch(`${BASE_URL}/iot/camera/frame`, {
    method: "POST",
    headers: { Authorization: `Device ${token}`, "Content-Type": "image/jpeg" },
    body: blob,
    signal,
  });
  if (!response.ok && response.status !== 204) {
    throw new DeviceRequestError(
      await readError(response, `Frame upload failed (${response.status})`),
      response.status,
    );
  }
}

/** Turns the endpoint's headerless PCM into something the Web Audio API can
 * play. `decodeAudioData` cannot be used here — it expects a container it can
 * sniff (WAV, MP3, OGG) and these bytes have no header at all, so the sample
 * rate and format have to be supplied by us. */
export function pcmToAudioBuffer(audioContext, pcm, sampleRate) {
  const samples = new Int16Array(pcm);
  const buffer = audioContext.createBuffer(1, samples.length, sampleRate);
  const channel = buffer.getChannelData(0);
  // Signed 16-bit maps to [-1, 1) by dividing by 32768, not 32767: the
  // negative range genuinely reaches -32768, and dividing by 32767 would
  // clip that one sample past -1.
  for (let i = 0; i < samples.length; i += 1) {
    channel[i] = samples[i] / 32768;
  }
  return buffer;
}
