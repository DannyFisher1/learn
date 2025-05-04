# app/core/ai/embeddings.py

import logging
from typing import Optional

# Langchain imports
from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings

# App imports
from app import config
from app.utils import get_logger

logger = get_logger(__name__)

# --- Global Variable for Embeddings Caching ---
_embeddings: Optional[Embeddings] = None # Use the base Embeddings type

# --- Embedding Model Initialization ---
def _get_embeddings(force_reload: bool = False) -> Embeddings:
    """
    Initializes and returns the appropriate embeddings model based on ACTIVE config.
    Uses a singleton pattern but allows forced reload.
    Called by vector_store.py during initialization and potentially by
    provider_service.py during provider switching (indirectly via vector_store).
    """
    global _embeddings
    # Re-initialize if force_reload is True OR if embeddings haven't been loaded yet
    if _embeddings is None or force_reload:
        # Use the dynamically updatable provider and model from config
        provider = config.ACTIVE_AI_PROVIDER
        model_name = config.ACTIVE_EMBEDDING_MODEL

        logger.info(f"Initializing Embeddings (Provider: {provider.upper()}, Model: {model_name}, Force Reload: {force_reload})")
        try:
            if provider == "ollama":
                _embeddings = OllamaEmbeddings(
                    model=model_name,
                    base_url=config.OLLAMA_BASE_URL # Use base config for URL
                )
            elif provider == "openai":
                # Check key again just in case config state is bypassed or changed
                if not config.OPENAI_API_KEY:
                    error_msg = "OpenAI API Key not found for OpenAI embeddings."
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                _embeddings = OpenAIEmbeddings(
                    model=model_name,
                    api_key=config.OPENAI_API_KEY
                )
            else:
                error_msg = f"Unsupported AI_PROVIDER for embeddings: {provider}"
                logger.error(error_msg)
                raise ValueError(error_msg) # Raise specific error for unsupported provider

            logger.info("Embeddings model initialized successfully.")

        except ValueError as ve: # Catch specific configuration errors
             logger.error(f"Configuration error initializing embeddings: {ve}")
             _embeddings = None # Ensure reset on failure
             raise # Re-raise the configuration error
        except Exception as e:
            logger.error(f"Failed to initialize embeddings model: {e}", exc_info=True)
            _embeddings = None # Ensure reset on failure
            raise RuntimeError(f"Embeddings initialization failed: {e}") # Raise generic runtime error

    # Ensure embeddings are not None after attempt
    if _embeddings is None:
         raise RuntimeError("Embeddings could not be initialized.")

    return _embeddings