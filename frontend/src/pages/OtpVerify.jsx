import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../services/api";

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
    return <Navigate to="/home" replace />;
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
      navigate("/home");
    } catch (err) {
      setVerifyError(err.message || "Verification failed.");
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="screen-center">
      <form className="auth-form" onSubmit={handleVerify}>
        <h1>Check your email</h1>
        <p className="hint">{sendMessage}</p>
        <input
          type="text"
          inputMode="numeric"
          pattern="\d{6}"
          maxLength={6}
          placeholder="6-digit code"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          required
        />
        {verifyError && <p className="error">{verifyError}</p>}
        <button type="submit" disabled={verifying || code.length !== 6}>
          {verifying ? "Verifying…" : "Verify"}
        </button>
        <button type="button" onClick={handleSendCode} disabled={sendState === "sending"}>
          {sendState === "sending" ? "Sending…" : "Resend code"}
        </button>
        <p className="hint">
          Wrong account?{" "}
          <button type="button" onClick={logout} style={{ background: "none", color: "#4f46e5", padding: 0 }}>
            Log out
          </button>
        </p>
      </form>
    </div>
  );
}
