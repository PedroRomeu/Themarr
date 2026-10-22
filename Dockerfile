# Themarr server image (headless web UI, see Themarr_Docker.py)
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# YouTube changes often and yt-dlp follows: always the latest release on each build.
# After the requirements step on purpose, so the Docker cache never skips it.
RUN pip install --no-cache-dir -U "yt-dlp[default]"

COPY core/ core/
COPY templates/ templates/
COPY static/ static/
COPY jellyfin/ jellyfin/
COPY api_controller.py routes.py main.py Themarr_Docker.py ./
RUN python -m compileall -q /app

ENV THEMARR_MODE=server \
    THEMARR_MEDIA_ROOT=/data \
    THEMARR_CONFIG_DIR=/config \
    THEMARR_PORT=8686 \
    XDG_CACHE_HOME=/tmp/cache \
    DENO_DIR=/tmp/deno \
    PYTHONUNBUFFERED=1

EXPOSE 8686
CMD ["python", "Themarr_Docker.py"]
