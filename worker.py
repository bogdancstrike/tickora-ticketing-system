"""Worker entry point.

Runs the Kafka consumer to process async tasks (notifications, SLA, etc.).
"""
import signal
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv()

from src.config import Config
from framework.commons.logger import logger

def _signal_handler(signum, _frame):
    sig_name = signal.Signals(signum).name
    logger.info("shutdown signal received", signal=sig_name)
    sys.exit(0)

def main():
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    logger.info("starting worker", worker_name=Config.WORKER_NAME)

    # Import modules to register task handlers
    import src.ticketing.notifications  # noqa: F401
    # import src.ticketing.sla          # noqa: F401 (not implemented yet)

    from src.tasking.consumer import run_consumer
    run_consumer()

if __name__ == "__main__":
    main()
