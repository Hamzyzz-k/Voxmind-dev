import { useMemo, useRef } from "react";
import ClickSpark from "../reactbits/ClickSpark";
import OptionWheel from "../reactbits/OptionWheel";
import { LANG_LABELS } from "../services/speech";

/** Slide-in history panel.
 *
 * OptionWheel renders only the curved list; the translucent overlay, backdrop
 * blur and open/close transition are this wrapper's job (see .history-panel in
 * index.css). The language selector lives here too, keeping the chat screen
 * itself uncluttered.
 */
export default function HistoryPanel({
  open,
  onClose,
  threads,
  activeThreadId,
  onSelectThread,
  onNewChat,
  lang,
  onLangChange,
  busy,
}) {
  const titles = useMemo(() => threads.map((t) => t.title || "New chat"), [threads]);

  const activeIndex = useMemo(() => {
    const i = threads.findIndex((t) => t.id === activeThreadId);
    return i >= 0 ? i : 0;
  }, [threads, activeThreadId]);

  const highlightedRef = useRef(activeIndex);

  // OptionWheel fires onChange every time the highlighted item changes —
  // while scrolling and dragging, not just on click. Opening a chat there
  // meant every thread you scrolled past was loaded and run. So onChange is
  // treated as "highlight only", and a chat opens only on a deliberate click.
  const handleWheelChange = (index) => {
    highlightedRef.current = index;
  };

  const handleWheelClick = (event) => {
    // Ignore clicks on empty space around the arc.
    const el = event.target.closest?.('[class*="option-wheel__item"]');
    if (!el) return;

    // Read the position straight from the DOM rather than trusting the
    // highlight, which lags a click on an off-centre item by a frame.
    const items = [...event.currentTarget.querySelectorAll('[class*="option-wheel__item"]')];
    const index = items.indexOf(el);
    const thread = threads[index >= 0 ? index : highlightedRef.current];
    if (thread && thread.id !== activeThreadId) onSelectThread(thread.id);
  };

  return (
    <>
      <div
        className={`panel-backdrop${open ? " open" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        className={`history-panel${open ? " open" : ""}`}
        aria-label="Chat history"
        aria-hidden={!open}
      >
        <div className="panel-header">
          <p className="panel-title">Chats</p>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close chat history">
            ✕
          </button>
        </div>

        {/* ClickSpark's own wrapper is hard-coded width:100%/height:100%, so as a
            direct flex child it stretches and starves the wheel below it. This
            plain block gives that percentage height something auto-sized to
            resolve against. */}
        <div className="spark-wrap">
          <ClickSpark sparkColor="#03B3C3" sparkSize={10} sparkRadius={15} sparkCount={8} duration={400}>
            <button type="button" className="btn-primary" onClick={onNewChat} disabled={busy}>
              + New Chat
            </button>
          </ClickSpark>
        </div>

        <div className="panel-wheel" onClick={handleWheelClick}>
          {titles.length === 0 ? (
            <p className="panel-empty">No chats yet.</p>
          ) : (
            <OptionWheel
              items={titles}
              textColor="#c4c4c4"
              activeColor="#03B3C3"
              side="left"
              fontSize={1.6}
              spacing={1.4}
              draggable
              defaultSelected={activeIndex}
              onChange={handleWheelChange}
            />
          )}
        </div>

        <div className="panel-section">
          <label className="panel-label" htmlFor="lang-select">
            Language
          </label>
          <select
            id="lang-select"
            className="lang-select"
            value={lang}
            onChange={(e) => onLangChange(e.target.value)}
            disabled={busy}
          >
            {Object.entries(LANG_LABELS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </aside>
    </>
  );
}
