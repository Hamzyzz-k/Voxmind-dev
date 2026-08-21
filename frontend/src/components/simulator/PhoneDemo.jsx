import { useCallback, useEffect, useRef, useState } from "react";
import {
  DeviceRequestError,
  captureFrame,
  deviceAsk,
  pcmToAudioBuffer,
  pushFrame,
} from "../../services/simulatorDevice";

/** How often the simulated device uploads a frame.
 *
 * Two frames a second, which is roughly what the real ESP32's WiFi sustains
 * and well inside the 600/minute device rate limit. Without this the device
 * only ever transmits when the ask button is pressed, so it never registers
 * as alive and the devices panel shows it permanently offline — which looks
 * exactly like a broken device rather than an idle one.
 */
const STREAM_INTERVAL_MS = 500;

/** Distance below which the obstacle warning fires, in centimetres. Matches
 * the ~1m threshold in the design (tasks/phase2-plan.md §4). */
const WARN_CM = 100;
const MIN_CM = 20;
const MAX_CM = 300;

/** A press shorter than this counts as "just describe what is ahead" rather
 * than a spoken question. Below roughly this length a recording is a click
 * and a breath, and sending it to speech-to-text produces a confident
 * transcription of nothing. */
const MIN_SPEECH_MS = 400;

/** Buzz cadence at the threshold and when almost touching an obstacle. A
 * fixed-rate buzz tells the wearer something is there; a quickening one tells
 * them whether they are walking into it or away from it, which is the part
 * that actually helps. */
const SLOW_PULSE_MS = 620;
const FAST_PULSE_MS = 110;

function pulseIntervalFor(distanceCm) {
  const t = Math.min(1, Math.max(0, (WARN_CM - distanceCm) / (WARN_CM - MIN_CM)));
  return SLOW_PULSE_MS + (FAST_PULSE_MS - SLOW_PULSE_MS) * t;
}

/** The wearable, simulated on a phone-shaped screen.
 *
 * The camera and microphone are real; the distance sensor is not. There is no
 * VL53L0X in a laptop and nothing in a webcam image can honestly stand in for
 * a time-of-flight range reading, so the distance is driven by a control the
 * presenter moves, and is labelled as simulated everywhere it appears. The
 * alternative — guessing at depth from image size and calling it a sensor —
 * would be a nicer demo and a dishonest one, and it is exactly the sort of
 * claim that falls apart under questioning at a viva.
 *
 * Everything else is real: the frame is a real JPEG from a real camera, the
 * question is real recorded audio, and the answer comes back from the same
 * /iot/ask endpoint the hardware calls, as raw PCM.
 */
