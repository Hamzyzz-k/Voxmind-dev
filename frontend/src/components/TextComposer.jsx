import { useState } from "react";

/** Typing alternative to the mic.
 *
 * Submitted text takes exactly the same path as a transcript — it just skips
 * STT — so tone, profile memory, thread context, the one-sentence response rule
 * and the spoken reply all behave identically. Spoken commands work here too,
 * since intent detection happens on the server.
 */
export default function TextComposer({ onSubmit, disabled }) {
  const [text, setText] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    setText("");
    onSubmit(trimmed);
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <input
        type="text"
        className="composer-input"
        placeholder="…or type your message"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        aria-label="Type a message"
      />
      <button
        type="submit"
        className="composer-send"
        disabled={disabled || !text.trim()}
        aria-label="Send message"
      >
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M2.01 21 23 12 2.01 3 2 10l15 2-15 2z" />
        </svg>
      </button>
    </form>
  );
}
