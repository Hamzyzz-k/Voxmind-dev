# VoxMind

Multilingual, voice-based AI assistant (English, Hindi, Kannada, Tamil). BCA capstone
project — Phase 1 (web app). See `VOXMIND_PROJECT_SPEC.md` (project instructions folder)
for the full spec, and `ACCOUNT_SETUP.md` for the external accounts/keys you need before
the pipeline works end-to-end.

## Stack

- Frontend: React + Vite (`frontend/`)
- Backend: FastAPI (`backend/`)
- Auth: Firebase Authentication + custom email OTP (MFA)
- Database: Cloud Firestore
- LLM: Groq (Llama 3.3 70B) with Gemini 2.5 Flash fallback
- STT: Web Speech API (browser) + Python `SpeechRecognition` (backend fallback)
- TTS: Google Cloud Text-to-Speech
- Search: DuckDuckGo Search (time-sensitive queries only)

## Local development

### Prerequisites

- Node.js 18+, Python 3.11+, Firebase CLI (`npm i -g firebase-tools`)
- Accounts/keys from `ACCOUNT_SETUP.md` (Groq + Gemini keys required for the LLM step;
  SMTP required for OTP emails; GCP project + Cloud TTS required for spoken responses)

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

## Status

Phase 1 (web app) in progress. Phase 2 (ESP-based hardware/IoT layer) is out of scope —
see the spec's `iot` namespace note.
