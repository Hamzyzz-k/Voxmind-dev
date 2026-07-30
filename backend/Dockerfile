FROM python:3.11-slim

WORKDIR /app

# ffmpeg is required by pydub to decode browser-recorded audio (webm/ogg) for
# the backend Speech-to-Text fallback path.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Cloud Run injects $PORT (defaults to 8080); shell form lets $PORT expand.
ENV PORT=8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
