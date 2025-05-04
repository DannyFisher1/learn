# run.py
import uvicorn
import os
import sys
from dotenv import load_dotenv
import logging
import subprocess
import signal

# Configure basic logging for the runner script itself
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# Load environment variables from .env file in the current directory
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    logger.info(f"Loading environment variables from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    logger.warning(".env file not found. Using default settings or existing environment variables.")

# Get host and port from environment variables, providing defaults
# These names (`API_HOST`, `API_PORT`) should match what you might use in your .env
HOST = os.getenv("API_HOST", "0.0.0.0") # Use 0.0.0.0 to be accessible on the network
PORT = int(os.getenv("API_PORT", 9000)) # Default FastAPI/Uvicorn port

# Determine if reload should be enabled (useful for development)
# Set ENABLE_RELOAD=false in .env or environment to disable
ENABLE_RELOAD = os.getenv("ENABLE_RELOAD", "TRUE").lower() in ("true", "1", "t")

# Location of the FastAPI app instance
# Assumes your main FastAPI instance `app` is in `backend/app/main.py`
APP_MODULE_STR = "app.main:app"

# --- Main Execution ---
if __name__ == "__main__":
    logger.info(f"--- Preparing to run FastAPI application: {APP_MODULE_STR} ---")
    logger.info(f"Host: {HOST}")
    logger.info(f"Port: {PORT}")
    logger.info(f"Reload enabled: {ENABLE_RELOAD}")

    # Start Chroma server on port 8000
    chroma_proc = None
    try:
        logger.info("Starting Chroma server on port 8000...")
        chroma_proc = subprocess.Popen([
            os.path.join(os.path.dirname(sys.executable), "chroma"), "run", "--host", "0.0.0.0", "--port", "8000"
        ])
        logger.info(f"Chroma server started with PID {chroma_proc.pid}")
    except Exception as e:
        logger.error(f"Failed to start Chroma server: {e}")
        sys.exit(1)

    def cleanup(*args):
        if chroma_proc:
            logger.info("Terminating Chroma server...")
            chroma_proc.terminate()
            chroma_proc.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Check if the app module string seems correct (basic check)
    if not APP_MODULE_STR or ":" not in APP_MODULE_STR:
        logger.error(f"Invalid APP_MODULE_STR: '{APP_MODULE_STR}'. Should be in 'module.path:app_instance' format.")
        cleanup()

    try:
        # Run uvicorn programmatically
        uvicorn.run(
            APP_MODULE_STR,
            host=HOST,
            port=PORT,
            reload=ENABLE_RELOAD,
            log_level="debug",     # Explicitly set uvicorn log level to debug
            # workers=1          # Use 1 worker when reload=True. For production, set reload=False and increase workers.
        )
    except ImportError as e:
         logger.error(f"ImportError: Failed to import '{APP_MODULE_STR}'. Ensure the module and application instance exist and Python can find them.")
         logger.error(f"Original error: {e}")
         cleanup()
    except Exception as e:
        logger.error(f"An unexpected error occurred while trying to run uvicorn: {e}", exc_info=True)
        cleanup()