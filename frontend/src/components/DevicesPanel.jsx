import { useCallback, useEffect, useState } from "react";
import CameraView from "./CameraView";
import ClickSpark from "../reactbits/ClickSpark";
import { listDevices, registerDevice, revokeDevice } from "../services/iot";

/** Slide-in panel for Phase 2 hardware: registering a device, seeing whether
 * it's online, viewing its camera feed, and revoking it. Mirrors
 * HistoryPanel's slide-in mechanics, from the right rather than the left. */
export default function DevicesPanel({ open, onClose }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);
  // The plaintext token is shown exactly once, right after registration, and
  // is never retrievable again — not even by us. Losing this state loses it
  // for good, which is the whole point.
  const [justRegistered, setJustRegistered] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listDevices();
      setDevices(res.devices);
    } catch (err) {
      setError(err.message || "Couldn't load devices.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  async function handleRegister(e) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setAdding(true);
    setError(null);
    try {
      const device = await registerDevice(trimmed);
      setJustRegistered(device);
      setName("");
      await refresh();
    } catch (err) {
      setError(err.message || "Couldn't register the device.");
    } finally {
      setAdding(false);
    }
  }

  async function handleRevoke(deviceId) {
    if (expandedId === deviceId) setExpandedId(null);
    try {
      await revokeDevice(deviceId);
      await refresh();
    } catch (err) {
      setError(err.message || "Couldn't remove the device.");
    }
  }

  function handleAcknowledgeToken() {
    setJustRegistered(null);
  }

  return (
    <>
      <div className={`panel-backdrop${open ? " open" : ""}`} onClick={onClose} aria-hidden="true" />

      <aside className={`devices-panel${open ? " open" : ""}`} aria-label="Devices" aria-hidden={!open}>
        <div className="panel-header">
          <p className="panel-title">Devices</p>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close devices panel">
            ✕
          </button>
        </div>

        {justRegistered && (
          <div className="device-token-reveal">
            <p className="device-token-warning">
              This is the only time <strong>{justRegistered.name}</strong>'s token will be shown. Copy it into the
              device now — it can't be retrieved again.
            </p>
            <code className="device-token-value">{justRegistered.token}</code>
            <div className="device-token-actions">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => navigator.clipboard?.writeText(justRegistered.token)}
              >
                Copy
              </button>
              <button type="button" className="btn-primary" onClick={handleAcknowledgeToken}>
                Done
              </button>
            </div>
          </div>
        )}

        <form className="device-add-form" onSubmit={handleRegister}>
          <input
            type="text"
            placeholder="Device name (e.g. Glasses)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={60}
            disabled={adding}
          />
          <div className="spark-wrap">
            <ClickSpark sparkColor="#03B3C3" sparkSize={10} sparkRadius={15} sparkCount={8} duration={400}>
              <button type="submit" className="btn-primary" disabled={adding || !name.trim()}>
                {adding ? "Adding…" : "+ Add device"}
              </button>
            </ClickSpark>
          </div>
        </form>

        {error && <p className="form-error">{error}</p>}

        <div className="device-list">
          {loading && devices.length === 0 && <p className="panel-empty">Loading…</p>}
          {!loading && devices.length === 0 && <p className="panel-empty">No devices yet.</p>}

          {devices.map((d) => (
            <div key={d.id} className="device-card">
              <div className="device-card-row">
                <span className={`device-status-dot${d.online ? " online" : ""}`} aria-hidden="true" />
                <span className="device-name">{d.name}</span>
                <span className="device-status-text">{d.online ? "Online" : "Offline"}</span>
              </div>

              <div className="device-card-actions">
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => setExpandedId(expandedId === d.id ? null : d.id)}
                >
                  {expandedId === d.id ? "Hide camera" : "View camera"}
                </button>
                <button type="button" className="btn-ghost device-revoke" onClick={() => handleRevoke(d.id)}>
                  Remove
                </button>
              </div>

              {expandedId === d.id && <CameraView deviceId={d.id} />}
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}
