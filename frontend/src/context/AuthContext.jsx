import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
} from "firebase/auth";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { auth } from "../firebase";
import { api } from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [mfaVerified, setMfaVerified] = useState(false);
  const [mfaChecked, setMfaChecked] = useState(false);

  // The backend is the source of truth for MFA status (it checks
  // mfaVerifiedAt server-side on every request) — we ask it rather than
  // trusting a client-only flag, so a stale/expired session correctly
  // routes back to the OTP screen.
  const checkMfaStatus = useCallback(async () => {
    try {
      await api.get("/profile");
      setMfaVerified(true);
    } catch {
      setMfaVerified(false);
    } finally {
      setMfaChecked(true);
    }
  }, []);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      setUser(firebaseUser);
      setAuthLoading(false);
      setMfaChecked(false);
      setMfaVerified(false);
      if (firebaseUser) {
        await checkMfaStatus();
      } else {
        setMfaChecked(true);
      }
    });
    return unsubscribe;
  }, [checkMfaStatus]);

  const login = (email, password) => signInWithEmailAndPassword(auth, email, password);
  const signup = (email, password) => createUserWithEmailAndPassword(auth, email, password);
  const logout = () => firebaseSignOut(auth);

  const value = { user, authLoading, mfaVerified, mfaChecked, checkMfaStatus, login, signup, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
