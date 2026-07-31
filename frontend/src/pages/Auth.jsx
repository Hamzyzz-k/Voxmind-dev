import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import ElectricBorder from "../reactbits/ElectricBorder";
import FuzzyText from "../reactbits/FuzzyText";
import GooeyNav from "../reactbits/GooeyNav";
import { useAuth } from "../context/AuthContext";

// Module-level so the array identity is stable across renders.
const AUTH_ITEMS = [
  { label: "Sign In", href: "#signin" },
  { label: "Sign Up", href: "#signup" },
];
const GOOEY_COLORS = [1, 2, 3, 1];
const TITLE_GRADIENT = ["#D856BF", "#03B3C3"];

export default function Auth() {
  const { login, signup } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState("signin"); // signin | signup
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const isSignup = mode === "signup";

  const handleModeChange = useCallback((index) => {
    setMode(index === 0 ? "signin" : "signup");
    setError(null);
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (isSignup && password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      if (isSignup) {
        await signup(email, password);
      } else {
        await login(email, password);
      }
      navigate("/otp");
    } catch (err) {
      setError(err.message || (isSignup ? "Could not create account." : "Could not sign in."));
    } finally {
      setSubmitting(false);
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

      <GooeyNav items={AUTH_ITEMS} colors={GOOEY_COLORS} onChange={handleModeChange} />

      <ElectricBorder
        color="#03B3C3"
        speed={1}
        chaos={0.12}
        thickness={2}
        borderRadius={16}
        style={{ borderRadius: 16, width: "100%", maxWidth: 380 }}
      >
        <div className="auth-card">
          <form className="auth-form" onSubmit={handleSubmit}>
            <h2>{isSignup ? "Create your account" : "Welcome back"}</h2>

            <input
              type="email"
              placeholder="Email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <input
              type="password"
              placeholder="Password"
              autoComplete={isSignup ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={6}
              required
            />
            {isSignup && (
              <input
                type="password"
                placeholder="Confirm password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                minLength={6}
                required
              />
            )}

            {error && <p className="form-error">{error}</p>}

            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting
                ? isSignup
                  ? "Creating account…"
                  : "Signing in…"
                : isSignup
                  ? "Sign Up"
                  : "Sign In"}
            </button>
          </form>
        </div>
      </ElectricBorder>
    </div>
  );
}
