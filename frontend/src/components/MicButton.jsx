export default function MicButton({ isRecording, disabled, onPressStart, onPressEnd }) {
  const handlers = disabled
    ? {}
    : {
        onMouseDown: onPressStart,
        onMouseUp: onPressEnd,
        onMouseLeave: () => isRecording && onPressEnd(),
        onTouchStart: (e) => {
          e.preventDefault();
          onPressStart();
        },
        onTouchEnd: (e) => {
          e.preventDefault();
          onPressEnd();
        },
      };

  return (
    <button
      type="button"
      className={`mic-button${isRecording ? " recording" : ""}`}
      disabled={disabled}
      aria-pressed={isRecording}
      aria-label={isRecording ? "Recording — release to send" : "Hold to speak"}
      {...handlers}
    >
      🎤
    </button>
  );
}
