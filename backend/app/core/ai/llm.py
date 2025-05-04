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

# --- Global Variable for LLM Caching ---
_llm: Optional[BaseChatModel] = None

# --- LLM Initialization ---
def _get_llm(force_reload: bool = False) -> BaseChatModel:
    """
    Initializes and returns the appropriate LLM based on ACTIVE config.
    Uses a singleton pattern but allows forced reload.
    """
    global _llm
    if _llm is None or force_reload:
        provider = config.ACTIVE_AI_PROVIDER
        model_name = config.ACTIVE_LLM_MODEL
        logger.info(f"Initializing LLM (Provider: {provider.upper()}, Model: {model_name}, Force Reload: {force_reload})")
        try:
            if provider == "ollama":
                _llm = ChatOllama(
                    model=model_name,
                    base_url=config.OLLAMA_BASE_URL,
                    temperature=0.1 # Keep temperature low for agent consistency maybe
                )
            elif provider == "openai":
                if not config.OPENAI_API_KEY:
                    error_msg = "OpenAI API Key not found for OpenAI LLM."
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                # OpenAI Functions/Tools agents work best with models supporting function calling
                llm_model_name = model_name
                if "gpt-3.5" not in llm_model_name and "gpt-4" not in llm_model_name:
                     logger.warning(f"Selected OpenAI model {llm_model_name} might not fully support function calling needed for optimal agent performance.")

                _llm = ChatOpenAI(
                    model=llm_model_name,
                    temperature=0.1, # Keep temperature low for agent consistency maybe
                    api_key=config.OPENAI_API_KEY
                )
            else:
                error_msg = f"Unsupported AI_PROVIDER for LLM: {provider}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            logger.info("LLM initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}", exc_info=True)
            _llm = None # Ensure reset on failure
            raise
    # Check if _llm is None after attempt (should be caught by raise, but defensive)
    if _llm is None:
        raise RuntimeError("LLM could not be initialized.")
    return _llm