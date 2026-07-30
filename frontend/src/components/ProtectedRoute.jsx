import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function ProtectedRoute({ children, requireMfa = true }) {
  const { user, authLoading, mfaVerified, mfaChecked } = useAuth();

  if (authLoading || (user && !mfaChecked)) {
    return <div className="screen-center">Loading…</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (requireMfa && !mfaVerified) {
    return <Navigate to="/otp" replace />;
  }
  return children;
}
