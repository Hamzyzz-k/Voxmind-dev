import { useEffect, useRef } from "react";
import BlurText from "../reactbits/BlurText";

/** Assistant replies reveal word-by-word via BlurText; the user's own messages
 *  render plainly, since they already know what they just said. Only the newest
 *  assistant message animates — replaying the effect on every past message while
 *  scrolling back through a thread would be noise. */
export default function ChatTranscript({ messages }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const lastIndex = messages.length - 1;

  if (messages.length === 0) {
    return (
      <div className="transcript">
        <p className="transcript-empty">Tap the mic and ask something to get started.</p>
        <div ref={endRef} />
      </div>
    );
  }

  return (
    <div className="transcript">
      {messages.map((msg, i) => {
        const key = `${i}-${msg.role}`;
        if (msg.role === "assistant") {
          const isNewest = i === lastIndex;
          return (
            <div key={key} className="message assistant">
              {isNewest ? (
                <BlurText
                  text={msg.text}
                  delay={80}
                  animateBy="words"
                  direction="top"
                  className="ai-response-text"
                />
              ) : (
                <span className="ai-response-text">{msg.text}</span>
              )}
            </div>
          );
        }
        return (
          <div key={key} className="message user">
            {msg.text}
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
