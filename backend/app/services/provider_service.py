# app/services/provider_service.py

import logging
from typing import Literal

# App imports
from app import config
from app.utils import get_logger
# Import core components needed for re-initialization
from app.core.components.vector_store import get_vectorstore # To reload embeddings via vector store
from app.core.ai.agents.executor import get_agent_executor # To reload agent/LLM

logger = get_logger(__name__)

def switch_active_provider(new_provider: Literal['ollama', 'openai']) -> bool:
    """
    Switches the active AI provider and triggers re-initialization of
    dependent core components (LLM, Embeddings, Agent Executor).

    This function orchestrates the change by:
    1. Updating the central configuration state.
    2. Forcing a reload of the embedding models (via vector store init).
    3. Forcing a reload of the agent executor (which reloads the LLM and chains).

    Args:
        new_provider: The provider to switch to ('ollama' or 'openai').

    Returns:
        True if the switch and re-initialization were successful.

    Raises:
        ValueError: If the provider cannot be switched due to configuration issues
                    (e.g., missing API key for OpenAI). This is raised by
                    `config.update_active_provider`.
        RuntimeError: If a core component (embeddings, agent executor) fails
                      to re-initialize after the provider switch.
    """
    current_provider = config.ACTIVE_AI_PROVIDER
    if new_provider == current_provider:
        logger.info(f"Provider is already set to {current_provider.upper()}. No switch needed.")
        # Considered successful as the desired state is already met
        return True

    logger.info(f"Attempting to switch active provider from {current_provider.upper()} to {new_provider.upper()}...")

    original_provider = current_provider # Store for potential revert on error

    try:
        # --- Step 1: Update Configuration State ---
        # This function in config.py now handles the check for OpenAI key
        # and raises ValueError if switching to OpenAI without a key.
        logger.debug(f"Updating active provider in config to {new_provider.upper()}...")
        config.update_active_provider(new_provider)
        logger.debug(f"Config updated. Active provider is now {config.ACTIVE_AI_PROVIDER.upper()}.")


        # --- Step 2: Force Reload Embeddings ---
        # Embeddings are tied to the vector store instance via the embedding function.
        # Re-initializing the vector store with force_reload_embeddings=True will
        # trigger the re-initialization of the embeddings using the *new* active provider.
        logger.info("Forcing reload of embeddings via vector store re-initialization...")
        get_vectorstore(force_reload_embeddings=True)
        logger.info("Embeddings reloaded successfully (via vector store).")


        # --- Step 3: Force Reload Agent Executor ---
        # This will automatically re-initialize the LLM using the new active provider
        # and rebuild the agent and chains (including the combine_docs_chain).
        logger.info("Forcing reload of Agent Executor (which includes LLM)...")
        get_agent_executor(force_reload=True)
        logger.info("Agent Executor reloaded successfully.")


        # --- Success ---
        logger.info(f"Successfully switched provider to {new_provider.upper()} and re-initialized components.")
        return True

    except (ValueError, RuntimeError) as config_or_init_error:
         # Catch specific errors from config update or component re-init
         logger.error(f"Failed to switch provider to {new_provider.upper()}: {config_or_init_error}", exc_info=False) # Less verbose logging maybe
         # --- Attempt to Revert Config State ---
         # This is optional but can prevent the config being left in a broken state
         # if, e.g., embeddings loaded but agent failed.
         logger.warning(f"Attempting to revert configuration back to {original_provider.upper()}...")
         try:
             config.update_active_provider(original_provider)
             # Also try to reload components based on the *original* provider state?
             # This could get complex and might be better handled by restarting the app.
             logger.info(f"Configuration reverted to {config.ACTIVE_AI_PROVIDER.upper()}. Component state might be inconsistent - restart recommended.")
         except Exception as revert_error:
              logger.error(f"Failed to revert configuration after switch error: {revert_error}", exc_info=True)

         # Re-raise the original error that caused the switch failure
         raise config_or_init_error

    except Exception as e:
        # Catch any other unexpected errors during the process
        logger.error(f"Unexpected error during provider switch to {new_provider.upper()}: {e}", exc_info=True)
         # Attempt to revert config state here too?
        logger.warning(f"Attempting to revert configuration back to {original_provider.upper()} due to unexpected error...")
        try:
            config.update_active_provider(original_provider)
            logger.info(f"Configuration reverted to {config.ACTIVE_AI_PROVIDER.upper()}. Component state might be inconsistent - restart recommended.")
        except Exception as revert_error:
            logger.error(f"Failed to revert configuration after switch error: {revert_error}", exc_info=True)

        # Raise a generic runtime error for unexpected issues
        raise RuntimeError(f"An unexpected error occurred while switching providers: {e}")

    # This line should not be reachable if exceptions are handled correctly
    # return False