import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import Auth from "./pages/Auth";
import Entering from "./pages/Entering";
import Home from "./pages/Home";
import Landing from "./pages/Landing";
import OtpVerify from "./pages/OtpVerify";

// Lazy, unlike every other route here, because this one pulls in three.js.
// Imported eagerly it lands in the main bundle and every visitor downloads
// roughly 700KB of 3D engine to read the landing page — on the mobile
// connections this app is actually used on, that is the difference between a
// fast first paint and a blank screen. Only /simulator pays for it now.
const Simulator = lazy(() => import("./pages/Simulator"));

function App() {
  return (
    <Routes>
      {/* Public front door — explains what VoxMind is before asking for an
          account. Signed-in visitors get a link straight through to /home. */}
      <Route path="/" element={<Landing />} />
      {/* Deliberately public, and deliberately not inside ProtectedRoute. Its
          3D design view runs entirely in the browser, so a reviewer can open
          the link on their own device and inspect the hardware without an
          account. The live-demonstration tab inside it gates itself, because
          that half does talk to the backend. */}
      <Route
        path="/simulator"
        element={
          <Suspense fallback={<div className="sim-loading">Loading the simulator…</div>}>
            <Simulator />
          </Suspense>
        }
      />
      {/* Sign in and sign up share one screen, toggled by GooeyNav. */}
      <Route path="/login" element={<Auth />} />
      <Route path="/signup" element={<Navigate to="/login" replace />} />
      <Route
        path="/otp"
        element={
          <ProtectedRoute requireMfa={false}>
            <OtpVerify />
          </ProtectedRoute>
        }
      />
      {/* Hyperspeed transition between finishing auth and the chat page. */}
      <Route
        path="/entering"
        element={
          <ProtectedRoute>
            <Entering />
          </ProtectedRoute>
        }
      />
      <Route
        path="/home"
        element={
          <ProtectedRoute>
            <Home />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}

export default App;
