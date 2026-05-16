import os
import sys
import logging
import traceback
import threading
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "app.log")
ERROR_FILE = os.path.join(LOG_DIR, "error.log")
CRASH_FILE = os.path.join(LOG_DIR, "crash.log")
LAST_RUN_FILE = os.path.join(LOG_DIR, "last_run.txt")

_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_console_formatter = logging.Formatter("[%(levelname)s] %(message)s")

logger = logging.getLogger("photo_memories")
logger.setLevel(logging.DEBUG)

_app_handler = TimedRotatingFileHandler(
    LOG_FILE, when="midnight", backupCount=30, encoding="utf-8"
)
_app_handler.setLevel(logging.DEBUG)
_app_handler.setFormatter(_formatter)

_error_handler = TimedRotatingFileHandler(
    ERROR_FILE, when="midnight", backupCount=30, encoding="utf-8"
)
_error_handler.setLevel(logging.WARNING)
_error_handler.setFormatter(_formatter)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_console_formatter)

logger.addHandler(_app_handler)
logger.addHandler(_error_handler)
logger.addHandler(_console_handler)


def _write_crash(exc_type, exc_value, exc_tb, source="main"):
    try:
        with open(CRASH_FILE, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"\n{'='*60}\n")
            f.write(f"CRASH @ {datetime.now().isoformat()}  source={source}\n")
            f.write(f"sys.argv: {sys.argv}\n")
            for key in ("SOURCE_DRIVE", "PHOTO_DATA_DIR", "DEEPSEEK_API_KEY"):
                val = os.environ.get(key, "<not set>")
                if key == "DEEPSEEK_API_KEY" and val and val != "<not set>":
                    val = val[:8] + "..."
                f.write(f"env.{key}: {val}\n")
            f.write("\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
            f.write(f"{'='*60}\n")
    except Exception:
        pass


def _sys_excepthook(exc_type, exc_value, exc_tb):
    _original_excepthook(exc_type, exc_value, exc_tb)
    _write_crash(exc_type, exc_value, exc_tb, source="uncaught")


def _threading_excepthook(args):
    _write_crash(args.exc_type, args.exc_value, args.exc_traceback, source="thread")


_original_excepthook = sys.excepthook
sys.excepthook = _sys_excepthook
threading.excepthook = _threading_excepthook


def mark_startup():
    try:
        from datetime import datetime
        with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
            f.write(f"started @ {datetime.now().isoformat()}\n")
    except Exception:
        pass


def mark_ok_exit():
    try:
        from datetime import datetime
        with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
            f.write(f"ok @ {datetime.now().isoformat()}\n")
    except Exception:
        pass


def check_previous_crash():
    try:
        if not os.path.isfile(LAST_RUN_FILE):
            return False
        with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content.startswith("started"):
            logger.warning(f"上次运行未正常退出（可能闪退），标记内容: {content}")
            return True
        return False
    except Exception:
        return False
