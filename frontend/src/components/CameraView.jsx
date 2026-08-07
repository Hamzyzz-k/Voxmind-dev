import { useEffect, useState } from "react";
import { fetchCameraFrame, getStreamTicket } from "../services/iot";

// ~3fps. The ESP32-CAM's own WiFi is the bottleneck long before this number
// is — see the Phase 2 architecture doc for why higher isn't free.
const POLL_INTERVAL_MS = 333;

// The backend issues tickets with a 60s TTL; refreshing at 45s leaves a
// margin so a slow request never lands with an already-expired ticket.
const TICKET_REFRESH_MS = 45_000;

/** Polls one device's latest video frame and renders it.
 *
 * The frame can't be an `<img src="...">` pointed straight at the API: an
 * `<img>` tag sends no custom headers, so it can't carry the stream ticket,
 * and a ticket in the URL would leak into browser history and server logs.
 * So this fetches each frame as a Blob and renders it via an object URL
 * instead — which makes leak prevention the caller's job: every swap MUST
 * revoke the previous URL, or the tab leaks ~15KB per frame and dies within
 * the hour at this poll rate.
 *
 * All mutable poll state (cancellation flag, current ticket, the timer id,
 * the live object URL) lives in plain closure variables *inside* the effect,
 * not in refs on the component. Refs are shared by every effect instance for
 * the component's whole lifetime — under StrictMode's dev-only mount ->
 * cleanup -> mount, that let the *second* mount's fresh `cancelled = false`
 * silently un-cancel the *first* mount's still-settling poll chain, so both
 * ended up running forever in parallel. Two independent 3fps loops flooded
 * the endpoint and tripped its rate limit within seconds — caught only by
 * watching real network traffic, not by reading the code. A plain `let`
 * declared inside the effect callback is a fresh binding on every
 * invocation, so the orphaned instance's own closure sees its own
 * cancellation and stops for good.
 */
export default function CameraView({ deviceId }) {
  const [frameUrl, setFrameUrl] = useState(null);
  const [status, setStatus] = useState("connecting"); // connecting | live | offline | error

  useEffect(() => {
    let cancelled = false;
    let paused = false;
    let ticket = null;
    let ticketIssuedAt = 0;
    let currentUrl = null;
    let timerId = null;
    const controller = new AbortController();

    async function ensureTicket() {
      if (ticket && Date.now() - ticketIssuedAt < TICKET_REFRESH_MS) return ticket;
      const res = await getStreamTicket(deviceId);
      ticket = res.ticket;
      ticketIssuedAt = Date.now();
      return ticket;
    }

    function swapFrame(blob) {
      const nextUrl = URL.createObjectURL(blob);
      if (currentUrl) URL.revokeObjectURL(currentUrl);
      currentUrl = nextUrl;
      setFrameUrl(nextUrl);
    }

    // Drops the last frame's object URL rather than leaving it allocated for
    // as long as the device stays offline — same leak-prevention rule as a
    // normal swap, just with nothing to replace it.
    function clearFrame() {
      if (currentUrl) {
        URL.revokeObjectURL(currentUrl);
        currentUrl = null;
        setFrameUrl(null);
      }
    }

    async function pollOnce() {
      try {
        const currentTicket = await ensureTicket();
        const blob = await fetchCameraFrame(deviceId, currentTicket, { signal: controller.signal });
        if (cancelled) return;

        if (blob) {
          swapFrame(blob);
          setStatus("live");
        } else {
          // 404 — no recent frame. A frozen last image would look live when
          // it isn't, so the placeholder takes over instead of leaving the
          // previous frame on screen.
          clearFrame();
          setStatus("offline");
        }
      } catch (err) {
        if (err.name === "AbortError") return;
        // A stream-ticket rejection (expired/invalid) means our clock-based
        // refresh missed — force a fresh one on the next attempt rather than
        // retrying the same bad ticket in a loop.
        if (err.status === 401 || err.status === 403) {
          ticket = null;
        }
        clearFrame();
        setStatus("error");
      }
    }

    function scheduleNext() {
      if (cancelled) return;
      timerId = setTimeout(async () => {
        if (!paused) await pollOnce();
        scheduleNext();
      }, POLL_INTERVAL_MS);
    }

    pollOnce().then(scheduleNext);

    // A backgrounded tab polling at 3fps burns bandwidth and Render hours
    // for a frame nobody's looking at.
    const onVisibility = () => {
      paused = document.hidden;
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      controller.abort();
      document.removeEventListener("visibilitychange", onVisibility);
      if (timerId) clearTimeout(timerId);
      if (currentUrl) URL.revokeObjectURL(currentUrl);
    };
  }, [deviceId]);

  return (
    <div className="camera-view">
      {frameUrl && status === "live" ? (
        <img className="camera-frame" src={frameUrl} alt="Live view from device" />
      ) : (
        <div className={`camera-placeholder camera-placeholder--${status}`}>
          {status === "connecting" && "Connecting…"}
          {status === "offline" && "Device offline"}
          {status === "error" && "Couldn't reach the stream"}
        </div>
      )}
    </div>
  );
}
