/** Turns a Firebase Auth error into something a person can act on.
 *
 * Firebase's own `.message` reads like `"Firebase: Error (auth/invalid-
 * credential)."` — the SDK's internal error code, not a sentence written for
 * a user. Every other error surface in this app (mic errors, chat errors,
 * device errors) is a short plain-English sentence; login/signup were the
 * one place still leaking a raw SDK string, because Auth.jsx's catch block
 * fell straight through to `err.message` with nothing translating it first.
 *
 * Deliberately vague on credential errors specifically: `auth/invalid-
 * credential` covers both "no such account" and "wrong password" in current
 * Firebase versions (folded together on purpose, to stop a login form
 * confirming which emails have accounts), and older SDK behaviour or edge
 * cases can still surface `auth/user-not-found` / `auth/wrong-password`
 * separately — both map to the same one message here, for the same reason
 * Firebase folded them together upstream.
 */
const MESSAGES = {
  "auth/invalid-credential": "Incorrect email or password.",
  "auth/wrong-password": "Incorrect email or password.",
  "auth/user-not-found": "Incorrect email or password.",
  "auth/invalid-email": "That doesn't look like a valid email address.",
  "auth/missing-password": "Enter a password.",
  "auth/weak-password": "Use a password with at least 6 characters.",
  "auth/email-already-in-use": "An account with that email already exists — try signing in instead.",
  "auth/user-disabled": "This account has been disabled.",
  "auth/too-many-requests": "Too many attempts. Wait a moment before trying again.",
  "auth/network-request-failed": "Couldn't reach the server. Check your connection and try again.",
  "auth/popup-closed-by-user": "Sign-in was closed before it finished.",
};

/** `fallback` is chosen by the caller (different verbs for sign in vs sign
 * up), so a code this map has never seen still reads as a sentence about
 * what was being attempted, not a generic "something went wrong". */
export function describeAuthError(error, fallback) {
  return MESSAGES[error?.code] || fallback;
}
