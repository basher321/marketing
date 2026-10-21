"""cPanel "Setup Python App" entry point. The server (LiteSpeed) speaks WSGI, so the
FastAPI (ASGI) app is wrapped by a2wsgi. It loads this file once and then forks
worker processes, so anything holding a thread or a socket is made per process:
a2wsgi's event-loop thread is created on the first request, and the startup
check's database connection is dropped before the fork. Keep
SCHEDULER_ENABLED=false here (idle processes are stopped); run jobs through cron
+ GET /cron/{job_id} instead."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)  # settings read .env from the working directory
sys.path.insert(0, HERE)

from a2wsgi import ASGIMiddleware  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app as asgi_app, on_startup  # noqa: E402

on_startup()
engine.dispose()  # no pooled connection may be shared across forked workers

_wsgi = None
_pid = None


def application(environ, start_response):
    global _wsgi, _pid
    if _wsgi is None or _pid != os.getpid():
        _wsgi, _pid = ASGIMiddleware(asgi_app), os.getpid()
    return _wsgi(environ, start_response)
