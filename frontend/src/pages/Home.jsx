import { useCallback, useEffect, useRef, useState } from "react";
import ChatTranscript from "../components/ChatTranscript";
import LanguageSelector from "../components/LanguageSelector";
import MicButton from "../components/MicButton";
import StopMuteButton from "../components/StopMuteButton";
import ThreadPanel from "../components/ThreadPanel";
import ToneToggle from "../components/ToneToggle";
import Visualizer from "../components/Visualizer";
import { useAuth } from "../context/AuthContext";
import { api } from "../services/api";
import {
  LANG_LABELS,
  ensureVoicesLoaded,
  findVoiceForLang,
  isWebSpeechSupported,
  recordAudioBlob,
  speakWithBrowserVoice,
  startWebSpeechRecognition,
  stopBrowserVoice,
} from "../services/speech";

export default function Home() {
  const { logout } = useAuth();
  const [lang, setLang] = useState("en");
  const [tone, setTone] = useState("friendly");
  const [messages, setMessages] = useState([]);
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [status, setStatus] = useState("Hold the mic and speak.");

  const recognitionRef = useRef(null);
  const recorderRef = useRef(null);
  const modeRef = useRef(null);
  const audioRef = useRef(null);
  const isMutedRef = useRef(false);

  // askBackend runs inside speech callbacks that close over stale state, so
  // mute is mirrored into a ref to keep the value read at call time correct.
  useEffect(() => {
    isMutedRef.current = isMuted;
  }, [isMuted]);

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
    setStatus("Hold the mic and speak.");
  }, []);

  // Initial load: voices, profile, threads. Opens the most recent thread, or
  // creates a first one if the user has none yet.
  useEffect(() => {
    (async () => {
      try {
        ensureVoicesLoaded();
        const [profile, threadList] = await Promise.all([api.get("/profile"), refreshThreads()]);
        setTone(profile.profile.tone);

        if (threadList.length > 0) {
          await openThread(threadList[0].id);
        } else {
          const thread = await api.post("/chat/threads");
          setThreads([thread]);
          setActiveThreadId(thread.id);
        }
      } catch (err) {
        setStatus(err.message || "Couldn't load your chats.");
      }
    })();
  }, [refreshThreads, openThread]);

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
    // Server-generated audio (ElevenLabs) is preferred; the browser voice is
    // the fallback when it's unavailable.
    if (res.audio_base64) {
      const audio = new Audio(`data:${res.audio_content_type};base64,${res.audio_base64}`);
      audioRef.current = audio;
      audio.onended = () => setIsSpeaking(false);
      audio.onerror = () => setIsSpeaking(false);
      setIsSpeaking(true);
      audio.play().catch(() => setIsSpeaking(false));
      setStatus(res.used_search ? "Answered with live search results." : "");
      return;
    }

    const outcome = await speakWithBrowserVoice(res.reply_text, res.lang, {
      onEnd: () => setIsSpeaking(false),
    });

    if (outcome === "speaking") {
      setIsSpeaking(true);
      setStatus(res.audio_error || "Using your browser's voice.");
    } else if (outcome === "no-voice") {
      // Don't fail silently: speechSynthesis just does nothing when the OS has
      // no voice for this language (common for Kannada/Tamil on Windows).
      setStatus(`Voice unavailable for ${LANG_LABELS[res.lang] || res.lang} — showing text only.`);
    } else {
      setStatus("This browser can't play voice replies — showing text only.");
    }
  }, []);

  const askBackend = useCallback(
    async (transcriptText) => {
      if (!activeThreadId) {
        setStatus("No active chat — start a new one.");
        return;
      }
      setMessages((prev) => [...prev, { role: "user", text: transcriptText }]);
      setStatus("Thinking…");
      setIsProcessing(true);
      try {
        const res = await api.post("/chat/ask", {
          transcript: transcriptText,
          lang,
          thread_id: activeThreadId,
          speak: !isMutedRef.current,
        });
        setMessages((prev) => [...prev, { role: "assistant", text: res.reply_text }]);

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
        setStatus(err.message || "The assistant is busy right now. Please try again.");
      } finally {
        setIsProcessing(false);
      }
    },
    [lang, activeThreadId, playReply],
  );

  const handleNewChat = useCallback(async () => {
    stopSpeaking();
    try {
      const thread = await api.post("/chat/threads");
      setThreads((prev) => [thread, ...prev]);
      setActiveThreadId(thread.id);
      setMessages([]);
      setPanelOpen(false);
      setStatus("Hold the mic and speak.");
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

  const handleDeleteThread = useCallback(
    async (threadId) => {
      try {
        await api.delete(`/chat/threads/${threadId}`);
        const remaining = threads.filter((t) => t.id !== threadId);
        setThreads(remaining);

        if (threadId === activeThreadId) {
          stopSpeaking();
          if (remaining.length > 0) {
            await openThread(remaining[0].id);
          } else {
            const thread = await api.post("/chat/threads");
            setThreads([thread]);
            setActiveThreadId(thread.id);
            setMessages([]);
          }
        }
      } catch (err) {
        setStatus(err.message || "Couldn't delete that chat.");
      }
    },
    [threads, activeThreadId, openThread, stopSpeaking],
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
    recorderRef.current = await recordAudioBlob({
      onStop: handleFallbackBlob,
      onError: () => {
        setStatus("Microphone permission denied.");
        setIsRecording(false);
      },
    });
    if (!recorderRef.current) {
      setIsRecording(false);
    }
  }, [handleFallbackBlob]);

  const handlePressStart = useCallback(() => {
    if (isProcessing) return;
    stopSpeaking(); // don't talk over the user
    setIsRecording(true);
    setStatus("Listening…");

    if (isWebSpeechSupported()) {
      modeRef.current = "webspeech";
      recognitionRef.current = startWebSpeechRecognition(lang, {
        onResult: (text) => askBackend(text),
        onError: () => {
          if (modeRef.current === "webspeech") {
            startFallbackRecording();
          }
        },
        onEnd: () => {},
      });
    } else {
      startFallbackRecording();
    }
  }, [isProcessing, lang, askBackend, startFallbackRecording, stopSpeaking]);

  const handlePressEnd = useCallback(() => {
    setIsRecording(false);
    if (modeRef.current === "webspeech" && recognitionRef.current) {
      recognitionRef.current.stop();
    } else if (modeRef.current === "fallback" && recorderRef.current) {
      recorderRef.current.stop();
    }
  }, []);

  const handleToneChange = useCallback(async (newTone) => {
    setTone(newTone);
    try {
      await api.patch("/profile", { tone: newTone });
    } catch {
      // non-critical — tone will just reset next reload
    }
  }, []);

  const handleLangChange = useCallback(async (newLang) => {
    setLang(newLang);
    await ensureVoicesLoaded(); // avoid a false warning before voices load
    if (!findVoiceForLang(newLang)) {
      setStatus(
        `Note: no ${LANG_LABELS[newLang] || newLang} voice installed in this browser — ` +
          `replies use ElevenLabs audio, or show as text if that's unavailable.`,
      );
    }
  }, []);

  return (
    <div className="app-layout">
      <ThreadPanel
        threads={threads}
        activeThreadId={activeThreadId}
        onSelect={handleSelectThread}
        onNewChat={handleNewChat}
        onDelete={handleDeleteThread}
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        busy={isProcessing}
      />

      <div className="app-shell">
        <header className="app-header">
          <button
            type="button"
            className="panel-toggle"
            onClick={() => setPanelOpen((o) => !o)}
            aria-label="Toggle chat list"
          >
            ☰
          </button>
          <h1>VoxMind</h1>
          <div className="header-controls">
            <LanguageSelector lang={lang} onChange={handleLangChange} disabled={isRecording || isProcessing} />
            <ToneToggle tone={tone} onChange={handleToneChange} disabled={isProcessing} />
            <button type="button" onClick={logout}>
              Log out
            </button>
          </div>
        </header>

        <ChatTranscript messages={messages} />

        <div className="controls">
          <div className="status-line">{status}</div>
          <Visualizer active={isRecording || isProcessing || isSpeaking} />
          <div className="control-row">
            <MicButton
              isRecording={isRecording}
              disabled={isProcessing}
              onPressStart={handlePressStart}
              onPressEnd={handlePressEnd}
            />
            <StopMuteButton
              isSpeaking={isSpeaking}
              isMuted={isMuted}
              onStop={stopSpeaking}
              onToggleMute={handleToggleMute}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
