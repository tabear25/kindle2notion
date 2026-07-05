# kindle2notion — container image for the Flask web UI.
# Render builds this Dockerfile directly from the GitHub repo.
# Full deployment guide: deploy/render/README.md
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install Python dependencies first so this layer is cached across code-only changes.
COPY requirements/requirements.txt ./requirements/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r requirements/requirements.txt

# Install the Chromium build matching the installed Playwright package, together
# with its OS-level libraries. `--with-deps` runs the required apt-get steps.
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy the application source.
COPY . .

# Render injects PORT at runtime; EXPOSE documents the default for local runs.
EXPOSE 10000

# Production server. `python web_main.py` (Werkzeug dev server) remains for
# local development and the VPS systemd unit.
CMD ["gunicorn", "-c", "gunicorn.conf.py", "web_main:app"]
