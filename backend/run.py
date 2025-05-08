import requests
import uvicorn
import os
import sys
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load .env (optional) ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    logger.info(f"Loading environment variables from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)

# --- Config ---
HOST          = os.getenv("API_HOST", "0.0.0.0")
PORT          = int(os.getenv("API_PORT", 9000))
ENABLE_RELOAD = os.getenv("ENABLE_RELOAD", "TRUE").lower() in ("true", "1", "t")
APP_MODULE_STR = "app.main:app"


# --- Run App ---
if __name__ == "__main__":
    logger.info(f"Starting FastAPI: {APP_MODULE_STR} at {HOST}:{PORT} (reload={ENABLE_RELOAD})")
    uvicorn.run(
        APP_MODULE_STR,
        host=HOST,
        port=PORT,
        reload=ENABLE_RELOAD,
        reload_dirs=["/app"],
        log_level="debug",
    )
