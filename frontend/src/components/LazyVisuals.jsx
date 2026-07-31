import { Suspense, lazy } from "react";

/** Lazy wrappers for the WebGL-heavy React Bits components.
 *
 * three, postprocessing and face-api.js together are ~1.5MB — most of the app's
 * weight. Imported statically they land in the initial bundle, so the login
 * screen would download the entire 3D stack before it could render an email
 * field. Splitting them keeps auth light and defers the cost to the screens that
 * actually draw something.
 *
 * Fallbacks are empty rather than spinners: each of these renders inside an
 * already-positioned container, and a placeholder would only flash.
 */

const HyperspeedInner = lazy(() => import("../reactbits/Hyperspeed"));
const MagicRingsInner = lazy(() => import("../reactbits/MagicRings"));
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

export function LazyGridScan(props) {
  return (
    <Suspense fallback={null}>
      <GridScanInner {...props} />
    </Suspense>
  );
}
