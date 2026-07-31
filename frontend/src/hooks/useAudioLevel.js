import { useEffect, useRef, useState } from "react";
import { readLevel } from "../services/audioLevel";

/** Samples the shared analyser once per animation frame while `active`.
 *
 * Throttled to ~20 updates/sec rather than every frame: MagicRings re-renders a
 * WebGL scene on prop change, and driving that at 60fps from React state burns
 * far more CPU than the visual gain justifies. The level is also smoothed so
 * the rings ease between values instead of snapping.
 */
export function useAudioLevel(active) {
  const [level, setLevel] = useState(0);
  const rafRef = useRef(null);
  const smoothedRef = useRef(0);
  const lastEmitRef = useRef(0);

  useEffect(() => {
    if (!active) {
      // Ease back to rest rather than cutting to zero.
      smoothedRef.current = 0;
      setLevel(0);
      return undefined;
    }

    const EMIT_INTERVAL_MS = 50;

    const tick = (now) => {
      const raw = readLevel();
      // Asymmetric smoothing: rise quickly with the voice, fall gently.
      const k = raw > smoothedRef.current ? 0.35 : 0.12;
      smoothedRef.current += (raw - smoothedRef.current) * k;

      if (now - lastEmitRef.current >= EMIT_INTERVAL_MS) {
        lastEmitRef.current = now;
        setLevel(Math.round(smoothedRef.current * 100) / 100);
      }
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [active]);

  return level;
}
