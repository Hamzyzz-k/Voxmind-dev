# VoxMind — Deployment Guide

**Status: live.**

| | URL |
|---|---|
| Frontend | https://voxmind-504022.web.app |
| Backend | https://voxmind-api.onrender.com |
| Readiness probe | https://voxmind-api.onrender.com/readyz |

Frontend on **Firebase Hosting**, backend on **Render**. Both free, neither needs
a credit card.

Redeploying:
- **Backend** — push to `master`; Render rebuilds automatically.
- **Frontend** — `cd frontend && npm run build && firebase deploy --only hosting`
  from the repo root (needs `VITE_API_BASE_URL` set to the Render URL in
  `frontend/.env`).

## Why Render instead of Cloud Run

The spec names Cloud Run, but Cloud Run cannot be enabled without a billing
account linked to the GCP project — verified directly:

```
ERROR: FAILED_PRECONDITION: Billing account for project '598470647922' is not
found. Billing must be enabled for activation of service(s) 'run.googleapis.com'
```

This is the same wall that moved TTS off Google Cloud earlier. Render's free tier
needs no card. The backend ships as a plain Docker container, so if you ever add
billing, moving to Cloud Run is one `gcloud run deploy` — nothing below is
Render-specific.

**Free-tier tradeoff:** Render sleeps a free service after ~15 minutes idle, and
the next request takes ~30–50s to wake it. Before a live demo, load the site once
a minute beforehand so it's warm.

---

## What's already done

No action needed on these — they're finished and verified:

- Service account `voxmind-backend@voxmind-504022.iam.gserviceaccount.com` created,
  granted `roles/datastore.user` + `roles/firebaseauth.admin` (least privilege —
  no broader project access)
- Its key written to `backend/serviceAccountKey.json`, confirmed gitignored, and
  verified to work: a real Firestore read/write round-trip succeeded using only
  that key, with Application Default Credentials unavailable
- `render.yaml` blueprint committed
- `backend/.dockerignore` keeps `.env`, the key, and `.venv` out of the image
- Dockerfile runs as a non-root user
- Firestore security rules already deployed to the live project

---

## Step 1 — Push to GitHub

Render deploys from a Git repo, so this is a prerequisite rather than optional.

