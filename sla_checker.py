"""SLA checker entry point.

Runs a loop every 60s to check for SLA breaches.
Uses a Redis lock to ensure only one instance is active.
"""
import signal
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv()

from src.config import Config
from framework.commons.logger import logger
from src.core.db import get_db
from src.core.redis_client import get_redis
from src.ticketing.service import sla_service

def _signal_handler(signum, _frame):
    logger.info("shutdown signal received")
    sys.exit(0)

def main():
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    logger.info("starting sla checker")
    redis = get_redis()
    lock_key = "lock:sla_checker"
    client_id = f"{Config.WORKER_NAME}:{time.time()}"

    while True:
        # Try to acquire leader lock for 70 seconds
        if redis.set(lock_key, client_id, ex=70, nx=True):
            try:
                with get_db() as db:
                    count = sla_service.check_all_breaches(db)
                    if count > 0:
                        logger.info("sla check completed", breaches_found=count)
                    
                    # Also trigger dashboard refresh
                    from src.tasking.producer import publish
                    publish("refresh_dashboard_mvs", {})
            except Exception as e:
                logger.error("sla check failed", error=str(e))
        else:
            logger.debug("sla checker: leader lock held by another instance")

        time.sleep(60)

if __name__ == "__main__":
    main()
