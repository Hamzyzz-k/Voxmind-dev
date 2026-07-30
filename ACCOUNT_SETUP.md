# VoxMind — Account & API Key Setup

None of this needs to happen before you start reading code or running the backend
against the Firebase emulators — but the LLM, TTS, and OTP-email pieces stay honestly
disabled (clear error responses, no fake data) until you complete the relevant section
below. Do these in any order; each section says what it unlocks.

Everything here stays within free tiers. The one exception — Cloud Text-to-Speech — is
called out explicitly in step 6.

## 1. Google account

You just need a normal Google account for everything below (GCP, Firebase, AI Studio all
use the same login).

## 2. Create the GCP project

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → create a new
   project (e.g. `voxmind-prod`). Note the **project ID** (not the display name).
2. This project ID will be used for both Firebase and Cloud Run — same project, not two
   separate ones.

## 3. Add Firebase to the project

1. Go to [console.firebase.google.com](https://console.firebase.google.com) → "Add
   project" → choose the GCP project you just created (don't create a new one here).
2. **Authentication**: Build → Authentication → Get started → enable **Email/Password**
   sign-in provider. (We use custom email OTP for MFA, not Firebase's native MFA — no
   extra setup needed there.)
3. **Firestore**: Build → Firestore Database → Create database → **Native mode** → pick
   a region close to you.
4. **Hosting**: Build → Hosting → Get started (just acknowledges Hosting is enabled; the
   actual deploy happens later via CLI).
5. Project settings (gear icon) → General → "Your apps" → Add app → Web app. Copy the
   config values (`apiKey`, `authDomain`, `projectId`, etc.) into `frontend/.env` —
   this is public config, safe to expose in the frontend bundle.

**Unlocks:** real login/signup (once you also point the frontend at the real project
instead of `demo-voxmind` + emulators) and Firestore writes in production.

## 4. Install the CLIs and authenticate locally

```bash
npm install -g firebase-tools
firebase login

# Install the gcloud CLI: https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default login
```

The last command is required even for **local development against the emulators** — the
Admin SDK needs a resolvable credential object to initialize, even though it doesn't
validate it against emulator calls. It's free and only needs to be run once.

**Unlocks:** `firebase emulators:start` working with the Admin SDK; later, `firebase
deploy` and `gcloud run deploy`.

## 5. Groq API key (primary LLM)

1. Go to [console.groq.com](https://console.groq.com) → sign in → API Keys → Create key.
2. Put it in `backend/.env` as `GROQ_API_KEY`. Free tier, no billing account needed.

**Unlocks:** `/chat/ask` responses via Llama 3.3 70B.

## 6. Gemini API key (fallback LLM)

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) (this
   is **Google AI Studio**, not Vertex AI) → Create API key → attach it to the same GCP
   project from step 2.
2. Put it in `backend/.env` as `GEMINI_API_KEY`. Free tier, no billing account needed.
   Note: on the free tier, Google may use submitted prompts to improve their models —
   fine for a class demo, just don't feed it real sensitive data.

**Unlocks:** automatic fallback when Groq errors or rate-limits.

## 7. SMTP provider (OTP emails)

Pick one — both are free and take a few minutes:

**Option A — Gmail App Password (simplest for a demo)**
1. Enable 2-Step Verification on the Gmail account you'll send from:
   [myaccount.google.com/security](https://myaccount.google.com/security).
2. Create an App Password: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. In `backend/.env`: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER=you@gmail.com`,
   `SMTP_PASSWORD=<the 16-char app password>`, `SMTP_FROM=you@gmail.com`.

**Option B — Brevo (formerly Sendinblue), 300 emails/day free**
1. Sign up at [app.brevo.com](https://app.brevo.com) → Settings → SMTP & API → SMTP tab.
2. Use the generated SMTP credentials in `backend/.env` (`SMTP_HOST=smtp-relay.brevo.com`, etc.).

**Unlocks:** `/auth/otp/request` actually sending an email instead of returning a 503.

## 8. Cloud Text-to-Speech (spoken responses) — needs a billing account

1. In the GCP console: APIs & Services → Library → search "Cloud Text-to-Speech API" →
   Enable.
2. If prompted, link a **billing account** (Billing → Link a billing account → add a
   card). This is the one place a card is required — Cloud TTS is on Google's
   **Always Free** list (1M WaveNet characters/month), but the API itself won't turn on
   without billing attached, even if you stay at $0. Consider setting a budget alert
   (Billing → Budgets & alerts) for peace of mind.
3. No separate API key needed — the backend authenticates via the same
   `gcloud auth application-default login` credential locally, and via the Cloud Run
   service's attached service account in production.

**Unlocks:** `audio_base64` in `/chat/ask` responses instead of text-only + `audio_error`.

## 9. Secret Manager (for production deployment only)

Not needed for local dev (`.env` handles that). Before deploying to Cloud Run:

```bash
gcloud services enable secretmanager.googleapis.com

echo -n "your-groq-key" | gcloud secrets create GROQ_API_KEY --data-file=-
echo -n "your-gemini-key" | gcloud secrets create GEMINI_API_KEY --data-file=-
echo -n "your-smtp-password" | gcloud secrets create SMTP_PASSWORD --data-file=-
```

We'll wire these into the Cloud Run service with `--set-secrets` when we get to
deployment — happy to hand you the exact commands then, once the project actually
exists to target.

## Summary checklist

- [ ] GCP project created, Firebase linked
- [ ] Firebase Auth (Email/Password) + Firestore (Native mode) + Hosting enabled
- [ ] Firebase web config copied into `frontend/.env`
- [ ] `firebase login` + `gcloud auth application-default login` done locally
- [ ] Groq API key in `backend/.env`
- [ ] Gemini API key in `backend/.env`
- [ ] SMTP credentials in `backend/.env`
- [ ] Cloud Text-to-Speech API enabled (billing account attached)
- [ ] (Later, at deploy time) Secrets pushed to Secret Manager