export default function PhoneDemo({ deviceToken, lang = "en" }) {
  const videoRef = useRef(null);

  const [cameraState, setCameraState] = useState("idle"); // idle | starting | live | denied | error
  const [distance, setDistance] = useState(220);
  const [autoSweep, setAutoSweep] = useState(false);
  const [warning, setWarning] = useState(false);
  const [recording, setRecording] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");
  const [voice, setVoice] = useState("");
  const [error, setError] = useState("");

  // Long-lived browser resources, deliberately not state: changing them must
  // never trigger a re-render, and they have to survive one.
  const streamRef = useRef(null);
  const audioContextRef = useRef(null);
  const recorderRef = useRef(null);
  const speakingSourceRef = useRef(null);

  // Read by the buzz loop every pulse. In a ref rather than a dependency so
  // moving the slider retunes the existing loop instead of tearing it down
  // and restarting it on every pixel of drag.
  const distanceRef = useRef(distance);
  distanceRef.current = distance;

  const ensureAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    // Browsers start contexts suspended until a user gesture; every entry
    // point here is inside one, so this is always allowed to resume.
    if (audioContextRef.current.state === "suspended") audioContextRef.current.resume();
    return audioContextRef.current;
  }, []);

  const startCamera = useCallback(async () => {
    setCameraState("starting");
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 } },
        audio: true,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      ensureAudioContext();
      setCameraState("live");
    } catch (err) {
      // A denied permission is a different problem from a missing camera, and
      // the fix is different too, so they must not collapse into one message.
      setCameraState(err.name === "NotAllowedError" ? "denied" : "error");
      setError(err.name === "NotAllowedError" ? "" : err.message || "Could not open the camera.");
    }
  }, [ensureAudioContext]);

  // Tear the camera and microphone down when the demo unmounts. Without this
  // the recording indicator stays lit in the browser tab after navigating
  // away, which looks exactly like spyware to anyone watching.
  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      speakingSourceRef.current?.stop();
      audioContextRef.current?.close();
      audioContextRef.current = null;
    };
  }, []);

  // --- Frame streaming --------------------------------------------------
  // Uploads frames the way the firmware will, which doubles as the device's
  // heartbeat. All loop state is closure-local rather than refs, for the same
  // StrictMode reason documented at length in CameraView.jsx: a second mount's
  // fresh `cancelled = false` would otherwise un-cancel the first mount's
  // dying loop, leaving two uploaders running against one rate limit.
  useEffect(() => {
    if (cameraState !== "live") return undefined;

    let cancelled = false;
    let timerId = null;
    let consecutiveFailures = 0;
    const controller = new AbortController();

    async function tick() {
      if (cancelled) return;
      // A backgrounded tab has nothing worth transmitting, and the frames
      // would burn Render hours nobody is watching.
      if (!document.hidden) {
        try {
          const blob = await captureFrame(videoRef.current);
          if (blob && !cancelled) {
            await pushFrame(deviceToken, blob, { signal: controller.signal });
            consecutiveFailures = 0;
            if (!cancelled) setStreaming(true);
          }
        } catch (err) {
          if (err.name !== "AbortError") {
            consecutiveFailures += 1;
            // One dropped frame is normal on a slow connection and not worth
            // reporting. A sustained failure means something real is wrong,
            // and silently pretending to stream would be worse than saying so.
            if (consecutiveFailures >= 4 && !cancelled) setStreaming(false);
          }
        }
      }
      if (!cancelled) timerId = setTimeout(tick, STREAM_INTERVAL_MS);
    }
    tick();

    return () => {
      cancelled = true;
      controller.abort();
      if (timerId) clearTimeout(timerId);
    };
  }, [cameraState, deviceToken]);

  // --- Simulated distance sweep ---------------------------------------
  useEffect(() => {
    if (!autoSweep) return undefined;
    let frameId = null;
    const startedAt = performance.now();

    function step(now) {
      // A slow triangle between far and near, so the demo walks toward an
      // obstacle and away again without anyone touching the slider.
      const period = 9000;
      const phase = ((now - startedAt) % period) / period;
      const triangle = phase < 0.5 ? phase * 2 : (1 - phase) * 2;
      setDistance(Math.round(MAX_CM - triangle * (MAX_CM - MIN_CM)));
      frameId = requestAnimationFrame(step);
    }
    frameId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frameId);
  }, [autoSweep]);

  // --- Obstacle warning -------------------------------------------------
  // This loop is the whole point of the two-layer design: it never calls the
  // network, never waits for a model, and keeps running while a cloud request
  // is in flight. It is the layer that still works when the internet does not.
  useEffect(() => {
    if (cameraState !== "live") return undefined;

    let cancelled = false;
    let timerId = null;

    function buzz() {
      if (cancelled) return;
      const cm = distanceRef.current;
      if (cm >= WARN_CM) {
        setWarning(false);
        timerId = setTimeout(buzz, 120);
        return;
      }
      setWarning(true);

      const context = audioContextRef.current;
      if (context && context.state === "running") {
        // A low, short, square-ish pulse — closer to a motor against the
        // temple than to an alarm. On the real device this is felt, not
        // heard; a laptop has no vibration motor, so it is rendered as the
        // sound that motor would make.
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.type = "square";
        oscillator.frequency.value = 62;
        // Quieter while the assistant is talking, so the spoken answer stays
        // intelligible. The warning is never silenced outright: suppressing a
        // collision alert to finish a sentence is the wrong trade.
        const peak = speakingSourceRef.current ? 0.05 : 0.16;
        gain.gain.setValueAtTime(0.0001, context.currentTime);
        gain.gain.exponentialRampToValueAtTime(peak, context.currentTime + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.07);
        oscillator.connect(gain).connect(context.destination);
        oscillator.start();
        oscillator.stop(context.currentTime + 0.08);
      }
      if (navigator.vibrate) navigator.vibrate(35);

      timerId = setTimeout(buzz, pulseIntervalFor(cm));
    }
    buzz();

    return () => {
      cancelled = true;
      if (timerId) clearTimeout(timerId);
      setWarning(false);
    };
  }, [cameraState]);

  // --- Ask ---------------------------------------------------------------
  const playReply = useCallback(
    (pcm, sampleRate) => {
      const context = ensureAudioContext();
      speakingSourceRef.current?.stop();
      const source = context.createBufferSource();
      source.buffer = pcmToAudioBuffer(context, pcm, sampleRate);
      source.connect(context.destination);
      source.onended = () => {
        if (speakingSourceRef.current === source) speakingSourceRef.current = null;
      };
      speakingSourceRef.current = source;
      source.start();
    },
    [ensureAudioContext],
  );

  const send = useCallback(
    async (audioBlob) => {
      setBusy(true);
      setError("");
      setTranscript("");
      setReply("");
      try {
        const imageBlob = await captureFrame(videoRef.current);
        const result = await deviceAsk({ token: deviceToken, imageBlob, audioBlob, lang });
        setTranscript(result.transcript);
        setReply(result.replyText);
        setVoice(result.voice);
        playReply(result.pcm, result.sampleRate);
      } catch (err) {
        setError(
          err instanceof DeviceRequestError ? err.message : err.message || "Something went wrong.",
        );
      } finally {
        setBusy(false);
      }
    },
    [deviceToken, lang, playReply],
  );

  const startRecording = useCallback(() => {
    if (busy || cameraState !== "live" || !streamRef.current) return;
    const audioTracks = streamRef.current.getAudioTracks();
    if (audioTracks.length === 0) return;

    ensureAudioContext();
    const chunks = [];
    const recorder = new MediaRecorder(new MediaStream(audioTracks));
    const startedAt = performance.now();

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = () => {
      const heldMs = performance.now() - startedAt;
      // A tap means "describe what is ahead" — the device treats silence with
      // a photo as a valid request, so no audio is sent at all rather than a
      // fragment of room tone for the transcriber to hallucinate over.
      const spoke = heldMs >= MIN_SPEECH_MS && chunks.length > 0;
      send(spoke ? new Blob(chunks, { type: "audio/webm" }) : null);
    };

    recorderRef.current = recorder;
    recorder.start();
    setRecording(true);
  }, [busy, cameraState, ensureAudioContext, send]);

  const stopRecording = useCallback(() => {
    setRecording(false);
    const recorder = recorderRef.current;
    recorderRef.current = null;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }, []);

  const proximity = Math.min(1, Math.max(0, (WARN_CM - distance) / (WARN_CM - MIN_CM)));

  return (
    <div className="phone-demo">
      <div className={`phone-chassis${warning ? " phone-chassis--warning" : ""}`}>
        <div className="phone-notch" />
        <div className="phone-screen">
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video ref={videoRef} className="phone-video" playsInline muted />

          {cameraState !== "live" && (
            <div className="phone-overlay">
              {cameraState === "idle" && (
                <>
                  <p className="phone-overlay__title">Glasses camera</p>
                  <p className="phone-overlay__body">
                    The webcam stands in for the camera on the frame. Nothing is recorded or
                    uploaded until the ask button is pressed.
                  </p>
                  <button type="button" className="sim-button sim-button--primary" onClick={startCamera}>
                    Start the glasses
                  </button>
                </>
              )}
              {cameraState === "starting" && <p className="phone-overlay__body">Opening camera…</p>}
              {cameraState === "denied" && (
                <>
                  <p className="phone-overlay__title">Camera and microphone blocked</p>
                  <p className="phone-overlay__body">
                    Allow both in the browser's address bar, then start again. The demo needs the
                    camera to see and the microphone to hear the question.
                  </p>
                  <button type="button" className="sim-button" onClick={startCamera}>
                    Try again
                  </button>
                </>
              )}
              {cameraState === "error" && (
                <>
                  <p className="phone-overlay__title">Could not open the camera</p>
                  <p className="phone-overlay__body">{error}</p>
                  <button type="button" className="sim-button" onClick={startCamera}>
                    Try again
                  </button>
                </>
              )}
            </div>
          )}

          {cameraState === "live" && (
            <div className={`phone-live${streaming ? " is-online" : ""}`}>
              <span className="phone-live__dot" />
              {streaming ? "Device online · streaming" : "Connecting…"}
            </div>
          )}

          {warning && (
            <div className="phone-warning" role="status">
              <span className="phone-warning__dot" />
              Obstacle {distance}cm — buzzing
            </div>
          )}

          {(transcript || reply || busy) && (
            <div className="phone-captions">
              {transcript && <p className="phone-captions__asked">“{transcript}”</p>}
              {busy && <p className="phone-captions__status">Looking…</p>}
              {reply && <p className="phone-captions__reply">{reply}</p>}
              {reply && voice && <p className="phone-captions__meta">spoken via {voice}</p>}
            </div>
          )}
        </div>

        <button
          type="button"
          className={`phone-ask${recording ? " phone-ask--recording" : ""}`}
          disabled={cameraState !== "live" || busy}
          onPointerDown={startRecording}
          onPointerUp={stopRecording}
          onPointerLeave={stopRecording}
          onPointerCancel={stopRecording}
        >
          {busy ? "Thinking…" : recording ? "Listening… release to send" : "Hold to ask"}
        </button>
      </div>

      <div className="sim-controls">
        <h3 className="sim-controls__title">Simulated VL53L0X distance sensor</h3>
        <p className="sim-controls__note">
          A laptop has no time-of-flight sensor, so this reading is driven by hand. Everything
          else in this demo — the image, the question, the answer, the voice — is real.
        </p>

        <label className="sim-slider">
          <span className="sim-slider__label">
            Obstacle distance
            <strong className={distance < WARN_CM ? "is-warning" : ""}>{distance} cm</strong>
          </span>
          <input
            type="range"
            min={MIN_CM}
            max={MAX_CM}
            value={distance}
            disabled={autoSweep}
            onChange={(event) => setDistance(Number(event.target.value))}
          />
          <span className="sim-slider__scale">
            <span>{MIN_CM}cm</span>
            <span>warn under {WARN_CM}cm</span>
            <span>{MAX_CM}cm</span>
          </span>
        </label>

        <label className="sim-check">
          <input
            type="checkbox"
            checked={autoSweep}
            onChange={(event) => setAutoSweep(event.target.checked)}
          />
          Walk toward an obstacle automatically
        </label>

        <div className="sim-meter" aria-hidden="true">
          <div
            className={`sim-meter__fill${distance < WARN_CM ? " is-warning" : ""}`}
            style={{ width: `${proximity * 100}%` }}
          />
        </div>

        {error && cameraState === "live" && <p className="sim-error">{error}</p>}

        <ol className="sim-steps">
          <li>Press <strong>Start the glasses</strong> and allow the camera and microphone.</li>
          <li>Drag the distance below 100cm — the buzz starts and quickens as it closes in.</li>
          <li>Hold the ask button and say “what is in front of me?”, then release.</li>
          <li>Tap the button without speaking to just get a description of the scene.</li>
        </ol>
      </div>
    </div>
  );
}
