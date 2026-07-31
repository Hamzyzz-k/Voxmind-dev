import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LazyHyperspeed } from "../components/LazyVisuals";

/** Full-screen Hyperspeed transition, played once after OTP verification and
 *  cross-dissolved into the chat page. */

// Module-level constant, not an inline object: the component rebuilds its
// entire WebGL scene whenever this prop's identity changes.
const EFFECT_OPTIONS = {
  distortion: "turbulentDistortion",
  length: 400,
  roadWidth: 10,
  islandWidth: 2,
  lanesPerRoad: 3,
  fov: 90,
  fovSpeedUp: 150,
  speedUp: 2,
  carLightsFade: 0.4,
  totalSideLightSticks: 20,
  lightPairsPerRoadWay: 40,
  colors: {
    roadColor: 0x080808,
    islandColor: 0x0a0a0a,
    background: 0x000000,
    shoulderLines: 0xffffff,
    brokenLines: 0xffffff,
    leftCars: [0xd856bf, 0x6750a2, 0xc247ac],
    rightCars: [0x03b3c3, 0x0e5ea5, 0x324555],
    sticks: 0x03b3c3,
  },
};

const HOLD_MS = 2600; // time the effect is fully visible
const FADE_MS = 800; // cross-dissolve out

export default function Entering() {
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const fadeTimer = setTimeout(() => setLeaving(true), HOLD_MS);
    const navTimer = setTimeout(() => navigate("/home", { replace: true }), HOLD_MS + FADE_MS);
    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(navTimer);
    };
  }, [navigate]);

  return (
    <div className={`hyperspeed-overlay${leaving ? " leaving" : ""}`}>
      <LazyHyperspeed effectOptions={EFFECT_OPTIONS} />
    </div>
  );
}
