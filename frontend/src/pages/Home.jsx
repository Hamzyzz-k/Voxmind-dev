import { useCallback, useEffect, useRef, useState } from "react";
import ChatTranscript from "../components/ChatTranscript";
import LanguageSelector from "../components/LanguageSelector";
import MicButton from "../components/MicButton";
import ToneToggle from "../components/ToneToggle";
import Visualizer from "../components/Visualizer";
import { useAuth } from "../context/AuthContext";
import { api } from "../services/api";
import {
  isWebSpeechSupported,
  recordAudioBlob,
  speakWithBrowserVoice,
  startWebSpeechRecognition,
} from "../services/speech";

export default function Home() {
  const { logout } = useAuth();
  const [lang, setLang] = useState("en");
  const [tone, setTone] = useState("friendly");
  const [messages, setMessages] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [status, setStatus] = useState("Hold the mic and speak.");

  const recognitionRef = useRef(null);
  const recorderRef = useRef(null);
  const modeRef = useRef(null);
  const audioRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const [history, profile] = await Promise.all([api.get("/chat/history"), api.get("/profile")]);
        setMessages(history.messages.map((m) => ({ role: m.role, text: m.text })));
        setTone(profile.profile.tone);
      } catch (err) {
        setStatus(err.message || "Couldn't load your data.");
      }
    })();
  }, []);

  const askBackend = useCallback(
    async (transcriptText) => {
      setMessages((prev) => [...prev, { role: "user", text: transcriptText }]);
      setStatus("Thinking…");
      setIsProcessing(true);
      try {
        const res = await api.post("/chat/ask", { transcript: transcriptText, lang });
        setMessages((prev) => [...prev, { role: "assistant", text: res.reply_text }]);
        if (res.audio_base64) {
          audioRef.current = new Audio(`data:${res.audio_content_type};base64,${res.audio_base64}`);
          audioRef.current.play().catch(() => {});
          setStatus(res.used_search ? "Answered with live search results." : "");
        } else {
          // ElevenLabs errored or its free-tier credits ran out — fall back
          // to the browser's own voice automatically, no user action needed.
          const spoke = speakWithBrowserVoice(res.reply_text, lang);
          setStatus(spoke ? res.audio_error || "Using your browser's voice." : res.audio_error || "");
        }
      } catch (err) {
        setStatus(err.message || "The assistant is busy right now. Please try again.");
      } finally {
        setIsProcessing(false);
      }
    },
    [lang],
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
  }, [isProcessing, lang, askBackend, startFallbackRecording]);

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

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>VoxMind</h1>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <LanguageSelector lang={lang} onChange={setLang} disabled={isRecording || isProcessing} />
          <ToneToggle tone={tone} onChange={handleToneChange} disabled={isProcessing} />
          <button type="button" onClick={logout}>
            Log out
          </button>
        </div>
      </header>

      <ChatTranscript messages={messages} />

      <div className="controls">
        <div className="status-line">{status}</div>
        <Visualizer active={isRecording || isProcessing} />
        <MicButton
          isRecording={isRecording}
          disabled={isProcessing}
          onPressStart={handlePressStart}
          onPressEnd={handlePressEnd}
        />
      </div>
    </div>
  );
}
