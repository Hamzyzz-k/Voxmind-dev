# VoxMind — Account & API Key Setup

None of this needs to happen before you start reading code or running the backend
against the Firebase emulators — but the LLM, TTS, and OTP-email pieces stay honestly
disabled (clear error responses, no fake data) until you complete the relevant section
below. Do these in any order; each section says what it unlocks and ends with a way to
check you did it right before moving on.

Everything here stays within free tiers. The one exception — Cloud Text-to-Speech — is
called out explicitly in section 8 (a card is required on file, but you won't be charged
under the free quota).

Budget roughly 45–60 minutes to work through all nine sections the first time.

---

## 1. Google account

You just need one normal Google account. It's used for GCP, Firebase, and AI Studio —
all three share the same login, so there's nothing separate to sign up for here.

---

## 2. Create the GCP project

1. Open [console.cloud.google.com](https://console.cloud.google.com) in a browser,
   signed in with the Google account from step 1.
2. At the top of the page, click the **project picker** dropdown (it's next to the
   "Google Cloud" logo — it may currently say "Select a project" or show an existing
   project name).
3. In the dialog that opens, click **New Project** (top-right of the dialog).
4. Fill in:
   - **Project name**: something recognizable, e.g. `VoxMind`. Google will
     auto-generate a **Project ID** below it (e.g. `voxmind-504022`) — you can edit
     this ID before creating the project, but not after. Write it down; you'll paste
     it into `.env` files repeatedly.
   - **Organization** / **Location**: leave as default (`No organization`) unless your
     Google account is tied to a Workspace org.
5. Click **Create**. Wait for the notification bell (top-right) to show "Creating
   project..." finish — usually 10–30 seconds.
6. Once created, use the project picker again to **select** the new project so it's
   active (the project name should now appear in the top bar next to the logo).

**Verify:** the top bar shows your project name, and running `gcloud config get-value
project` (after section 4) prints your project ID.

**Note this down** — you'll need it repeatedly:
```
GCP / Firebase project ID: voxmind-504022
```

---

## 3. Add Firebase to the project

Firebase is a layer on top of the same GCP project — you're not creating a second
project, you're attaching Firebase services to the one from section 2.

1. Open [console.firebase.google.com](https://console.firebase.google.com).
2. Click **Add project** (or **Create a project**).
3. On the first screen, instead of typing a new name, click the dropdown / search box
   and select your **existing GCP project** from section 2 (it should appear in the
   list — this is what links Firebase to the same project ID instead of creating a
   separate one).
4. Click **Continue**. On the next screen, Google Analytics is optional — toggle it
   **off** unless you specifically want it (not needed for this project). Click
   **Create project** (or **Continue**), then **Continue** again once it's ready.

### 3a. Enable Email/Password authentication

1. In the left sidebar, under **Build**, click **Authentication**.
2. Click **Get started**.
3. You'll see a list of sign-in providers. Click **Email/Password**.
4. Toggle the first switch (**Email/Password**) to **enabled**. Leave "Email link
   (passwordless sign-in)" **off** — we're not using it.
5. Click **Save**.

*(We use our own custom email-OTP flow for MFA — see the main spec — not Firebase's
built-in multi-factor auth, so there's nothing else to configure here.)*

### 3b. Create the Firestore database

1. In the left sidebar, under **Build**, click **Firestore Database**.
2. Click **Create database**.
3. Choose **Native mode** (not "Datastore mode" — Native mode is the one the Admin SDK
   and these docs assume).
4. Pick a **location** — any region close to you or your teammates is fine (e.g.
   `asia-south1 (Mumbai)` if you're in India). This can't be changed later, but it
   doesn't otherwise affect this project functionally.
5. Under rules, leave the default (**production mode**, which starts locked-down) — the
   repo already ships its own `firestore.rules` (deny-all direct client access; the
   backend uses the Admin SDK, which bypasses these rules) that you'll deploy later with
   `firebase deploy --only firestore:rules`.
6. Click **Create**.

### 3c. Enable Hosting

1. In the left sidebar, under **Build**, click **Hosting**.
2. Click **Get started** and click through the three setup steps shown — you can skip
   actually running the `firebase init`/`deploy` commands shown there for now; we'll do
   the real deploy later once the frontend is ready. This step just flips Hosting on for
   the project.

### 3d. Register a Web app and get the client config

1. Click the **gear icon** next to "Project Overview" (top-left) → **Project settings**.
2. Scroll down to **Your apps**. Click the **web icon** (`</>`) to add a web app.
3. Give it a nickname (e.g. `voxmind-web`) — this is just a label, not user-facing.
   Leave "Also set up Firebase Hosting for this app" **unchecked** (already enabled
   above).
4. Click **Register app**. Firebase shows a `firebaseConfig` object like:
   ```js
   const firebaseConfig = {
     apiKey: "AIzaSy...",
     authDomain: "voxmind-472011.firebaseapp.com",
     projectId: "voxmind-472011",
     storageBucket: "voxmind-472011.appspot.com",
     messagingSenderId: "123456789012",
     appId: "1:123456789012:web:abcdef1234567890",
   };
   ```
5. Copy each value into `frontend/.env` (copy `frontend/.env.example` to `frontend/.env`
   first if you haven't):

   | Firebase config key | `.env` variable |
   |---|---|
   | `apiKey` | `VITE_FIREBASE_API_KEY` |
   | `authDomain` | `VITE_FIREBASE_AUTH_DOMAIN` |
   | `projectId` | `VITE_FIREBASE_PROJECT_ID` |
   | `storageBucket` | `VITE_FIREBASE_STORAGE_BUCKET` |
   | `messagingSenderId` | `VITE_FIREBASE_MESSAGING_SENDER_ID` |
   | `appId` | `VITE_FIREBASE_APP_ID` |
//// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyC0V9IQSbIdZdjGsu5VIknCB9jUBgvfYLA",
  authDomain: "voxmind-504022.firebaseapp.com",
  projectId: "voxmind-504022",
  storageBucket: "voxmind-504022.firebasestorage.app",
  messagingSenderId: "598470647922",
  appId: "1:598470647922:web:8ea4f6e59bfbf4010ae2eb"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
   This is public client config, not a secret — it's safe to ship inside the frontend
   bundle (Firebase enforces access via Auth + Firestore rules, not by hiding this).
6. Also set `VITE_USE_FIREBASE_EMULATOR=false` in `frontend/.env` once you actually want
   to point the app at this real project instead of the local emulators (leave it
   `true` while developing against `firebase emulators:start`).
7. Click **Continue to console** to finish.

**Verify:** `frontend/.env` has all six `VITE_FIREBASE_*` values filled in (no blanks),
and in the Firebase console, **Authentication → Sign-in method** shows Email/Password as
Enabled, **Firestore Database** shows an empty database ready to use, and **Hosting**
shows a `*.web.app` domain assigned.

**Unlocks:** real login/signup and Firestore reads/writes in production, once you also
flip `VITE_USE_FIREBASE_EMULATOR=false`.

---

## 4. Install the CLIs and authenticate locally

You need two command-line tools: the Firebase CLI (Node-based) and the Google Cloud CLI
(`gcloud`).

### 4a. Firebase CLI

```bash
npm install -g firebase-tools
firebase --version   # sanity check, should print a version number
firebase login
```

`firebase login` opens a browser window — sign in with the same Google account from
step 1 and click **Allow**. Back in the terminal you should see "Success! Logged in as
you@example.com".

### 4b. gcloud CLI

1. Install it from [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)
   (there's a Windows installer `.exe` — run it and accept the defaults; it'll open a
   new terminal/PowerShell window with `gcloud` on the PATH once done).
2. Then run:
   ```bash
   gcloud init
   ```
   Follow the prompts: log in (opens a browser, same Google account), then when asked
   "Pick cloud project to use", select the project from section 2 by its **project ID**.
3. Confirm the default project stuck:
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   gcloud config get-value project
   ```
4. Finally, set up Application Default Credentials — a **separate** login step from
   `gcloud init`, required for any code (like this backend) that uses Google client
   libraries locally:
   ```bash
   gcloud auth application-default login
   ```
   This opens another browser consent screen. Click **Allow**.

This last command is required even for **local development against the Firestore/Auth
emulators** — recent versions of the Admin SDK need a resolvable credential object just
to construct the client, even though it's never actually validated against the emulator.
It's free, doesn't touch billing, and only needs to be run once per machine (each
teammate needs to run it once on their own machine, not just you).

**Verify:**
```bash
gcloud auth list                       # shows your account as ACTIVE
gcloud auth application-default print-access-token   # prints a long token string, no error
```

**Unlocks:** `firebase emulators:start` and the backend working together locally;
later, `firebase deploy` and `gcloud run deploy`.

---

## 5. Groq API key (primary LLM)

1. Go to [console.groq.com](https://console.groq.com).
2. Sign in (Google sign-in is offered, or email).
3. In the left sidebar, click **API Keys**.
4. Click **Create API Key**. Give it a name (e.g. `voxmind-dev`). Click **Submit**.
5. Groq shows the key **once** — click the copy icon immediately. If you navigate away
   before copying it, you'll have to delete it and create a new one.
6. Open `backend/.env` (copy from `backend/.env.example` first if you haven't) and set:
   ```
   GROQ_API_KEY=gsk_your_real_key_here
   ```

No credit card or billing setup is needed — Groq's free tier covers this comfortably
for a class project.

**Verify** (paste your real key in place of `YOUR_KEY` — don't leave it in any file
other than `backend/.env`, which is gitignored):

macOS/Linux/Git Bash:
```bash
curl -s https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer YOUR_KEY" | head -c 200
```

Windows PowerShell:
```powershell
Invoke-RestMethod -Uri "https://api.groq.com/openai/v1/models" `
  -Headers @{ Authorization = "Bearer YOUR_KEY" }
```
(PowerShell's `curl`/`curl.exe` distinction and `$VAR` syntax differ from bash, so the
bash one-liner above will error even with a valid key — use `Invoke-RestMethod` instead.)

Either way this should print JSON (a list of models), not an auth error.

**Unlocks:** `/chat/ask` responses via Llama 3.3 70B.

---

## 6. Gemini API key (fallback LLM)

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey). This
   is **Google AI Studio** — a separate, simpler product from **Vertex AI**; don't use
   the Vertex AI console for this, the spec specifically calls for the AI Studio key.
2. If prompted, accept the terms of service.
3. Click **Create API key**.
4. In the dialog, choose **Create API key in existing project** and select the GCP
   project from section 2 (keeps everything under one project ID; you can also let it
   create a new project, but that adds a second project ID to keep track of, so existing
   project is simpler here).
5. Copy the generated key (starts with `AIza...`).
6. In `backend/.env`, set:
   ```
   GEMINI_API_KEY=your_real_key_here
   ```

No billing account is needed for the AI Studio free tier. One thing worth knowing: on
the free tier, Google's terms allow them to use submitted prompts to improve their
models (the paid tier opts out of this) — completely fine for a class demo, just don't
feed it real sensitive personal data during testing.

**Verify** (paste your real key in place of `YOUR_KEY`):

macOS/Linux/Git Bash:
```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY" | head -c 200
```

Windows PowerShell:
```powershell
Invoke-RestMethod -Uri "https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY"
```

Either way this should print JSON (a list of models), not an error about an invalid key.
A key that's valid but tied to the wrong product (e.g. a Vertex AI credential instead of
an AI Studio key) will also fail here — make sure you generated it from
[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey), not the GCP
Vertex AI console.

**Unlocks:** automatic fallback to Gemini 2.5 Flash when Groq errors or rate-limits.

---

## 7. SMTP provider (OTP emails)

Pick **one** of these two options.

### Option A — Gmail App Password (fastest for a demo)

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security) on the
   Gmail account you want to send OTP emails from (can be your personal account or a
   throwaway one made for the project).
2. Under "How you sign in to Google", make sure **2-Step Verification** is turned **on**
   (App Passwords only appear once 2FA is enabled). If it's off, click it and follow the
   prompts to enable it (you'll need your phone).
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   directly (Google sometimes buries this link under Security → 2-Step Verification →
   scroll to the bottom → App passwords).
4. Under "App name", type something like `VoxMind` and click **Create**.
5. Google shows a 16-character password in a yellow box (spaces don't matter, e.g.
   `abcd efgh ijkl mnop`). Copy it — you won't be able to see it again.
6. In `backend/.env`:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=youraccount@gmail.com
   SMTP_PASSWORD=abcdefghijklmnop   # the 16-char app password, spaces removed
   SMTP_FROM=youraccount@gmail.com
   ```

### Option B — Brevo (free tier: 300 emails/day, no personal Gmail involved)

1. Sign up at [app.brevo.com](https://app.brevo.com) (free plan, no card required).
2. Verify your email address (check your inbox for a confirmation link).
3. Once logged in, click your account name (top-right) → **SMTP & API**.
4. Click the **SMTP** tab (not "API Keys" — we want SMTP credentials specifically).
5. Note the **SMTP server** (`smtp-relay.brevo.com`) and **port** (`587`). Brevo also
   shows a **Login** value here — this is *not* your account email, it's a
   system-generated identifier that looks like `1234ab001@smtp-brevo.com`. That's
   correct and expected; it's used only to authenticate the SMTP connection. Click
   **Generate a new SMTP key** to get the password value (shown once — copy it
   immediately).
6. Separately, the **From** address has to be a sender Brevo has verified for you —
   it's a different concept from the SMTP login above. Go to **Senders, Domains &
   Dedicated IPs → Senders**. The email address you signed up to Brevo with is usually
   already listed there as verified; if not, click **Add a sender**, enter an address
   you control, and click the confirmation link Brevo emails to it. Use *that* verified
   address as `SMTP_FROM` — not the `@smtp-brevo.com` login string.
7. In `backend/.env`:
   ```
   SMTP_HOST=smtp-relay.brevo.com
   SMTP_PORT=587
   SMTP_USER=1234ab001@smtp-brevo.com   # the system login from step 5 — used for auth only
   SMTP_PASSWORD=<the generated SMTP key>
   SMTP_FROM=you@example.com            # your verified sender from step 6, NOT the login
   ```

**Verify** — the fastest check doesn't need the full backend/Firebase flow, just a
direct SMTP send using the credentials you just put in `.env`. There's a small helper
script for this: `backend/scripts/verify_smtp.py`. Run it from the `backend/` folder:

Windows PowerShell:
```powershell
cd backend
.venv\Scripts\python.exe scripts\verify_smtp.py you@example.com
```

macOS/Linux/Git Bash:
```bash
cd backend
./.venv/bin/python scripts/verify_smtp.py you@example.com
```

(replace `you@example.com` with an address you can actually check). If it raises
instead of printing "Sent", the exception message will say what's wrong (bad auth,
unverified sender, etc.). Also check Brevo's dashboard under **Transactional → Email →
Logs** — that's the authoritative place to see whether Brevo accepted, delivered, or
blocked it, even if the script itself reports success.

Once that works, you can also verify end-to-end through the actual API: with the
backend running and `backend/.env` filled in, call `POST /auth/otp/request` with a
valid Firebase ID token (see the README's local dev section) and confirm the email
lands, instead of getting a 503.

**Unlocks:** `/auth/otp/request` actually sending an email instead of returning an
honest 503 ("email delivery not configured yet").

---

## 8. Cloud Text-to-Speech (spoken responses) — needs a billing account

1. In [console.cloud.google.com](https://console.cloud.google.com), make sure the right
   project is selected in the top bar (from section 2).
2. In the left sidebar (or search bar at the top), go to **APIs & Services** → **Library**.
3. Search for `Cloud Text-to-Speech API` and click it.
4. Click **Enable**.
5. If you see a prompt to link billing, click **Billing** in the left sidebar (or you'll
   be redirected automatically) → **Link a billing account** → **Create billing
   account** (or select an existing one if you already have one) → follow the prompts to
   add a card.

   This is the **only** place in this whole setup where a card is required. Cloud
   Text-to-Speech is on Google's **Always Free** monthly list (1 million WaveNet
   characters free every month), but the API itself refuses to turn on for a project
   with no billing account attached at all — even though you'll stay at $0 under normal
   class-project usage.

   To be extra safe, set a budget alert: **Billing** → **Budgets & alerts** → **Create
   budget** → set a small amount (e.g. ₹100 / $1) so you get an email if anything
   unexpected happens.
6. No separate API key is needed for this one — the backend authenticates the same way
   as Firestore: via `gcloud auth application-default login` locally (section 4b), and
   automatically via the Cloud Run service's attached service account once deployed.

**Verify:**
```bash
gcloud services list --enabled | grep texttospeech
```
should print a line for `texttospeech.googleapis.com`.

**Unlocks:** `audio_base64` actually being populated in `/chat/ask` responses, instead
of text-only replies with an `audio_error` message.

---

## 9. Secret Manager (for production deployment only — skip for now)

Not needed for local dev — `backend/.env` handles secrets there, and it's gitignored.
This section is only relevant once we're ready to deploy the backend to Cloud Run;
come back to it then rather than doing it now.

```bash
gcloud services enable secretmanager.googleapis.com

echo -n "your-groq-key" | gcloud secrets create GROQ_API_KEY --data-file=-
echo -n "your-gemini-key" | gcloud secrets create GEMINI_API_KEY --data-file=-
echo -n "your-smtp-password" | gcloud secrets create SMTP_PASSWORD --data-file=-
```

We'll wire these into the Cloud Run service with `--set-secrets` at actual deploy time —
happy to hand you the exact `gcloud run deploy` command then, once we're at that step.

---

## Summary checklist

- [ ] GCP project created (section 2) — project ID noted down
- [ ] Firebase linked to that project (3), Email/Password auth enabled (3a), Firestore
      Native-mode database created (3b), Hosting enabled (3c)
- [ ] Web app registered, all 6 `VITE_FIREBASE_*` values in `frontend/.env` (3d)
- [ ] `firebase login` done (4a)
- [ ] `gcloud init` + `gcloud auth application-default login` done (4b) — **every**
      teammate needs to run this once on their own machine
- [ ] `GROQ_API_KEY` in `backend/.env`, verified with curl (5)
- [ ] `GEMINI_API_KEY` in `backend/.env`, verified with curl (6)
- [ ] SMTP credentials in `backend/.env`, test email confirmed received (7)
- [ ] Cloud Text-to-Speech API enabled, billing account attached, budget alert set (8)
- [ ] *(Later, at deploy time only)* Secrets pushed to Secret Manager (9)
