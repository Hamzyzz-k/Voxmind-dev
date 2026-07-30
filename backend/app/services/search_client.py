"""DuckDuckGo search, triggered only for time-sensitive transcripts. Never
raises to the caller — on any failure (rate limit, network, timeout) it
returns None so the LLM answers from its own knowledge, per spec: "skip it
silently ... never block or error out on a failed search."
"""

import asyncio
import logging

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

TIME_SENSITIVE_KEYWORDS: dict[str, list[str]] = {
    "en": [
        "today", "latest", "news", "current", "currently", "now", "this week",
        "this month", "score", "weather", "price", "recent", "update", "live",
    ],
    "hi": ["आज", "ताज़ा", "ताजा", "समाचार", "अभी", "मौसम", "कीमत", "हाल"],
    "kn": ["ಇಂದು", "ಇತ್ತೀಚಿನ", "ಸುದ್ದಿ", "ಈಗ", "ಹವಾಮಾನ", "ಬೆಲೆ", "ಪ್ರಸ್ತುತ"],
    "ta": ["இன்று", "சமீபத்திய", "செய்தி", "இப்போது", "வானிலை", "விலை", "தற்போதைய"],
}

_SEARCH_TIMEOUT_SECONDS = 8


def is_time_sensitive(transcript: str, lang: str) -> bool:
    text = transcript.lower()
    keywords = TIME_SENSITIVE_KEYWORDS.get(lang, []) + TIME_SENSITIVE_KEYWORDS["en"]
    return any(keyword.lower() in text for keyword in keywords)


def _search_sync(query: str, max_results: int) -> list[dict]:
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def search_web(query: str, max_results: int = 3) -> list[dict] | None:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_search_sync, query, max_results), timeout=_SEARCH_TIMEOUT_SECONDS
        )
    except Exception as exc:
        logger.warning("DuckDuckGo search failed, skipping search context: %s", exc)
        return None


def format_search_context(results: list[dict]) -> str:
    lines = [f"- {r.get('title', '')}: {r.get('body', '')}" for r in results]
    return "\n".join(lines)
