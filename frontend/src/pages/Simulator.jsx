import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import GlassesScene from "../components/simulator/GlassesScene";
import PhoneDemo from "../components/simulator/PhoneDemo";
import { PARTS } from "../components/simulator/glassesModel";
import { useAuth } from "../context/AuthContext";
import { listDevices, registerDevice } from "../services/iot";

const EXPLODE_PRESETS = [
  { label: "Assembled", value: 0 },
  { label: "Half", value: 0.5 },
  { label: "Exploded", value: 1 },
];

/** The VoxMind Glasses simulator.
 *
 * Split in two on purpose, and the split follows who needs what:
 *
 *   - The design half is public. Someone reviewing this project should be
 *     able to open a link on their own phone and turn the device over in
 *     their hands without an account, a password, or a copy of this laptop.
 *   - The live half is not, and cannot be. It authenticates as a real device
 *     against a real backend and spends real API quota, so it lives behind
 *     the same sign-in as the rest of the app.
 */
export default function Simulator() {
  const { user, mfaVerified } = useAuth();
  const [tab, setTab] = useState("design");

  const [explode, setExplode] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  const [autoRotate, setAutoRotate] = useState(true);
  const [resetSignal, setResetSignal] = useState(0);

  const selected = PARTS.find((part) => part.id === selectedId) || null;
  const totalCost = PARTS.reduce((sum, part) => sum + (part.price || 0), 0);

  return (
    <div className="simulator">
      <header className="sim-header">
        <div>
          <p className="sim-eyebrow">VoxMind Glasses</p>
          <h1 className="sim-title">Device simulator</h1>
          <p className="sim-subtitle">
            The wearable, before it is built: its structure, its components, and its behaviour
            running against the live backend.
          </p>
        </div>
        <Link className="sim-button sim-button--ghost" to="/">
          Back to VoxMind
        </Link>
      </header>

      <nav className="sim-tabs" aria-label="Simulator sections">
        <button
          type="button"
          className={`sim-tab${tab === "design" ? " is-active" : ""}`}
          onClick={() => setTab("design")}
        >
          Physical design
        </button>
        <button
          type="button"
          className={`sim-tab${tab === "demo" ? " is-active" : ""}`}
          onClick={() => setTab("demo")}
        >
          Live demonstration
        </button>
      </nav>

      {tab === "design" ? (
        <section className="sim-design">
          <div className="sim-viewport">
            <GlassesScene
              explode={explode}
              selectedId={selectedId}
              onSelect={setSelectedId}
              autoRotate={autoRotate}
              resetSignal={resetSignal}
            />
            <p className="sim-viewport__hint">
              Drag to rotate · scroll to zoom · click a component
            </p>
          </div>

          <aside className="sim-panel">
            <div className="sim-panel__controls">
              <label className="sim-slider">
                <span className="sim-slider__label">
                  Exploded view
                  <strong>{Math.round(explode * 100)}%</strong>
                </span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={explode}
                  onChange={(event) => setExplode(Number(event.target.value))}
                />
              </label>

              <div className="sim-presets">
                {EXPLODE_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    className={`sim-chip${explode === preset.value ? " is-active" : ""}`}
                    onClick={() => setExplode(preset.value)}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>

              <div className="sim-panel__row">
                <label className="sim-check">
                  <input
                    type="checkbox"
                    checked={autoRotate}
                    onChange={(event) => setAutoRotate(event.target.checked)}
                  />
                  Rotate
                </label>
                <button type="button" className="sim-chip" onClick={() => setResetSignal((n) => n + 1)}>
                  Reset view
                </button>
              </div>
            </div>

            {selected ? (
              <div className="sim-detail">
                <div className="sim-detail__head">
                  <span className="sim-swatch" style={{ background: selected.color }} />
                  <h2>{selected.name}</h2>
                </div>
                <p className="sim-detail__role">{selected.role}</p>
                <p className="sim-detail__body">{selected.detail}</p>
                {selected.price !== null && (
                  <p className="sim-detail__price">Approx. ₹{selected.price.toLocaleString("en-IN")}</p>
                )}
                <button type="button" className="sim-chip" onClick={() => setSelectedId(null)}>
                  Clear selection
                </button>
              </div>
            ) : (
              <p className="sim-detail__empty">
                Select a component in the model, or from the list below, to read what it does and
                why it was chosen.
              </p>
            )}

            <ul className="sim-parts">
              {PARTS.map((part) => (
                <li key={part.id}>
                  <button
                    type="button"
                    className={`sim-part${selectedId === part.id ? " is-active" : ""}`}
                    onClick={() => setSelectedId(selectedId === part.id ? null : part.id)}
                  >
                    <span className="sim-swatch" style={{ background: part.color }} />
                    <span className="sim-part__name">{part.name}</span>
                    {part.price !== null && (
                      <span className="sim-part__price">₹{part.price.toLocaleString("en-IN")}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>

            <p className="sim-total">
              Electronics bill of materials: <strong>₹{totalCost.toLocaleString("en-IN")}</strong>
              <span> — frame, lenses and power bank excluded.</span>
            </p>
          </aside>
        </section>
      ) : (
        <DemoTab user={user} mfaVerified={mfaVerified} />
      )}
    </div>
  );
}

/** The live half.
 *
 * A device token is shown to its owner exactly once, at registration, and is
 * only ever stored hashed on the server — so this cannot look up the token of
 * a device registered earlier. It provisions a fresh simulated device and
 * keeps that token in memory for the session instead. Deliberately not
 * localStorage: a long-lived device credential sitting in a browser store on
 * a shared demo machine is the kind of thing that is still there months
 * later.
 */
function DemoTab({ user, mfaVerified }) {
  const [deviceToken, setDeviceToken] = useState(null);
  const [deviceName, setDeviceName] = useState("");
  const [status, setStatus] = useState("idle"); // idle | provisioning | ready | error
  const [error, setError] = useState("");
  const [existingCount, setExistingCount] = useState(null);

  const signedIn = Boolean(user) && mfaVerified;

  useEffect(() => {
    if (!signedIn) return undefined;
    let cancelled = false;
    listDevices()
      .then((res) => {
        if (!cancelled) setExistingCount(res.devices.length);
      })
      .catch(() => {
        if (!cancelled) setExistingCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [signedIn]);

  const provision = useCallback(async () => {
    setStatus("provisioning");
    setError("");
    try {
      const name = `Simulator ${new Date().toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
      })}`;
      const device = await registerDevice(name, "glasses");
      setDeviceToken(device.token);
      setDeviceName(device.name);
      setStatus("ready");
    } catch (err) {
      setStatus("error");
      setError(err.message || "Could not register a simulated device.");
    }
  }, []);

  if (!signedIn) {
    return (
      <section className="sim-gate">
        <h2>Sign in to run the live demonstration</h2>
        <p>
          This half talks to the real backend as a real device: it registers against your account,
          sends a real photo to the vision model, and spends real API quota. That needs a signed-in
          account, so it cannot be opened anonymously.
        </p>
        <p className="sim-gate__aside">
          The physical design tab needs no account — it runs entirely in this browser.
        </p>
        <Link className="sim-button sim-button--primary" to="/login">
          Sign in
        </Link>
      </section>
    );
  }

  if (status !== "ready") {
    return (
      <section className="sim-gate">
        <h2>Provision a simulated device</h2>
        <p>
          The simulator authenticates exactly as the physical glasses would, with a device token
          rather than your login. Registering one here creates a real device on your account and
          hands this browser tab its token for the session.
        </p>
        {existingCount !== null && existingCount > 0 && (
          <p className="sim-gate__aside">
            You already have {existingCount} device{existingCount === 1 ? "" : "s"} registered. A
            device token is only ever shown once, at registration, so a fresh one is created for
            this session rather than reusing an old device you no longer hold the token for.
          </p>
        )}
        <button
          type="button"
          className="sim-button sim-button--primary"
          onClick={provision}
          disabled={status === "provisioning"}
        >
          {status === "provisioning" ? "Registering…" : "Register simulated glasses"}
        </button>
        {error && <p className="sim-error">{error}</p>}
      </section>
    );
  }

  return (
    <section className="sim-demo">
      <p className="sim-demo__device">
        Running as <strong>{deviceName}</strong> · authenticated with a device token, not your
        login
      </p>
      <PhoneDemo deviceToken={deviceToken} />
    </section>
  );
}
