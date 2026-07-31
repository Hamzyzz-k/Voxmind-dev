const MicIcon = () => (
  <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="9" y="2" width="6" height="11" rx="3" />
    <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
    <line x1="12" y1="18" x2="12" y2="22" />
  </svg>
);

const StopIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </svg>
);

/** Hold to talk. While a reply is being generated the same button becomes a
 *  cancel control, so a mistaken or misheard question can be abandoned without
 *  waiting for it to finish. */
export default function MicButton({ isRecording, isProcessing, onPressStart, onPressEnd, onCancel }) {
  if (isProcessing) {
    return (
      <button
        type="button"
        className="mic-button cancellable"
        onClick={onCancel}
        aria-label="Cancel this request"
        title="Cancel"
      >
        <StopIcon />
      </button>
    );
  }

  const handlers = {
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
      aria-pressed={isRecording}
      aria-label={isRecording ? "Recording — release to send" : "Hold to speak"}
      title={isRecording ? "Release to send" : "Hold to speak"}
      {...handlers}
    >
      <MicIcon />
    </button>
  );
}
