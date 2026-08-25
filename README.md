# VoxMind

Multilingual, voice-based AI assistant (English, Hindi, Kannada, Tamil). BCA capstone
project — Phase 1 (web app). See `VOXMIND_PROJECT_SPEC.md` (project instructions folder)
for the full spec, and `ACCOUNT_SETUP.md` for the external accounts/keys you need before
the pipeline works end-to-end.

**Live:** frontend <https://voxmind-cu.web.app> · backend
<https://voxmind-api.onrender.com> (health: `/readyz`)

## What it does

- Sign up / sign in, then verify with an emailed 6-digit OTP (MFA is enforced
  server-side, not just by the screen).
- Hold or tap the mic and speak in English, Hindi, Kannada or Tamil; the reply comes
  back as text and speech. There's a typing box as an alternative to speaking.
- **Spoken commands are followed, not answered.** "Make it louder" moves the volume
  slider; "speak in Hindi now" switches the reply language for the rest of the session.
  These are detected server-side and skip the LLM entirely.
- Remembers profile facts and past conversations across multiple chat threads, strictly
  isolated per user (the uid is part of every Firestore document path).
- A public landing page at `/` explains the project before asking for an account.

## Stack

- Frontend: React + Vite (`frontend/`)
- Backend: FastAPI (`backend/`)
- Auth: Firebase Authentication + custom email OTP (MFA)
- Database: Cloud Firestore
- LLM: Groq (Llama 3.3 70B) with Gemini 2.5 Flash fallback
- STT: Web Speech API (browser) + Python `SpeechRecognition` (backend fallback)
- TTS: ElevenLabs (`eleven_v3`, for Kannada support) with automatic browser
  `speechSynthesis` fallback if it errors or runs out of free-tier credits
- Search: DuckDuckGo Search (time-sensitive queries only)
- OTP email: Brevo HTTP API (Render's free tier blocks outbound SMTP ports), with SMTP
  kept as a local-dev fallback
- UI components: React Bits (LiquidEther, ScrollReveal, ElasticSlider, OptionWheel,
  ElectricBorder, GooeyNav, FuzzyText, Hyperspeed, GridScan, MagicRings, BlurText)

## Troubleshooting

**The mic says "no sound is reaching the mic".** The browser is recording an input
device that produces silence — commonly a virtual audio device (Oculus, OBS, a
disconnected headset) left as the Windows default. Change the default input in Windows
sound settings, or set the microphone for the site via the icon in the browser's
address bar.

**Diagnosing anything else about the mic:** load the app with `?micdebug=1` (e.g.
`/home?micdebug=1`) and every speech-recognition event is traced to the console —
whether the mic opened, whether speech was detected, what was captured, how long the
session stayed open. This exists because nobody developing this can test a microphone
from a dev environment; the only way to diagnose a mic report is to have the person who
can hear it read back what the browser actually did.

**Anything broken in production:** `curl https://voxmind-api.onrender.com/readyz` first.
It names the failing dependency instead of leaving you to guess from a bare 500.

**First request takes 30–50 seconds.** Render's free tier sleeps after ~15 minutes idle.
Warm the site before a demo.

## Local development

### Prerequisites

- Node.js 18+, Python 3.11+, Firebase CLI (`npm i -g firebase-tools`)
- Accounts/keys from `ACCOUNT_SETUP.md` (Groq + Gemini keys required for the LLM step;
  SMTP required for OTP emails; ElevenLabs key required for spoken responses — none of
  these need a credit card, including ElevenLabs)

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # fill in values
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
copy .env.example .env   # fill in Firebase web config
npm run dev
```

### Firebase emulators (Auth + Firestore, for local dev without a real project)

```bash
firebase emulators:start
```

## Deployment

Frontend → Firebase Hosting, backend → Render (Docker). See
**[DEPLOYMENT.md](DEPLOYMENT.md)** for the step-by-step.

Cloud Run was the original target but requires a billing account on the GCP project;
the backend is a plain container, so switching to it later needs no code changes.

## Tests

```bash
cd backend && .venv\Scripts\python -m pytest    # 107 tests, pure logic, no live API calls
cd frontend && npm run lint && npm run build
```

## Status

Phase 1 (web app) built and deployed, including the Round 2 additions (landing page,
volume control with spoken commands, HTML OTP email, typing input). Phase 2 (ESP-based
hardware/IoT layer) is out of scope — `backend/app/routes/iot.py` is a deliberate 501
stub for it.

Known gap: the ElevenLabs API key is revoked, so spoken replies currently fall back to
the browser's own voice, which is silent for Kannada and Tamil on most Windows machines.
Regenerating the key in the ElevenLabs dashboard restores real TTS with no code change.
