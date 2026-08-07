import { api } from "./api";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// --- Device management — Firebase ID token, same as every other endpoint ---

export const listDevices = () => api.get("/iot/devices");
export const registerDevice = (name, type = "glasses") => api.post("/iot/devices", { name, type });
export const revokeDevice = (id) => api.delete(`/iot/devices/${id}`);

/** Exchanges the caller's Firebase ID token for a short-lived, device-scoped
 * stream ticket. This is the *only* Firestore-touching call in the video
 * path — everything after it (frame polling) is checked in-process on the
 * backend with no database read at all, which is what keeps polling at
 * multiple frames per second off the Firestore free-tier quota. */
export const getStreamTicket = (deviceId) => api.post(`/iot/camera/${deviceId}/ticket`);

/** Fetches one video frame as a Blob, authenticated with a stream ticket
 * rather than the Bearer token `api.js` normally attaches.
 *
 * This can't go through `<img src="...">` at all: an `<img>` tag sends no
 * custom headers, and the tempting alternative — the ticket in the URL's
 * query string — would leak it into browser history, server logs and
 * Referer headers. So this fetches the bytes directly and the caller turns
 * them into a blob URL instead.
 *
 * Returns `null` on a 404 (no recent frame — device offline or stale), which
 * the caller treats as "show an offline placeholder", not an error.
 */
export async function fetchCameraFrame(deviceId, ticket, { signal } = {}) {
  const res = await fetch(`${BASE_URL}/iot/camera/${deviceId}/frame`, {
    headers: { Authorization: `Ticket ${ticket}` },
    signal,
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    const err = new Error(`Frame request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return res.blob();
}
