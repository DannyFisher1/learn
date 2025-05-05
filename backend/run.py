# run.py
import uvicorn
import os
import sys
from dotenv import load_dotenv
import logging
import subprocess
import signal

# Configure basic logging for the runner script itself
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    logger.info(f"Loading environment variables from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    logger.warning(".env file not found. Using default settings or existing environment variables.")

HOST         = os.getenv("API_HOST", "0.0.0.0")
PORT         = int(os.getenv("API_PORT", 9000))
ENABLE_RELOAD = os.getenv("ENABLE_RELOAD", "TRUE").lower() in ("true", "1", "t")
APP_MODULE_STR = "app.main:app"

# Redis settings  # <-- NEW
REDIS_PORT   = os.getenv("REDIS_PORT", "6379")          # default Redis port 6379
REDIS_BIN    = os.getenv("REDIS_BIN", "redis-server")   # path or command name

if __name__ == "__main__":
    logger.info(f"--- Preparing to run FastAPI application: {APP_MODULE_STR} ---")
    logger.info(f"Host: {HOST}")
    logger.info(f"Port: {PORT}")
    logger.info(f"Reload enabled: {ENABLE_RELOAD}")

    # --- Start Chroma --------------------------------------------------------
    chroma_proc = None
    try:
        logger.info("Starting Chroma server on port 8000...")
        chroma_proc = subprocess.Popen([
            os.path.join(os.path.dirname(sys.executable), "chroma"), "run",
            "--host", "0.0.0.0", "--port", "8000"
        ])
        logger.info(f"Chroma server started with PID {chroma_proc.pid}")
    except Exception as e:
        logger.error(f"Failed to start Chroma server: {e}")
        sys.exit(1)

    # --- Start Redis ---------------------------------------------------------  # <-- NEW
    redis_proc = None
    try:
        logger.info(f"Starting Redis server on port {REDIS_PORT}...")
        redis_proc = subprocess.Popen([REDIS_BIN, "--port", REDIS_PORT])
        logger.info(f"Redis server started with PID {redis_proc.pid}")
    except Exception as e:
        logger.error(f"Failed to start Redis server: {e}")
        if chroma_proc:
            chroma_proc.terminate()
        sys.exit(1)

    # --- Cleanup handler ------------------------------------------------------
    def cleanup(*args):
        if redis_proc:   # <-- NEW
            logger.info("Terminating Redis server...")
            redis_proc.terminate()
            redis_proc.wait()
        if chroma_proc:
            logger.info("Terminating Chroma server...")
            chroma_proc.terminate()
            chroma_proc.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # --- Run Uvicorn ----------------------------------------------------------
    if not APP_MODULE_STR or ":" not in APP_MODULE_STR:
        logger.error(f"Invalid APP_MODULE_STR: '{APP_MODULE_STR}'. "
                     "Should be in 'module.path:app_instance' format.")
        cleanup()

    try:
        uvicorn.run(
            APP_MODULE_STR,
            host=HOST,
            port=PORT,
            reload=ENABLE_RELOAD,
            reload_dirs=["backend/app"],  # <-- only watch this dir
            log_level="debug",
        )
    except ImportError as e:
        logger.error(f"ImportError: Failed to import '{APP_MODULE_STR}'. "
                     "Ensure the module and application instance exist and Python can find them.")
        logger.error(f"Original error: {e}")
        cleanup()
    except Exception as e:
        logger.error(f"An unexpected error occurred while trying to run uvicorn: {e}", exc_info=True)
        cleanup()
