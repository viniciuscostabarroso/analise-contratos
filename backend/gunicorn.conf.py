import os


def _int_env(name, default, minimum=1):
    raw_value = os.getenv(name, str(default))
    try:
        return max(minimum, int(raw_value))
    except (TypeError, ValueError):
        return default


bind = f":{os.getenv('PORT', '8080')}"
workers = _int_env("GUNICORN_WORKERS", 1, minimum=1)
threads = _int_env("GUNICORN_THREADS", 8, minimum=1)
timeout = _int_env("GUNICORN_TIMEOUT", 0, minimum=0)
graceful_timeout = _int_env("GUNICORN_GRACEFUL_TIMEOUT", 30, minimum=1)
keepalive = _int_env("GUNICORN_KEEPALIVE", 5, minimum=1)
worker_class = "gthread"
worker_tmp_dir = "/dev/shm"

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
capture_output = True
preload_app = False
