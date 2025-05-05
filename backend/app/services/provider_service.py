# app/services/provider_service.py

import logging
import asyncio
from typing import Literal

# App imports
from app import config
from app.utils import get_logger
# Import core component getters AND cache clear functions
from app.core.components.vector_store import get_vectorstore, clear_vectorstore_cache # <<< Added clear cache
from app.core.ai.llm import clear_llm_instance_cache # <<< Added clear cache
from app.core.ai.agents.executor import get_agent_executor, clear_agent_executor_cache # <<< Added clear cache
from app.core.ai.agents.chains import clear_combine_docs_chain_cache # <<< Added clear cache
# We don't need to import the getters for LLM/Chains here as executor handles them

logger = get_logger(__name__)

async def switch_active_provider(new_provider: Literal['ollama', 'openai']) -> bool:
    """
    Switches the active AI provider asynchronously. Clears relevant component
    caches before triggering re-initialization via threaded calls.

    This function orchestrates the change by:
    1. Clearing caches for LLM, VectorStore, Chains, and Agent Executor.
    2. Updating the central configuration state.
    3. Forcing reload of Embeddings (via vector store) and Agent Executor asynchronously.

    Args:
        new_provider: The provider to switch to ('ollama' or 'openai').

    Returns:
        True if the switch and re-initialization were successful.

    Raises:
        ValueError: If the provider cannot be switched due to configuration issues.
        RuntimeError: If a core component fails to re-initialize.
    """
    current_provider = config.ACTIVE_AI_PROVIDER
    if new_provider == current_provider:
        logger.info(f"Provider is already set to {current_provider.upper()}. No switch needed.")
        return True

    logger.info(f"Attempting to switch active provider from {current_provider.upper()} to {new_provider.upper()} asynchronously...")

    original_provider = current_provider # Store for potential revert on error

    try:
        # --- Step 1: Clear Caches ---
        # Clear caches *before* changing config and triggering reloads
        logger.debug("Clearing all relevant component caches...")
        clear_llm_instance_cache()
        clear_vectorstore_cache() # Assumes this clears embeddings indirectly too
        clear_combine_docs_chain_cache()
        clear_agent_executor_cache()
        logger.debug("Component caches cleared.")

        # --- Step 2: Update Configuration State (Sync, assumed fast) ---
        logger.debug(f"Updating active provider in config to {new_provider.upper()}...")
        config.update_active_provider(new_provider) # Can raise ValueError
        logger.debug(f"Config updated. Active provider is now {config.ACTIVE_AI_PROVIDER.upper()}.")


        # --- Step 3: Force Reload Components Asynchronously ---
        # Now that caches are clear and config is updated, these calls will
        # force re-creation using the new settings.

        # Embeddings (via vector store)
        logger.info("Forcing reload of embeddings via vector store re-initialization (in thread)...")
        # Pass force_reload_embeddings=True to ensure embedding function re-creation inside get_vectorstore
        await asyncio.to_thread(get_vectorstore, force_reload_embeddings=True)
        logger.info("Embeddings reloaded successfully (via vector store).")

        # Agent Executor (which includes LLM and chains)
        logger.info("Forcing reload of Agent Executor (which includes LLM/Chains) (in thread)...")
        # Pass force_reload=True to ensure executor and its dependencies are rebuilt
        await asyncio.to_thread(get_agent_executor, force_reload=True)
        logger.info("Agent Executor reloaded successfully.")


        # --- Success ---
        logger.info(f"Successfully switched provider to {new_provider.upper()} and re-initialized components.")
        return True

    except (ValueError, RuntimeError) as config_or_init_error:
         logger.error(f"Failed to switch provider to {new_provider.upper()}: {config_or_init_error}", exc_info=False)
         # Attempt to Revert Config State
         logger.warning(f"Attempting to revert configuration back to {original_provider.upper()}...")
         try:
             config.update_active_provider(original_provider)
             # Clear caches again after revert attempt? Maybe not essential.
             logger.info(f"Configuration reverted to {config.ACTIVE_AI_PROVIDER.upper()}. Component state might be inconsistent - restart recommended.")
         except Exception as revert_error:
              logger.error(f"Failed to revert configuration after switch error: {revert_error}", exc_info=True)
         raise config_or_init_error

    except Exception as e:
        logger.error(f"Unexpected error during provider switch to {new_provider.upper()}: {e}", exc_info=True)
        # Attempt to Revert Config State
        logger.warning(f"Attempting to revert configuration back to {original_provider.upper()} due to unexpected error...")
        try:
            config.update_active_provider(original_provider)
            logger.info(f"Configuration reverted to {config.ACTIVE_AI_PROVIDER.upper()}. Component state might be inconsistent - restart recommended.")
        except Exception as revert_error:
            logger.error(f"Failed to revert configuration after switch error: {revert_error}", exc_info=True)
        raise RuntimeError(f"An unexpected error occurred while switching providers: {e}")