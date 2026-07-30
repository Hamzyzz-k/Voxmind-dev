import { useEffect, useRef } from "react";

export default function ChatTranscript({ messages }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="transcript">
      {messages.map((msg, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <div key={i} className={`message ${msg.role}`}>
          {msg.text}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
