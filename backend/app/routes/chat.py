import base64
import logging
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.config import get_settings
from app.deps import CurrentUser, get_mfa_verified_user
from app.middleware.rate_limit import limiter
from app.models.chat import (
    SUPPORTED_LANGS,
    AskRequest,
    AskResponse,
    ChatHistoryResponse,
    ChatMessage,
    TranscribeResponse,
)
from app.services import firestore_client
from app.services.elevenlabs_client import ElevenLabsError, synthesize_speech
from app.services.gemini_client import LLMProviderError as GeminiError
from app.services.gemini_client import ask_gemini
from app.services.groq_client import LLMProviderError as GroqError
from app.services.groq_client import ask_groq
from app.services.prompt import build_messages
from app.services.search_client import format_search_context, is_time_sensitive, search_web
from app.services.stt_client import STTError, transcribe_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ask", response_model=AskResponse)
@limiter.limit(get_settings().rate_limit_chat)
async def ask(request: Request, body: AskRequest, user: CurrentUser = Depends(get_mfa_verified_user)):
    settings = get_settings()

    if body.lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported language: {body.lang}")

    # Assemble prompt context — all reads scoped to this uid.
    user_doc = firestore_client.get_user_doc(user.uid) or {}
    tone = user_doc.get("tone", "friendly")
    facts = [f["text"] for f in firestore_client.list_profile_facts(user.uid)]
    history = firestore_client.get_recent_chat_history(user.uid, settings.chat_history_limit)

    search_context = None
    used_search = False
    if is_time_sensitive(body.transcript, body.lang):
        results = await search_web(body.transcript)
        if results:
            search_context = format_search_context(results)
            used_search = True

    messages = build_messages(
        tone=tone,
        facts=facts,
        chat_history=history,
        transcript=body.transcript,
        lang=body.lang,
        today=date.today().isoformat(),
        search_context=search_context,
    )

    reply_text: str | None = None
    provider = "groq"
    try:
        reply_text = await ask_groq(messages)
    except GroqError as exc:
        logger.warning("Groq failed for uid=%s, falling back to Gemini: %s", user.uid, exc)
        provider = "gemini"
        try:
            reply_text = await ask_gemini(messages)
        except GeminiError as exc2:
            logger.error("Both Groq and Gemini failed for uid=%s: %s / %s", user.uid, exc, exc2)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The assistant is busy right now. Please try again in a moment.",
            ) from exc2

    firestore_client.append_chat_message(user.uid, "user", body.transcript, body.lang)
    firestore_client.append_chat_message(user.uid, "assistant", reply_text, body.lang)

    audio_base64 = None
    audio_error = None
    try:
        audio_bytes = await synthesize_speech(reply_text, body.lang)
        audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
    except ElevenLabsError as exc:
        logger.warning("ElevenLabs TTS failed for uid=%s, falling back to browser voice: %s", user.uid, exc)
        audio_error = "Using your browser's voice — ElevenLabs is unavailable right now."

    return AskResponse(
        reply_text=reply_text,
        lang=body.lang,
        used_search=used_search,
        audio_base64=audio_base64,
        audio_error=audio_error,
        llm_provider=provider,
    )


@router.post("/transcribe", response_model=TranscribeResponse)
@limiter.limit(get_settings().rate_limit_chat)
async def transcribe(
    request: Request,
    lang: str,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_mfa_verified_user),
):
    """Backend STT fallback for when the browser's Web Speech API is
    unsupported or fails. The frontend uploads a recorded audio blob here and
    then calls /chat/ask with the resulting transcript."""
    settings = get_settings()

    if lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported language: {lang}")
    if file.content_type not in settings.allowed_audio_content_types_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported audio type: {file.content_type}"
        )

    audio_bytes = await file.read()
    if len(audio_bytes) > settings.max_audio_upload_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Audio file too large")

    try:
        transcript = await transcribe_audio(audio_bytes, lang)
    except STTError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return TranscribeResponse(transcript=transcript, lang=lang)


@router.get("/history", response_model=ChatHistoryResponse)
async def get_history(user: CurrentUser = Depends(get_mfa_verified_user)):
    settings = get_settings()
    history = firestore_client.get_recent_chat_history(user.uid, settings.chat_history_limit)
    return ChatHistoryResponse(
        messages=[ChatMessage(role=m["role"], text=m["text"], lang=m.get("lang", "en"), created_at=m.get("createdAt")) for m in history]
    )
