# app/core/ai/llm.py

import logging
from typing import Optional

# Langchain imports
from langchain_core.language_models import BaseChatModel
from langchain_community.chat_models import ChatOllama
from langchain_openai import ChatOpenAI

# App imports
from app import config
from app.utils import get_logger

logger = get_logger(__name__)

# --- Module-level Cache ---
# Stores the singleton instance for the current configuration
_cached_llm_instance: Optional[BaseChatModel] = None

def _create_llm_instance() -> BaseChatModel:
    """
    Internal function to create a new LLM instance based on current configuration.
    Raises ValueError or RuntimeError on configuration or initialization errors.
    """
    provider = config.ACTIVE_AI_PROVIDER
    model_name = config.ACTIVE_LLM_MODEL
    logger.info(f"Creating NEW LLM instance (Provider: {provider.upper()}, Model: {model_name})")
    instance: Optional[BaseChatModel] = None
    try:
        if provider == "ollama":
            instance = ChatOllama(
                model=model_name,
                base_url=config.OLLAMA_BASE_URL,
                temperature=0.1
            )
        elif provider == "openai":
            if not config.OPENAI_API_KEY:
                error_msg = "OpenAI API Key not found for OpenAI LLM."
                logger.error(error_msg)
                raise ValueError(error_msg)

            llm_model_name = model_name
            if "gpt-3.5" not in llm_model_name and "gpt-4" not in llm_model_name:
                logger.warning(f"Selected OpenAI model {llm_model_name} might not fully support function calling needed for optimal agent performance.")

            instance = ChatOpenAI(
                model=llm_model_name,
                temperature=0.1,
                api_key=config.OPENAI_API_KEY
            )
        else:
            error_msg = f"Unsupported AI_PROVIDER for LLM: {provider}"
            logger.error(error_msg)
            raise ValueError(error_msg) # Raise specific error

        logger.info("LLM instance created successfully.")
        return instance

    except Exception as e:
        logger.error(f"Failed to create LLM instance: {e}", exc_info=True)
        # Raise a runtime error to signal failure upstream
        raise RuntimeError(f"LLM instance creation failed: {e}") from e


def get_llm() -> BaseChatModel:
    """
    Provides the LLM instance.

    This function acts as the access point for the LLM. It uses a module-level
    cache. It should be used as a FastAPI dependency (`Depends(get_llm)`)
    or called directly where a dependency cannot be injected but an instance is needed
    (e.g., during agent executor initialization if not refactored).

    The cache is invalidated by `clear_llm_instance_cache()`.
    """
    global _cached_llm_instance
    if _cached_llm_instance is None:
        logger.debug("No cached LLM instance found, creating new one.")
        _cached_llm_instance = _create_llm_instance() # Can raise exceptions
    else:
         logger.debug("Returning cached LLM instance.")

    # We should have an instance here unless _create_llm_instance failed,
    # in which case an exception would have been raised.
    if _cached_llm_instance is None:
         # This state should ideally not be reachable if error handling above is correct
         logger.critical("LLM instance is None after initialization attempt!")
         raise RuntimeError("Failed to get a valid LLM instance.")

    return _cached_llm_instance

def clear_llm_instance_cache():
    """
    Clears the cached LLM instance.
    This should be called when the underlying configuration (like the provider) changes,
    forcing `get_llm` to create a new instance on its next call.
    """
    global _cached_llm_instance
    logger.info("Clearing cached LLM instance.")
    _cached_llm_instance = None

# --- Deprecated Function (for reference during refactoring) ---
# def _get_llm(force_reload: bool = False) -> BaseChatModel:
#     """
#     DEPRECATED: Use get_llm() and clear_llm_instance_cache() instead.
#     Initializes and returns the appropriate LLM based on ACTIVE config.
#     Uses a singleton pattern but allows forced reload.
#     """
#     global _llm
#     if _llm is None or force_reload:
#         # ... old logic ...
#     if _llm is None:
#         raise RuntimeError("LLM could not be initialized.")
#     return _llm