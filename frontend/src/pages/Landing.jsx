import { Link } from "react-router-dom";
import { LazyLiquidEther, LazyScrollReveal } from "../components/LazyVisuals";
import ClickSpark from "../reactbits/ClickSpark";
import FuzzyText from "../reactbits/FuzzyText";
import { useAuth } from "../context/AuthContext";

// Module-level so the array identity is stable across renders. LiquidEther
// lists `colors` in its main effect's dependency array, so a fresh array on
// every render would tear down and rebuild the entire WebGL context, its FBOs
// and every shader pass each time — the same reason AUTH_ITEMS is hoisted in
// Auth.jsx.
const ETHER_COLORS = ["#D856BF", "#03B3C3", "#6750A2"];
const ETHER_LAYER = { position: "fixed", inset: 0, zIndex: -1 };
const TITLE_GRADIENT = ["#D856BF", "#03B3C3"];

// ScrollReveal only splits plain strings (`typeof children === 'string'`), so
// this has to stay one string with no nested markup.
const INTRO = `VoxMind is a voice assistant that listens in English, Hindi, Kannada and Tamil. Hold the mic, speak naturally, and it answers out loud — remembering who you are and what you talked about last time.`;

export default function Landing() {
  const { user, mfaVerified } = useAuth();
  const signedIn = Boolean(user) && mfaVerified;

  return (
    <div className="landing">
      <div style={ETHER_LAYER}>
        <LazyLiquidEther
          colors={ETHER_COLORS}
          mouseForce={20}
          cursorSize={100}
          resolution={0.5}
          autoDemo
          autoSpeed={0.4}
          autoIntensity={1.8}
        />
      </div>

      <section className="landing-hero">
        <div className="landing-title">
          <FuzzyText
            color="#FFFFFF"
            gradient={TITLE_GRADIENT}
            baseIntensity={0.15}
            hoverIntensity={0.35}
            enableHover
            /* Explicit, never "inherit" — inherit reads a computed style that
               doesn't exist yet on StrictMode's first pass, producing an
               invalid ctx.font and a 10px fallback render. */
            fontFamily="system-ui, -apple-system, Segoe UI, sans-serif"
          >
            VoxMind
          </FuzzyText>
        </div>

        <p className="landing-tagline">Speak. It listens, remembers, and answers.</p>

        <div className="spark-wrap">
          <ClickSpark sparkColor="#03B3C3" sparkSize={10} sparkRadius={15} sparkCount={8} duration={400}>
            <Link className="btn-primary landing-cta" to={signedIn ? "/home" : "/login"}>
              {signedIn ? "Continue to VoxMind" : "Get Started"}
            </Link>
          </ClickSpark>
        </div>

        <span className="landing-scroll-hint" aria-hidden="true">
          Scroll
        </span>
      </section>

      {/* Below the fold on purpose. ScrollReveal is scrub-driven from
          baseOpacity 0.1 — with nothing to scroll its words never animate in
          and the copy sits permanently at 10% opacity. */}
      <section className="landing-intro">
        <LazyScrollReveal enableBlur baseOpacity={0.1} baseRotation={3} blurStrength={4}>
          {INTRO}
        </LazyScrollReveal>
      </section>

      <footer className="landing-footer">
        <Link className="landing-link" to={signedIn ? "/home" : "/login"}>
          {signedIn ? "Continue to VoxMind →" : "Sign in or create an account →"}
        </Link>
      </footer>
    </div>
  );
}
