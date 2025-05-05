# app/core/ai/agents/chains.py

import logging
from typing import Optional
from pathlib import Path
import os # <<< Added import for path joining

# Langchain imports
from langchain_core.prompts import PromptTemplate # Removed ChatPromptTemplate, SystemMessage
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.runnables import Runnable

# App imports
from app import config
# --- Updated LLM import ---
from app.core.ai.llm import get_llm, clear_llm_instance_cache # <<< Import new functions
# --------------------------
from app.utils import get_logger

logger = get_logger(__name__)

# --- Module-level Cache for the Chain ---
_cached_combine_docs_chain: Optional[Runnable] = None

# --- Setup Function for the Combine Docs Chain ---
def setup_combine_docs_chain(force_reload_llm: bool = False):
    """
    Sets up the LLM and the chain that combines documents based on a template.
    This is specifically used by the RAG tool. Uses cached instance unless
    LLM is force reloaded or chain is not yet created.

    Args:
        force_reload_llm: If True, forces re-initialization of the underlying LLM
                          (by clearing its cache) and forces this chain to be rebuilt.
    """
    global _cached_combine_docs_chain

    # --- Clear LLM cache first if forcing reload ---
    if force_reload_llm:
        logger.debug("CombineDocsChain setup: Force Reload requested, clearing LLM cache.")
        clear_llm_instance_cache()
        # Also clear this chain's cache
        _cached_combine_docs_chain = None
    # -----------------------------------------------

    # --- Rebuild chain if needed ---
    if _cached_combine_docs_chain is None:
        logger.info(f"Setting up CombineDocsChain (LLM Forced Reload: {force_reload_llm}, Chain Cache Empty: {_cached_combine_docs_chain is None}).")

        try:
            # --- Get LLM instance (uses new getter, potentially cached) ---
            logger.debug("Getting LLM instance for CombineDocsChain...")
            llm_instance = get_llm()
            logger.debug("LLM instance obtained for CombineDocsChain.")
            # ------------------------------------------------------------

            # --- Load Prompt Template ---
            # Use BASE_DIR from config for reliable path
            template_filename = "rag_agent.txt"
            template_path = os.path.join(config.BASE_DIR, "prompts", template_filename)
            logger.debug(f"Loading RAG prompt from: {template_path}")

            if not os.path.isfile(template_path): # Use os.path.isfile for consistency
                logger.error(f"RAG Prompt template file not found at: {template_path}")
                raise FileNotFoundError(f"Prompt file not found: {template_path}")

            with open(template_path, 'r', encoding='utf-8') as f:
                 template_string = f.read()

            # Pre-processing template_string removed as PromptTemplate handles it well usually.
            # If you encounter issues with complex prompts, re-introduce specific replacements.
            # safe_template_string = (
            #     template_string
            #     .replace("{", "{{")
            #     .replace("}", "}}")
            #     .replace("{{context}}", "{context}")
            #     .replace("{{input}}", "{input}")
            # )
            # logger.debug("RAG prompt loaded and processed.")

            # --- Create PromptTemplate ---
            # Ensure your rag_agent.txt uses exactly "{context}" and "{input}"
            prompt = PromptTemplate.from_template(template_string)
            # ---------------------------

            # --- Create and Cache the Chain ---
            chain_instance = create_stuff_documents_chain(llm_instance, prompt)
            _cached_combine_docs_chain = chain_instance # Cache the new instance
            logger.info("CombineDocsChain setup complete and cached.")
            # --------------------------------

        except Exception as e:
            logger.error(f"Error setting up CombineDocs chain: {e}", exc_info=True)
            _cached_combine_docs_chain = None # Reset cache on failure
            raise RuntimeError(f"Failed to setup CombineDocsChain: {e}") from e
    else:
         logger.debug("Using cached CombineDocsChain instance.")


# --- Function to get the chain, ensuring it's set up ---
def get_combine_docs_chain() -> Runnable:
    """
    Returns the combine docs chain, setting it up if necessary (without forcing reload).
    """
    global _cached_combine_docs_chain
    if _cached_combine_docs_chain is None:
        logger.warning("CombineDocsChain accessed before explicit setup or after cache clear. Setting up now.")
        # Call setup without forcing LLM reload by default when accessed lazily
        setup_combine_docs_chain(force_reload_llm=False)

    # Check again after setup attempt
    if _cached_combine_docs_chain is None:
         logger.critical("CombineDocsChain is None after setup attempt!")
         raise RuntimeError("CombineDocsChain could not be initialized.")

    return _cached_combine_docs_chain

def clear_combine_docs_chain_cache():
    """Clears the cached combine docs chain instance."""
    global _cached_combine_docs_chain
    logger.info("Clearing cached CombineDocsChain instance.")
    _cached_combine_docs_chain = None