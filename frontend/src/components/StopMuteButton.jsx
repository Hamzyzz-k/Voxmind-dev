/** One control, two behaviours depending on state:
 *  - while the assistant is speaking → stops playback immediately
 *  - while idle → toggles mute, so future replies stay text-only
 *    (the backend skips the TTS call entirely when muted). */
export default function StopMuteButton({ isSpeaking, isMuted, onStop, onToggleMute }) {
  if (isSpeaking) {
    return (
      <button type="button" className="stop-mute stopping" onClick={onStop} aria-label="Stop speaking">
        ■ Stop
      </button>
    );
  }

  return (
    <button
      type="button"
      className={`stop-mute${isMuted ? " muted" : ""}`}
      onClick={onToggleMute}
      aria-pressed={isMuted}
      aria-label={isMuted ? "Unmute voice replies" : "Mute voice replies"}
    >
      {isMuted ? "🔇 Muted" : "🔊 Voice on"}
    </button>
  );
}
