import { useEffect, useState } from "react";
import { TALKBACK_CHANGE_EVENT, isTalkBackEnabled, toggleTalkBack } from "../services/talkback";

/** A visible, permanent switch for TalkBack, alongside the existing Alt+A
 * shortcut rather than replacing it.
 *
 * Before this, TalkBack's only entry point was a keyboard shortcut announced
 * once per browser tab — fine for a returning blind user who already knows
 * it, but it left two groups with no way in: a first-time visitor who missed
 * or didn't understand the spoken hint, and a low-vision user who can see
 * well enough to want a button but not well enough to read dense UI without
 * help. A permanent, findable switch closes both gaps without taking
 * anything away from someone who already knows Alt+A.
 *
 * Rendered once at the App root rather than per-page, so it is present on
 * every route without wiring it into five separate page components — see
 * App.jsx.
 *
 * Deliberately a small component reading talkback.js's state, not a second
 * copy of that state. talkback.js is intentionally a plain module rather
 * than React state (see its file docstring) so a capture-phase document
 * listener has nothing tied to a component's lifecycle to corrupt. Mirroring
 * that state here via the TALKBACK_CHANGE_EVENT keeps talkback.js as the only
 * source of truth: this component just reflects it, from whichever entry
 * point changed it last (this button, or Alt+A elsewhere).
 */
export default function TalkBackToggle() {
  const [enabled, setEnabled] = useState(isTalkBackEnabled);

  useEffect(() => {
    const onChange = (event) => setEnabled(event.detail.enabled);
    window.addEventListener(TALKBACK_CHANGE_EVENT, onChange);
    return () => window.removeEventListener(TALKBACK_CHANGE_EVENT, onChange);
  }, []);

  return (
    <button
      type="button"
      className={`talkback-toggle${enabled ? " is-on" : ""}`}
      onClick={toggleTalkBack}
      aria-pressed={enabled}
      // TalkBack's own click-intercept only arms action elements — button,
      // link, [role=button], etc. (see talkback.js's INTERACTIVE_SELECTOR).
      // This button matches that selector, so while TalkBack is already on,
      // clicking it goes through the same touch-then-confirm cycle as any
      // other button rather than toggling instantly. That is correct, not a
      // bug: a screen-reader-style user already relies on that cycle
      // everywhere else on the page, and this control should not quietly
      // break the one convention they have learned to trust.
      aria-label={enabled ? "Turn off TalkBack" : "Turn on TalkBack, a built-in screen reader"}
      title="TalkBack (Alt+A)"
    >
      <span className="talkback-toggle__dot" aria-hidden="true" />
      TalkBack
    </button>
  );
}
