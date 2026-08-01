import { Suspense, lazy } from "react";

/** Lazy wrappers for the heavyweight React Bits components.
 *
 * three, postprocessing and face-api.js together are ~1.5MB — most of the app's
 * weight. Imported statically they land in the initial bundle, so the login
 * screen would download the entire 3D stack before it could render an email
 * field. Splitting them keeps auth light and defers the cost to the screens that
 * actually draw something. ScrollReveal is here for the same reason rather than
 * for WebGL: it pulls in gsap plus ScrollTrigger, which measurably fattened the
 * entry chunk when imported directly.
 *
 * Fallbacks are empty rather than spinners: each of these renders inside an
 * already-positioned container, and a placeholder would only flash.
 */

const HyperspeedInner = lazy(() => import("../reactbits/Hyperspeed"));
const MagicRingsInner = lazy(() => import("../reactbits/MagicRings"));
const LiquidEtherInner = lazy(() => import("../reactbits/LiquidEther"));
const ScrollRevealInner = lazy(() => import("../reactbits/ScrollReveal"));
const GridScanInner = lazy(() =>
  // GridScan is a named export; normalise it to a default for lazy().
  import("../reactbits/GridScan").then((m) => ({ default: m.GridScan })),
);

export function LazyHyperspeed(props) {
  return (
    <Suspense fallback={null}>
      <HyperspeedInner {...props} />
    </Suspense>
  );
}

export function LazyMagicRings(props) {
  return (
    <Suspense fallback={null}>
      <MagicRingsInner {...props} />
    </Suspense>
  );
}

/** The landing page is the first thing every visitor loads, so this one matters
 * most: imported eagerly it would put all of three.js back on the critical path
 * — exactly what splitting these out removed. The copy and the call to action
 * render immediately; the fluid simulation arrives behind them. */
export function LazyLiquidEther(props) {
  return (
    <Suspense fallback={null}>
      <LiquidEtherInner {...props} />
    </Suspense>
  );
}

export function LazyScrollReveal(props) {
  return (
    <Suspense fallback={null}>
      <ScrollRevealInner {...props} />
    </Suspense>
  );
}

export function LazyGridScan(props) {
  return (
    <Suspense fallback={null}>
      <GridScanInner {...props} />
    </Suspense>
  );
}
