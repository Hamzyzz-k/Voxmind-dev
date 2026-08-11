FROM python:3.11-slim

# Fail fast and log immediately rather than buffering (matters for container logs).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ffmpeg: required by pydub to decode browser-recorded audio (webm/ogg) for the
#   backend Speech-to-Text fallback, and to convert ElevenLabs MP3 into the raw
#   PCM the hardware device plays directly.
# espeak-ng: last-resort text-to-speech. The website can fall back to the
#   browser's own voice when ElevenLabs fails; the glasses have no browser, and
#   a blind user cannot tell silence-because-it-broke apart from
#   silence-because-nothing-is-there. espeak-ng has no key, no quota and no
#   network call, so it cannot fail the same way. ~10MB.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Don't run as root.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Managed hosts inject $PORT (Cloud Run and Render both default to 8080);
# shell form lets it expand at runtime.
ENV PORT=8080
EXPOSE 8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
