"""Tickora — entry point.

Boots the HTTP API via QF Framework's FrameworkApp. The same image is reused
for the worker (see worker.py) and the SLA checker (see sla_checker.py).
"""

# GEVENT MONKEY PATCHING MUST BE FIRST
try:
    from gevent import monkey
    monkey.patch_all()
    try:
        import psycogreen.gevent
        psycogreen.gevent.patch_psycopg()
    except ImportError:
        pass
except ImportError:
    pass

import signal
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.config import Config  # noqa: E402
from framework.commons.logger import logger as log  # noqa: E402


def _signal_handler(signum, _frame):
    sig_name = signal.Signals(signum).name
    log.info("shutdown signal received", extra={"signal": sig_name})
    sys.exit(0)


def main() -> None:
    log.info(
        "starting tickora",
        extra={
            "role": Config.ROLE,
            "dev_mode": Config.DEV_MODE,
            "api_port": Config.API_PORT,
            "service": Config.SERVICE_NAME,
        },
    )

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # Best-effort DB warm-up. Migrations run separately via Alembic.
    try:
        from src.core.db import get_engine
        from sqlalchemy import text
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("postgres reachable")
    except Exception as e:
        log.warning("postgres not reachable yet", extra={"error": str(e)})

    from framework.app import FrameworkApp, FrameworkSettings  # type: ignore

    settings = FrameworkSettings(
        enable_etl=False,
        enable_api=True,
        enable_dynamic_endpoints=True,

        api_host="0.0.0.0",
        api_port=Config.API_PORT,
        api_version="1.0",
        api_title="Tickora API",
        api_description="Tickora — ticketing, tasking, distribution, audit, RBAC",

        endpoint_json_path="maps/endpoint.json",

        enable_tracing=Config.ENABLE_TRACING,
        otlp_endpoint=Config.OTLP_ENDPOINT,
        service_name=Config.SERVICE_NAME,
    )

    fw = FrameworkApp(settings, app_root=BASE_DIR)
    handles = fw.run()

    if handles.app:
        # Install correlation + error hooks on the Flask app QF created.
        from src.core.correlation import install_flask_hooks
        from src.core.errors import install_flask_error_handlers

        install_flask_hooks(handles.app)
        install_flask_error_handlers(handles.app)

        log.info("api listening", extra={"host": settings.api_host, "port": settings.api_port})
        try:
            handles.app.run(host=settings.api_host, port=settings.api_port, debug=False)
        except (KeyboardInterrupt, SystemExit):
            log.info("exiting")


if __name__ == "__main__":
    main()
