export default function ThreadPanel({
  threads,
  activeThreadId,
  onSelect,
  onNewChat,
  onDelete,
  open,
  onClose,
  busy,
}) {
  return (
    <>
      {open && <div className="panel-backdrop" onClick={onClose} aria-hidden="true" />}
      <aside className={`thread-panel${open ? " open" : ""}`} aria-label="Chat threads">
        <div className="thread-panel-header">
          <button type="button" className="new-chat" onClick={onNewChat} disabled={busy}>
            + New Chat
          </button>
        </div>

        <nav className="thread-list">
          {threads.length === 0 && <p className="thread-empty">No chats yet.</p>}
          {threads.map((thread) => (
            <div
              key={thread.id}
              className={`thread-item${thread.id === activeThreadId ? " active" : ""}`}
            >
              <button
                type="button"
                className="thread-title"
                onClick={() => onSelect(thread.id)}
                disabled={busy}
                title={thread.title || "New chat"}
              >
                {thread.title || "New chat"}
              </button>
              <button
                type="button"
                className="thread-delete"
                onClick={() => onDelete(thread.id)}
                disabled={busy}
                aria-label={`Delete ${thread.title || "New chat"}`}
              >
                ×
              </button>
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}
