import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import Auth from "./pages/Auth";
import Entering from "./pages/Entering";
import Home from "./pages/Home";
import OtpVerify from "./pages/OtpVerify";

function App() {
  return (
    <Routes>
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
      <Route path="/" element={<Navigate to="/home" replace />} />
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}

export default App;