**1a.** Create an empty repo at [github.com/new](https://github.com/new):
- Name: `voxmind` (or anything)
- **Private** is fine — Render can access private repos once you authorize it
- **Do not** tick "Add a README", "Add .gitignore", or "Choose a license" —
  the repo already has these, and initializing them here causes a merge conflict
  on your first push

**1b.** Copy the repo URL GitHub shows you, then run these from
`C:\Users\HAMZAH\Documents\Voxmind` (replace the URL with yours):

```bash
git remote add origin https://github.com/YOUR-USERNAME/voxmind.git
git push -u origin master
```

If prompted to sign in, use the browser flow or a personal access token.

**Safety note:** the entire git history was scanned for secrets before this guide
was written. The only key present is the Firebase *web* API key, which is public
by design (Firebase secures access via Auth + Firestore rules, not by hiding it).
No Groq, Gemini, SMTP, or ElevenLabs key has ever been committed, and
`backend/.env` + `backend/serviceAccountKey.json` are both gitignored. Safe to
push, including publicly.

---

## Step 2 — Deploy the backend to Render

**2a.** Sign up at [render.com](https://render.com) — "Get Started" → **Sign in
with GitHub**. No card requested.

**2b.** In the Render dashboard: **Add new** → **Blueprint**.

**2c.** Connect your GitHub account, pick the `voxmind` repo. Render finds
`render.yaml` automatically and shows a service named `voxmind-api`. Click
**Apply** / **Create**.

**2d.** The first build takes ~5 minutes (installing ffmpeg + Python deps). It
will fail to start until you add the environment variables in the next step —
that's expected.

**2e.** Set the secret env vars. Go to the `voxmind-api` service → **Environment**
in the left sidebar. `render.yaml` pre-filled the non-secret ones; you need to
fill these seven, which were deliberately left out of the repo:

| Key | Where to get the value |
|---|---|
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Open `backend/serviceAccountKey.json`, copy the **entire file** including the outer `{` and `}`, paste as one value |
| `GROQ_API_KEY` | From `backend/.env` |
| `GEMINI_API_KEY` | From `backend/.env` |
| `ELEVENLABS_API_KEY` | From `backend/.env` (re-enable the key in the ElevenLabs dashboard first if it's still revoked) |
| `SMTP_PASSWORD` | From `backend/.env` |
| `SMTP_USER` | From `backend/.env` (`...@smtp-brevo.com`) |
| `SMTP_FROM` | From `backend/.env` (your verified Brevo sender address) |

For `FIREBASE_SERVICE_ACCOUNT_JSON`, paste the JSON exactly as-is — newlines
inside are fine, Render stores it verbatim. If the app logs
`FIREBASE_SERVICE_ACCOUNT_JSON is set but is not valid JSON`, something was
truncated on paste; recopy the whole file.

**2f.** Click **Save changes**. Render redeploys automatically.

**2g.** When it goes live, copy the service URL from the top of the page — it
looks like `https://voxmind-api.onrender.com`.

**2h.** Verify it's up (may take ~50s if it slept):

```bash
curl https://voxmind-api.onrender.com/healthz
```

Should print `{"status":"ok"}`.

**Tell me the URL once you have it** — I'll wire the frontend to it, deploy the
frontend, and run the end-to-end checks.

---

## Step 3 — Deploy the frontend — done

`VITE_API_BASE_URL` set to the Render URL, built, and deployed to
https://voxmind-504022.web.app. Verified from the deployed page:

- `/readyz` returns `ready: true` with `credential_signing: ok`, `firestore: ok`
- A cross-origin call from the Hosting domain to the Render backend succeeds
  (CORS correct)
- An unauthenticated protected route returns `401`, not a CORS failure

---

## Step 4 — Remaining smoke test (needs a real mic)

The parts that need a human at a real browser, on
**https://voxmind-504022.web.app** rather than localhost: signup → OTP email →
verify → hold mic → speak → hear the reply. Worth trying one non-English language
too.

Re-enable the ElevenLabs API key first, or every reply falls back to the browser
voice (silent for Kannada/Tamil on most Windows installs — you'll see
"Voice unavailable for …" instead).

---

## Troubleshooting

### Every authenticated request returns 500

Hit `/readyz` first — it names the failing dependency instead of leaving you to
guess:

```bash
curl https://voxmind-api.onrender.com/readyz
```

| `/readyz` shows | Meaning | Fix |
|---|---|---|
| `credential_source: application_default` in production | `FIREBASE_SERVICE_ACCOUNT_JSON` isn't set | Add it in the Render dashboard |
| `credential_signing: failed` | JSON parsed, but the `private_key` was mangled on paste | Recopy the whole key file |
| `firestore: failed: Unknown … target uri is not valid: dns:///` | An emulator env var is set to an **empty string** | Delete `FIRESTORE_EMULATOR_HOST` / `FIREBASE_AUTH_EMULATOR_HOST` entirely — don't blank them |

That last one caused a real outage during this deploy. The Google client
libraries check whether those variables are *present*, not whether they contain
anything, so `FIRESTORE_EMULATOR_HOST=""` means "there's an emulator, at address
`''`". `app/firebase_app.py` now strips empty values defensively, but it's worth
knowing since the error message points nowhere near the cause.

---

## Rotating the service account key

The key in `backend/serviceAccountKey.json` is a long-lived credential with
Firestore and Auth access. It's gitignored and never committed, but if it's ever
exposed (pasted in a chat, committed by accident, shared in a screenshot),
revoke it:

```bash
# list keys
gcloud iam service-accounts keys list --iam-account=voxmind-backend@voxmind-504022.iam.gserviceaccount.com

# delete the compromised one
gcloud iam service-accounts keys delete KEY_ID --iam-account=voxmind-backend@voxmind-504022.iam.gserviceaccount.com

# create a replacement, then update FIREBASE_SERVICE_ACCOUNT_JSON in Render
gcloud iam service-accounts keys create backend/serviceAccountKey.json --iam-account=voxmind-backend@voxmind-504022.iam.gserviceaccount.com
```

On Windows, prefix `gcloud` with its full path if it isn't on PATH:
`& "C:\Users\HAMZAH\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"`

---

## Known free-tier limits

| Thing | Limit | Effect |
|---|---|---|
| Render free tier | Sleeps after ~15 min idle | ~30–50s cold start; warm it up before demos |
| Render free tier | 512 MB RAM, 0.1 CPU | Fine for this workload |
| ElevenLabs free | 10k credits/mo (~10 min audio) | Falls back to browser voice when exhausted |
| Groq free | Rate-limited per minute | Falls back to Gemini automatically |
| Brevo free | 300 emails/day | Plenty for OTP |
| DuckDuckGo | Unofficial, rate-limits | Search skipped silently; LLM still answers |
| Rate limiting | In-memory, per instance | Not a security boundary on its own |
