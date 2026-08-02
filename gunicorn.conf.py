import os

bind = f"0.0.0.0:{os.getenv('PORT') or os.getenv('WEB_PORT') or '10000'}"
workers = 1

worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "8"))

timeout = 0
keepalive = 75
accesslog = "-"
errorlog = "-"
