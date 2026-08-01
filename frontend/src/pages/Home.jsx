import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ChatTranscript from "../components/ChatTranscript";
import HistoryPanel from "../components/HistoryPanel";
import MicButton from "../components/MicButton";
import StopMuteButton from "../components/StopMuteButton";
import TextComposer from "../components/TextComposer";
import ToneToggle from "../components/ToneToggle";
import { useAuth } from "../context/AuthContext";
import { useAudioLevel } from "../hooks/useAudioLevel";
import { LazyGridScan, LazyMagicRings } from "../components/LazyVisuals";
import ClickSpark from "../reactbits/ClickSpark";
import ElasticSlider from "../reactbits/ElasticSlider";
import { api } from "../services/api";
import {
  connectAudioElement,
  connectStream,
  disconnectAudio,
  setOutputVolume,
} from "../services/audioLevel";
import {
  LANG_LABELS,
  describeRecognitionError,
  ensureVoicesLoaded,
  findVoiceForLang,
  isFatalRecognitionError,
  isWebSpeechSupported,
  recordAudioBlob,
  speakWithBrowserVoice,
  startWebSpeechRecognition,
  stopBrowserVoice,
} from "../services/speech";

// How much one spoken "louder"/"quieter" moves the slider. A multiple of the
// slider's own step size, so voice and drag land on the same values.
const VOLUME_STEP = 15;

