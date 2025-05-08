# app/config.py
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from app.utils import ensure_directory_exists # Import utility
from typing import Literal
# Load environment variables from .env file located in the parent directory
# Adjust the path if your .env file is elsewhere
dotenv_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=dotenv_path)

logger = logging.getLogger(__name__)

# --- Provider Selection ---
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").lower() # Default to ollama if not set



# --- Ollama Configuration ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

# --- OpenAI Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# --- RAG & Processing Configuration ---
try:
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 150))
    RETRIEVER_K = int(os.getenv("RETRIEVER_K", 5))
except ValueError:
    logger.error("Invalid non-integer value for CHUNK_SIZE, CHUNK_OVERLAP, or RETRIEVER_K in .env. Using defaults.")
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 150
    RETRIEVER_K = 5

# --- Storage Paths ---
# Use pathlib for better path management
BASE_DIR = Path(__file__).resolve().parent.parent # Project root (backend/)
UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "data/uploads")
VECTOR_STORE_DIR = BASE_DIR / os.getenv("VECTOR_STORE_DIR", "data")


SEARXNG_URL = os.getenv("SEARXNG_URL")
# Convert string 'true'/'false' from env var to boolean
SEARXNG_UNSECURE = os.getenv("SEARXNG_UNSECURE", "false").lower() == "true"

# Log SearXNG status
if SEARXNG_URL:
    logger.info(f"SearXNG integration enabled. Host: {SEARXNG_URL}, Unsecure (HTTP): {SEARXNG_UNSECURE}")
else:
    logger.warning("SearXNG URL not set in .env. Web search tool will be disabled.")

# --- Validate Configuration ---
if AI_PROVIDER not in ["ollama", "openai"]:
    logger.error(f"Invalid AI_PROVIDER specified: '{AI_PROVIDER}'. Must be 'ollama' or 'openai'. Defaulting to 'ollama'.")
    AI_PROVIDER = "ollama"

if AI_PROVIDER == "openai" and not OPENAI_API_KEY:
    logger.error("AI_PROVIDER is 'openai' but OPENAI_API_KEY is not set in .env. OpenAI calls will fail.")
    # You might want to raise an Exception here to prevent startup without a key:
    # raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER is 'openai'.")

logger.info(f"AI Provider selected: {AI_PROVIDER.upper()}")
if AI_PROVIDER == "ollama":
    logger.info(f"Using Ollama Base URL: {OLLAMA_BASE_URL}")
    logger.info(f"Using Ollama LLM Model: {OLLAMA_LLM_MODEL}")
    logger.info(f"Using Ollama Embedding Model: {OLLAMA_EMBEDDING_MODEL}")
else: # openai
    logger.info(f"Using OpenAI Chat Model: {OPENAI_CHAT_MODEL}")
    logger.info(f"Using OpenAI Embedding Model: {OPENAI_EMBEDDING_MODEL}")

# Ensure storage directories exist (using the utility function)
ensure_directory_exists(str(UPLOAD_DIR))
ensure_directory_exists(str(VECTOR_STORE_DIR))

logger.info(f"Upload directory: {UPLOAD_DIR}")
logger.info(f"Vector store directory: {VECTOR_STORE_DIR}")
logger.info(f"RAG Config: Chunk Size={CHUNK_SIZE}, Overlap={CHUNK_OVERLAP}, Retriever K={RETRIEVER_K}")

# Export selected models for easier access (optional)
SELECTED_LLM_MODEL = OLLAMA_LLM_MODEL if AI_PROVIDER == "ollama" else OPENAI_CHAT_MODEL
SELECTED_EMBEDDING_MODEL = OLLAMA_EMBEDDING_MODEL if AI_PROVIDER == "ollama" else OPENAI_EMBEDDING_MODEL



ACTIVE_AI_PROVIDER = AI_PROVIDER
logger.info(f"Initial active AI Provider set to: {ACTIVE_AI_PROVIDER.upper()}")

# We might also need to store active models if we allow switching specific models later
ACTIVE_LLM_MODEL = SELECTED_LLM_MODEL
ACTIVE_EMBEDDING_MODEL = SELECTED_EMBEDDING_MODEL

def update_active_provider(new_provider: Literal['ollama', 'openai']):
    """Updates the active provider and associated models in memory."""
    global ACTIVE_AI_PROVIDER, ACTIVE_LLM_MODEL, ACTIVE_EMBEDDING_MODEL
    if new_provider == "ollama":
        ACTIVE_AI_PROVIDER = "ollama"
        ACTIVE_LLM_MODEL = OLLAMA_LLM_MODEL
        ACTIVE_EMBEDDING_MODEL = OLLAMA_EMBEDDING_MODEL
    elif new_provider == "openai":
        # Add a check here BEFORE switching if the key is missing
        if not OPENAI_API_KEY:
             logger.error("Cannot switch to OpenAI: OPENAI_API_KEY is not configured.")
             raise ValueError("OpenAI API Key is not configured. Cannot switch provider.")
        ACTIVE_AI_PROVIDER = "openai"
        ACTIVE_LLM_MODEL = OPENAI_CHAT_MODEL
        ACTIVE_EMBEDDING_MODEL = OPENAI_EMBEDDING_MODEL
    else:
        # Should not happen with Literal validation, but good practice
        logger.error(f"Attempted to switch to invalid provider: {new_provider}")
        return False # Indicate failure

    logger.info(f"Runtime AI Provider switched to: {ACTIVE_AI_PROVIDER.upper()}")
    logger.info(f"Active LLM Model set to: {ACTIVE_LLM_MODEL}")
    logger.info(f"Active Embedding Model set to: {ACTIVE_EMBEDDING_MODEL}")
    return True # Indicate success

# --- Chroma Mode Configuration ---
# Set CHROMA_USE_HTTP to 'true' in your .env to use Chroma HTTP client mode (default: true)
CHROMA_USE_HTTP = os.getenv("CHROMA_USE_HTTP", "true").lower() == "true"

# --- Reddit Configuration ---
REDDIT_ENABLED = os.getenv("REDDIT_ENABLED", "false").lower() == "true"
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Store the output base directory path as a string
PROJECT_GENERATOR_OUTPUT_BASE_DIR_STR = os.getenv("DEFAULT_OUTPUT_BASE")
