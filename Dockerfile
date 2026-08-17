FROM python:3.12-slim

# ffmpeg wajib: YouTube menyajikan video dan audio sebagai stream terpisah,
# tanpa ffmpeg resolusi maksimal hanya 360p.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY worker.py cleanup.py ./

# Proses tidak berjalan sebagai root: yt-dlp memproses input yang tidak tepercaya.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /srv/downloads \
    && chown -R appuser:appuser /srv
USER appuser

ENV PYTHONUNBUFFERED=1 \
    DOWNLOAD_DIR=/srv/downloads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
