"""gunicorn configuration for the deployed web service (Docker/Render).

Local development on Windows keeps using ``py -3 web_main.py`` — gunicorn
does not run on Windows.
"""

import os

bind = f"0.0.0.0:{os.getenv('PORT') or os.getenv('WEB_PORT') or '10000'}"

# MUST stay 1: PipelineState, run_lock, and the SSE event buffer live in
# process memory. More workers would shard that state — concurrent runs
# would slip past the lock and /api/events could poll a worker that never
# saw the run.
workers = 1

# Threaded worker: the SSE stream parks one thread per subscriber while the
# other threads keep serving API calls.
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "8"))

# A sync run legitimately holds a request thread for minutes (SSE) — never
# let the watchdog kill the worker mid-stream. /healthz plus the platform's
# process supervision cover genuine hangs.
timeout = 0
keepalive = 75

accesslog = "-"
errorlog = "-"
