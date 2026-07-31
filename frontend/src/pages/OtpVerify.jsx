import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import ElectricBorder from "../reactbits/ElectricBorder";
import FuzzyText from "../reactbits/FuzzyText";
import { useAuth } from "../context/AuthContext";
import { api } from "../services/api";

const TITLE_GRADIENT = ["#D856BF", "#03B3C3"];

export default function OtpVerify() {
  const { mfaVerified, checkMfaStatus, logout } = useAuth();
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [sendState, setSendState] = useState("idle"); // idle | sending | sent | error
  const [sendMessage, setSendMessage] = useState(null);
  const [verifyError, setVerifyError] = useState(null);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    handleSendCode();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (mfaVerified) {
    // Route through the transition rather than straight to chat, so the
    // Hyperspeed sequence plays once on entering the app.
    return <Navigate to="/entering" replace />;
  }

  async function handleSendCode() {
    setSendState("sending");
    setSendMessage(null);
    try {
      const res = await api.post("/auth/otp/request");
      setSendState("sent");
      setSendMessage(`Code sent to your email. It expires in ${Math.round(res.expires_in_seconds / 60)} minutes.`);
    } catch (err) {
      setSendState("error");
      setSendMessage(err.message || "Could not send the verification code.");
    }
  }

  async function handleVerify(e) {
    e.preventDefault();
    setVerifyError(null);
    setVerifying(true);
    try {
      await api.post("/auth/otp/verify", { code });
      await checkMfaStatus();
      navigate("/entering");
    } catch (err) {
      setVerifyError(err.message || "Verification failed.");
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-title">
        <FuzzyText
          color="#FFFFFF"
          gradient={TITLE_GRADIENT}
          baseIntensity={0.15}
          hoverIntensity={0.35}
          enableHover
          /* Explicit rather than "inherit": inherit reads the canvas's computed
             style, which isn't available yet on the first effect pass under
             StrictMode, producing an invalid ctx.font and a 10px fallback. */
          fontFamily="system-ui, -apple-system, Segoe UI, sans-serif"
        >
          VoxMind
        </FuzzyText>
      </div>

      <ElectricBorder
        color="#03B3C3"
        speed={1}
        chaos={0.12}
        thickness={2}
        borderRadius={16}
        style={{ borderRadius: 16, width: "100%", maxWidth: 380 }}
      >
        <div className="auth-card">
          <form className="auth-form" onSubmit={handleVerify}>
            <h2>Check your email</h2>
            {sendMessage && <p className="form-hint">{sendMessage}</p>}

            <input
              type="text"
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              placeholder="6-digit code"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              required
            />

            {verifyError && <p className="form-error">{verifyError}</p>}

            <button type="submit" className="btn-primary" disabled={verifying || code.length !== 6}>
              {verifying ? "Verifying…" : "Verify"}
            </button>
            <button
              type="button"
              className="btn-ghost"
              onClick={handleSendCode}
              disabled={sendState === "sending"}
            >
              {sendState === "sending" ? "Sending…" : "Resend code"}
            </button>

            <p className="form-hint">
              Wrong account?{" "}
              <button type="button" className="link-button" onClick={logout}>
                Log out
              </button>
            </p>
          </form>
        </div>
      </ElectricBorder>
    </div>
  );
}