export default function Home() {
  const { logout } = useAuth();
  const [lang, setLang] = useState("en");
  const [tone, setTone] = useState(null); // null until loaded, so the toggle mounts with the right index
  const [messages, setMessages] = useState([]);
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolume] = useState(70);
  const [status, setStatus] = useState("Tap the mic to talk — or hold it while you speak.");

  const recognitionRef = useRef(null);
  const recorderRef = useRef(null);
  const modeRef = useRef(null);
  const audioRef = useRef(null);
  const isMutedRef = useRef(false);
  const volumeRef = useRef(70);
  // Whether reply audio is currently routed through the Web Audio graph. When
  // it is, the GainNode owns volume; setting the element's own `volume` as well
  // would attenuate twice.
  const graphConnectedRef = useRef(false);
  const pressActiveRef = useRef(false);
  const pressStartedAtRef = useRef(0);
  const latchedRef = useRef(false);
  const abortRef = useRef(null);

  // Rings are audio-reactive only while the mic is live or the reply is
  // speaking; idle the rest of the time.
  const audioActive = isRecording || isSpeaking;
  const level = useAudioLevel(audioActive);

  useEffect(() => {
    isMutedRef.current = isMuted;
  }, [isMuted]);

  /** Single point of truth for playback volume: the slider, voice commands and
   * anything else all go through here so the UI and the audio can't disagree.
   * Takes effect mid-utterance, not just on the next reply. */
  const applyVolume = useCallback((next) => {
    const clamped = Math.min(100, Math.max(0, Math.round(next)));
    volumeRef.current = clamped;
    setVolume(clamped);
    setOutputVolume(clamped / 100);
    if (!graphConnectedRef.current && audioRef.current) {
      audioRef.current.volume = clamped / 100;
    }
    return clamped;
  }, []);

  // Seed the audio graph with the initial value.
  useEffect(() => {
    setOutputVolume(volumeRef.current / 100);
  }, []);

  const refreshThreads = useCallback(async () => {
    const res = await api.get("/chat/threads");
    setThreads(res.threads);
    return res.threads;
  }, []);

  const openThread = useCallback(async (threadId) => {
    const res = await api.get(`/chat/threads/${threadId}`);
    setActiveThreadId(threadId);
    setMessages(res.messages.map((m) => ({ role: m.role, text: m.text })));
    setPanelOpen(false);
    setStatus("Tap the mic to talk — or hold it while you speak.");
  }, []);

  useEffect(() => {
    (async () => {
      try {
        ensureVoicesLoaded();
        const [profile, threadList] = await Promise.all([api.get("/profile"), refreshThreads()]);
        setTone(profile.profile.tone || "friendly");

        if (threadList.length > 0) {
          await openThread(threadList[0].id);
        } else {
          const thread = await api.post("/chat/threads");
          setThreads([thread]);
          setActiveThreadId(thread.id);
        }
      } catch (err) {
        setTone("friendly");
        setStatus(err.message || "Couldn't load your chats.");
      }
    })();
  }, [refreshThreads, openThread]);

  // Release the analyser when leaving the page. The recorder closes its own
  // stream in onstop, and Web Speech manages its capture internally.
  useEffect(() => {
    return () => disconnectAudio();
  }, []);

  const stopSpeaking = useCallback(() => {
    stopBrowserVoice();
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setIsSpeaking(false);
  }, []);

  const handleToggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const next = !prev;
      isMutedRef.current = next;
      setStatus(next ? "Muted — replies will be text only." : "Voice replies on.");
      return next;
    });
  }, []);

  const playReply = useCallback(async (res) => {
    if (res.audio_base64) {
      const audio = new Audio(`data:${res.audio_content_type};base64,${res.audio_base64}`);
      audio.crossOrigin = "anonymous";
      audioRef.current = audio;
      audio.onended = () => setIsSpeaking(false);
      audio.onerror = () => setIsSpeaking(false);
      setIsSpeaking(true);
      // Feed playback into the analyser so the rings pulse with the reply. The
      // same graph carries the volume GainNode; if it can't be built (no
      // AudioContext), fall back to the element's own volume.
      graphConnectedRef.current = connectAudioElement(audio);
      if (!graphConnectedRef.current) audio.volume = volumeRef.current / 100;
      audio.play().catch(() => setIsSpeaking(false));
      setStatus(res.used_search ? "Answered with live search results." : "");
      return;
    }

    const outcome = await speakWithBrowserVoice(res.reply_text, res.lang, {
      onEnd: () => setIsSpeaking(false),
      volume: volumeRef.current / 100,
    });

    if (outcome === "speaking") {
      // speechSynthesis exposes no audio stream, so the rings can't follow this
      // voice — they animate gently instead of pretending to be reactive.
      setIsSpeaking(true);
      setStatus(res.audio_error || "Using your browser's voice.");
    } else if (outcome === "no-voice") {
      setStatus(`Voice unavailable for ${LANG_LABELS[res.lang] || res.lang} — showing text only.`);
    } else {
      setStatus("This browser can't play voice replies — showing text only.");
    }
  }, []);

  /** Applies a spoken instruction the backend recognised ("louder", "speak in
   * Hindi") to the same state the on-screen controls drive, so the slider
   * visibly moves and the language dropdown follows along. */
  const applyCommand = useCallback(
    (command) => {
      if (!command) return;
      if (command.action === "volume_up") {
        // Someone asking to be louder wants to hear something, so a muted
        // assistant unmutes rather than silently nodding along.
        if (isMutedRef.current) {
          isMutedRef.current = false;
          setIsMuted(false);
        }
        applyVolume(volumeRef.current + VOLUME_STEP);
      } else if (command.action === "volume_down") {
        applyVolume(volumeRef.current - VOLUME_STEP);
      } else if (command.action === "set_language" && command.lang) {
        setLang(command.lang);
      }
    },
    [applyVolume],
  );

  const askBackend = useCallback(
    async (transcriptText) => {
      if (!activeThreadId) {
        setStatus("No active chat — start a new one.");
        return;
      }
      setMessages((prev) => [...prev, { role: "user", text: transcriptText }]);
      setStatus("Thinking…");
      setIsProcessing(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await api.post(
          "/chat/ask",
          {
            transcript: transcriptText,
            lang,
            thread_id: activeThreadId,
            speak: !isMutedRef.current,
          },
          { signal: controller.signal },
        );
        setMessages((prev) => [...prev, { role: "assistant", text: res.reply_text }]);

        // Applied before playback so the confirmation is spoken at the volume
        // and in the language the user just asked for.
        applyCommand(res.command);

        if (res.thread_title) {
          setThreads((prev) =>
            prev.map((t) => (t.id === res.thread_id ? { ...t, title: res.thread_title } : t)),
          );
        }

        if (isMutedRef.current) {
          setStatus("Muted — replies are text only.");
        } else {
          await playReply(res);
        }
      } catch (err) {
        // A cancel isn't a failure — don't show it as one.
        if (err.name === "AbortError") {
          setStatus("Cancelled.");
        } else {
          setStatus(err.message || "The assistant is busy right now. Please try again.");
        }
      } finally {
        abortRef.current = null;
        setIsProcessing(false);
      }
    },
    [lang, activeThreadId, playReply, applyCommand],
  );

  const handleTypedMessage = useCallback(
    (text) => {
      stopSpeaking(); // don't talk over the next question
      askBackend(text);
    },
    [askBackend, stopSpeaking],
  );

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    setStatus("Cancelled.");
  }, []);

  const handleNewChat = useCallback(async () => {
    stopSpeaking();
    try {
      const thread = await api.post("/chat/threads");
      setThreads((prev) => [thread, ...prev]);
      setActiveThreadId(thread.id);
      setMessages([]);
      setPanelOpen(false);
      setStatus("Tap the mic to talk — or hold it while you speak.");
    } catch (err) {
      setStatus(err.message || "Couldn't start a new chat.");
    }
  }, [stopSpeaking]);

  const handleSelectThread = useCallback(
    async (threadId) => {
      if (threadId === activeThreadId) {
        setPanelOpen(false);
        return;
      }
      stopSpeaking();
      try {
        await openThread(threadId);
      } catch (err) {
        setStatus(err.message || "Couldn't open that chat.");
      }
    },
    [activeThreadId, openThread, stopSpeaking],
  );

  const handleFallbackBlob = useCallback(
    async (blob) => {
      setStatus("Transcribing…");
      try {
        const formData = new FormData();
        formData.append("file", blob, "recording.webm");
        const res = await api.postForm("/chat/transcribe", formData, { query: { lang } });
        await askBackend(res.transcript);
      } catch (err) {
        setStatus(err.message || "Couldn't understand that. Please try again.");
        setIsProcessing(false);
      }
    },
    [lang, askBackend],
  );

  const startFallbackRecording = useCallback(async () => {
    modeRef.current = "fallback";
    const recorder = await recordAudioBlob({
      onStop: handleFallbackBlob,
      onError: () => {
        setStatus("Microphone access is blocked. Allow it in your browser's address bar.");
        setIsRecording(false);
      },
    });

    // getUserMedia is async, so the user may have already let go by the time it
    // resolves. Starting a recorder nobody is holding captures nothing and
    // looks exactly like a dead mic, so stop it immediately instead.
    if (!recorder) {
      setIsRecording(false);
      return;
    }
    recorderRef.current = recorder;
    if (!pressActiveRef.current) {
      recorder.stop();
      return;
    }
    // We own this stream, so it can safely drive the ring visualisation.
    if (recorder.stream) connectStream(recorder.stream);
  }, [handleFallbackBlob]);

  const stopListening = useCallback(() => {
    pressActiveRef.current = false;
    setIsRecording(false);
    if (modeRef.current === "webspeech" && recognitionRef.current) {
      recognitionRef.current.stop();
    } else if (modeRef.current === "fallback" && recorderRef.current) {
      recorderRef.current.stop();
    }
  }, []);

  const handlePressStart = useCallback(() => {
    if (isProcessing) return;

    // Already latched on from a previous tap — this press ends the turn.
    if (latchedRef.current) {
      latchedRef.current = false;
      stopListening();
      return;
    }

    stopSpeaking(); // don't talk over the user
    pressActiveRef.current = true;
    pressStartedAtRef.current = Date.now();
    setIsRecording(true);
    setStatus("Listening…");

    if (isWebSpeechSupported()) {
      modeRef.current = "webspeech";
      // No separate getUserMedia here on purpose. The Web Speech API captures
      // the microphone itself, and opening a second capture alongside it can
      // raise another permission prompt that aborts recognition mid-start —
      // the mic then appears to hear nothing at all. The rings simply stay
      // idle in this mode; a broken mic is far worse than a still animation.
      recognitionRef.current = startWebSpeechRecognition(lang, {
        // The user still has the turn while the button is held or the tap-latch
        // is armed; the session restarts itself rather than dying on a pause.
        isActive: () => pressActiveRef.current || latchedRef.current,
        onResult: (text) => askBackend(text),
        onError: (error) => {
          if (modeRef.current !== "webspeech") return;
          // Only hand over to the recorder when Web Speech genuinely can't run
          // and the user is still holding the button. Doing it for routine
          // "no-speech"/"aborted" starts a recorder after release that records
          // nothing, which is what made the mic look dead.
          if (isFatalRecognitionError(error) && pressActiveRef.current) {
            startFallbackRecording();
          } else {
            latchedRef.current = false;
            pressActiveRef.current = false;
            setStatus(describeRecognitionError(error));
            setIsRecording(false);
          }
        },
        onEnd: (gotResult, info) => {
          // A fatal error already handed this turn to the recorder, which is
          // still holding the microphone. Clearing the press flags here would
          // stop it the moment it started.
          if (modeRef.current !== "webspeech") return;
          // Recognition is over; never leave the latch armed.
          latchedRef.current = false;
          pressActiveRef.current = false;
          setIsRecording(false);
          if (!gotResult) {
            // The microphone opening successfully and then delivering silence
            // for seconds is not the same failure as a misheard word, and
            // saying "didn't catch that" for it sends people off blaming their
            // accent when the real cause is that the browser is recording the
            // wrong input device — a virtual or disconnected mic reports itself
            // as working and produces a flat zero signal.
            const silentInput = info && !info.heardSpeech && info.openForMs > 1500;
            setStatus((s) =>
              s.startsWith("Listening")
                ? silentInput
                  ? "No sound is reaching the mic. Check which input device is selected in Windows sound settings, or in the mic icon in your browser's address bar."
                  : "Didn't catch that — try again."
                : s,
            );
          }
        },
      });
      if (!recognitionRef.current) setIsRecording(false);
    } else {
      startFallbackRecording();
    }
  }, [isProcessing, lang, askBackend, startFallbackRecording, stopSpeaking, stopListening]);

  /** Hold-to-talk and tap-to-toggle in one control.
   *
   * Deciding which one the user meant from elapsed time alone does not work. A
   * deliberate, unhurried click easily runs 400-600ms, so a threshold low
   * enough to catch real taps also misreads slow clicks as push-to-talk — and
   * push-to-talk ends the turn the instant the button comes up, cutting the
   * microphone off before the user has said anything. That is precisely how
   * this presented: the mic opened, no speech was ever detected, and the turn
   * was closed by our own stop() call.
   *
   * So the release is interpreted by what actually happened, not by a
   * stopwatch: it only ends the turn if the user held the button AND had begun
   * speaking. Letting go before saying anything means they were tapping, so
   * recording latches on and the next click sends it. */
  const TAP_THRESHOLD_MS = 700;

  const handlePressEnd = useCallback(() => {
    if (latchedRef.current) return; // latched on; the next click stops it

    // Recognition already failed (permission denied, no device, ...) and has
    // cleared this flag along with showing why. Latching now would replace a
    // real error with a "Listening…" the app isn't actually doing.
    if (!pressActiveRef.current) return;

    const heldFor = Date.now() - pressStartedAtRef.current;
    // The recorder fallback can't report speech, so it keeps the time rule.
    const startedSpeaking =
      modeRef.current === "webspeech" ? Boolean(recognitionRef.current?.hasSpeech?.()) : true;

    if (heldFor < TAP_THRESHOLD_MS || !startedSpeaking) {
      latchedRef.current = true;
      setStatus("Listening… speak now, then click the mic again to send.");
      return;
    }
    stopListening();
  }, [stopListening]);

  const handleToneChange = useCallback(async (newTone) => {
    setTone(newTone);
    try {
      await api.patch("/profile", { tone: newTone });
    } catch {
      // non-critical — tone reverts on next load
    }
  }, []);

  const handleLangChange = useCallback(async (newLang) => {
    setLang(newLang);
    await ensureVoicesLoaded();
    if (!findVoiceForLang(newLang)) {
      setStatus(
        `No ${LANG_LABELS[newLang] || newLang} voice in this browser — replies use ElevenLabs audio, or text if unavailable.`,
      );
    } else {
      setStatus("Tap the mic to talk — or hold it while you speak.");
    }
  }, []);

  // Louder voice → larger, faster rings.
  const ringScaleRate = useMemo(() => 0.1 + level * 0.5, [level]);
  const ringSpeed = useMemo(() => 1 + level * 2.2, [level]);

  return (
    <div className="chat-entering">
      <HistoryPanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        threads={threads}
        activeThreadId={activeThreadId}
        onSelectThread={handleSelectThread}
        onNewChat={handleNewChat}
        lang={lang}
        onLangChange={handleLangChange}
        busy={isProcessing}
      />

      <div className="chat-shell">
        <header className="chat-header">
          <button
            type="button"
            className="icon-button"
            onClick={() => setPanelOpen(true)}
            aria-label="Open chat history"
          >
            ☰
          </button>
          <h1>VoxMind</h1>
          <div className="header-right">
            {tone !== null && (
              <ToneToggle tone={tone} onChange={handleToneChange} disabled={isProcessing} />
            )}
            <button type="button" className="icon-button" onClick={logout} aria-label="Log out">
              Log out
            </button>
          </div>
        </header>

        <ChatTranscript messages={messages} />

        <div className="stage">
          <div className={`stage-layer${isProcessing ? "" : " hidden"}`}>
            <LazyGridScan
              enableWebcam={false}
              showPreview={false}
              sensitivity={0.55}
              lineThickness={1}
              linesColor="#FFFFFF"
              gridScale={0.1}
              scanColor="#03B3C3"
              scanOpacity={0.4}
              enablePost
              bloomIntensity={0.6}
              chromaticAberration={0.002}
              noiseIntensity={0.01}
            />
          </div>
          <div className={`stage-layer${isProcessing ? " hidden" : ""}`}>
            <LazyMagicRings
              color="#D856BF"
              colorTwo="#03B3C3"
              ringCount={5}
              speed={ringSpeed}
              attenuation={10}
              lineThickness={2}
              baseRadius={0.3}
              radiusStep={0.08}
              scaleRate={ringScaleRate}
              opacity={1}
              blur={2}
              noiseAmount={0.08}
              followMouse={false}
              clickBurst={false}
            />
          </div>
        </div>

        <div className="controls">
          <div className="status-line">{status}</div>
          <div className="control-row">
            <MicButton
              isRecording={isRecording}
              isProcessing={isProcessing}
              onPressStart={handlePressStart}
              onPressEnd={handlePressEnd}
              onCancel={handleCancel}
            />
            {/* See .spark-wrap — ClickSpark's wrapper is 100%/100%, which
                stretches it when used directly as a flex child. */}
            <div className="spark-wrap">
              <ClickSpark sparkColor="#03B3C3" sparkSize={10} sparkRadius={15} sparkCount={8} duration={400}>
                <StopMuteButton
                  isSpeaking={isSpeaking}
                  isMuted={isMuted}
                  onStop={stopSpeaking}
                  onToggleMute={handleToggleMute}
                />
              </ClickSpark>
            </div>
            {/* defaultValue is what keeps voice commands and the slider in
                sync — the component re-syncs its internal value from it, so
                saying "louder" visibly moves the handle. */}
            <ElasticSlider
              defaultValue={volume}
              startingValue={0}
              maxValue={100}
              isStepped
              stepSize={5}
              onChange={applyVolume}
            />
          </div>
          <TextComposer onSubmit={handleTypedMessage} disabled={isProcessing || !activeThreadId} />
        </div>
      </div>
    </div>
  );
}
