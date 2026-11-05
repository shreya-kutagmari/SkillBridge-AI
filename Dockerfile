# ── SkillBridge AI — Dockerfile ──────────────────────────────────────────
# Multi-stage build: slim final image with no build tools.
#
# Build:  docker build -t skillbridge-ai .
# Run:    docker run -p 5000:5000 --env-file .env skillbridge-ai
# Dev:    docker run -p 5000:5000 -e SECRET_KEY=dev skillbridge-ai
# ─────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps for any C-extension wheels (e.g. pdfminer, numpy)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Final image ───────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source (no .env, no database.db — mount at runtime)
COPY . .

# Ensure uploads directory exists inside the image
RUN mkdir -p /app/uploads

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser

# Initialise DB and start gunicorn
# DATABASE_DB path can be overridden via bind-mount at runtime
ENV FLASK_ENV=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 5000

# Gunicorn: 2 synchronous workers, 120-second timeout (AI calls can be slow)
CMD ["sh", "-c", "python -c 'import app; app.init_db()' && \
     gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app"]
