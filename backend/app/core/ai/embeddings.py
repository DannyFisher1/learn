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

# --- Module-level Cache ---
# Stores the singleton instance for the current configuration
_cached_embeddings_instance: Optional[Embeddings] = None

def _create_embeddings_instance() -> Embeddings:
    """
    Internal function to create a new Embeddings instance based on current configuration.
    Raises ValueError or RuntimeError on configuration or initialization errors.
    """
    provider = config.ACTIVE_AI_PROVIDER
    model_name = config.ACTIVE_EMBEDDING_MODEL
    logger.info(f"Creating NEW Embeddings instance (Provider: {provider.upper()}, Model: {model_name})")
    instance: Optional[Embeddings] = None
    try:
        if provider == "ollama":
            instance = OllamaEmbeddings(
                model=model_name,
                base_url=config.OLLAMA_BASE_URL
            )
        elif provider == "openai":
            if not config.OPENAI_API_KEY:
                error_msg = "OpenAI API Key not found for OpenAI embeddings."
                logger.error(error_msg)
                raise ValueError(error_msg)
            instance = OpenAIEmbeddings(
                model=model_name,
                api_key=config.OPENAI_API_KEY
            )
        else:
            error_msg = f"Unsupported AI_PROVIDER for embeddings: {provider}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("Embeddings instance created successfully.")
        return instance

    except Exception as e:
        logger.error(f"Failed to create embeddings instance: {e}", exc_info=True)
        raise RuntimeError(f"Embeddings instance creation failed: {e}") from e

def get_embeddings() -> Embeddings:
    """
    Provides the Embeddings instance.

    Uses a module-level cache. Call `clear_embeddings_cache()` to invalidate.
    Intended for use by components like the vector store initializer.
    """
    global _cached_embeddings_instance
    if _cached_embeddings_instance is None:
        logger.debug("No cached Embeddings instance found, creating new one.")
        _cached_embeddings_instance = _create_embeddings_instance() # Can raise exceptions
    else:
        logger.debug("Returning cached Embeddings instance.")

    if _cached_embeddings_instance is None:
        logger.critical("Embeddings instance is None after initialization attempt!")
        raise RuntimeError("Failed to get a valid Embeddings instance.")

    return _cached_embeddings_instance

def clear_embeddings_cache():
    """
    Clears the cached Embeddings instance.
    Called when the provider configuration changes.
    """
    global _cached_embeddings_instance
    logger.info("Clearing cached Embeddings instance.")
    _cached_embeddings_instance = None

# --- Deprecated Function (for reference during refactoring) ---
# def _get_embeddings(force_reload: bool = False) -> Embeddings:
#     """
#     DEPRECATED: Use get_embeddings() and clear_embeddings_cache() instead.
#     Initializes and returns the appropriate embeddings model based on ACTIVE config.
#     Uses a singleton pattern but allows forced reload.
#     """
#     global _embeddings
#     if _embeddings is None or force_reload:
#        # ... old logic ...
#     if _embeddings is None:
#          raise RuntimeError("Embeddings could not be initialized.")
#     return _embeddings