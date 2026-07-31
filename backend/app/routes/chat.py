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
    ChatMessage,
    Thread,
    ThreadDetailResponse,
    ThreadListResponse,
    TranscribeResponse,
)
from app.services import firestore_client
from app.services.elevenlabs_client import ElevenLabsError, synthesize_speech
from app.services.gemini_client import LLMProviderError as GeminiError
from app.services.gemini_client import ask_gemini
from app.services.groq_client import LLMProviderError as GroqError
from app.services.groq_client import ask_groq
from app.services.prompt import build_messages, derive_thread_title
from app.services.search_client import format_search_context, is_time_sensitive, search_web
from app.services.stt_client import STTError, transcribe_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _to_thread(doc: dict) -> Thread:
    return Thread(
        id=doc["id"],
        title=doc.get("title"),
        created_at=doc.get("createdAt"),
        updated_at=doc.get("updatedAt"),
    )


def _to_message(doc: dict) -> ChatMessage:
    return ChatMessage(
        role=doc["role"], text=doc["text"], lang=doc.get("lang", "en"), created_at=doc.get("createdAt")
    )


def _require_thread(uid: str, thread_id: str) -> dict:
    """Loads a thread or 404s. The uid is part of the Firestore path, so this
    can never resolve to another user's thread."""
    thread = firestore_client.get_thread(uid, thread_id)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return thread


# --- Threads ---


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(user: CurrentUser = Depends(get_mfa_verified_user)):
    threads = firestore_client.list_threads(user.uid)
    return ThreadListResponse(threads=[_to_thread(t) for t in threads])


@router.post("/threads", response_model=Thread, status_code=status.HTTP_201_CREATED)
async def create_thread(user: CurrentUser = Depends(get_mfa_verified_user)):
    return _to_thread(firestore_client.create_thread(user.uid))


@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread(thread_id: str, user: CurrentUser = Depends(get_mfa_verified_user)):
    thread = _require_thread(user.uid, thread_id)
    messages = firestore_client.get_full_chat_history(user.uid, thread_id)
    return ThreadDetailResponse(thread=_to_thread(thread), messages=[_to_message(m) for m in messages])


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(thread_id: str, user: CurrentUser = Depends(get_mfa_verified_user)):
    _require_thread(user.uid, thread_id)
    firestore_client.delete_thread(user.uid, thread_id)


# --- Ask ---


@router.post("/ask", response_model=AskResponse)
@limiter.limit(get_settings().rate_limit_chat)
async def ask(request: Request, body: AskRequest, user: CurrentUser = Depends(get_mfa_verified_user)):
    settings = get_settings()

    if body.lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported language: {body.lang}")

    _require_thread(user.uid, body.thread_id)
    is_first_message = firestore_client.count_thread_messages(user.uid, body.thread_id) == 0

    # Assemble prompt context. Profile facts are global to the user; chat
    # history comes from this thread only, so threads never bleed into
    # each other's context.
    user_doc = firestore_client.get_user_doc(user.uid) or {}
    tone = user_doc.get("tone", "friendly")
    facts = [f["text"] for f in firestore_client.list_profile_facts(user.uid)]
    history = firestore_client.get_recent_chat_history(user.uid, body.thread_id, settings.chat_history_limit)

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

    firestore_client.append_chat_message(user.uid, body.thread_id, "user", body.transcript, body.lang)
    firestore_client.append_chat_message(user.uid, body.thread_id, "assistant", reply_text, body.lang)
    firestore_client.touch_thread(user.uid, body.thread_id)

    thread_title = None
    if is_first_message:
        thread_title = derive_thread_title(body.transcript)
        firestore_client.set_thread_title(user.uid, body.thread_id, thread_title)

    audio_base64 = None
    audio_error = None
    if body.speak:
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
        thread_id=body.thread_id,
        thread_title=thread_title,
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
