# app/core/ai/agents/chains.py

import logging
from typing import Optional
from pathlib import Path

# Langchain imports
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.runnables import Runnable
from langchain_core.messages import SystemMessage

# App imports
from app import config
from app.core.ai.llm import _get_llm # Import LLM getter
from app.utils import get_logger

logger = get_logger(__name__)

# --- Global for Caching the Chain ---
_combine_docs_chain: Optional[Runnable] = None

# --- Setup Function for the Combine Docs Chain ---
def setup_combine_docs_chain(force_reload_llm: bool = False):
    """
    Sets up the LLM and the chain that combines documents based on a template.
    This is specifically used by the RAG tool.

    Args:
        force_reload_llm: If True, forces re-initialization of the underlying LLM.
                          The chain itself is rebuilt if it doesn't exist or if LLM is reloaded.
    """
    global _combine_docs_chain
    llm_instance = _get_llm(force_reload=force_reload_llm)

    if _combine_docs_chain is None or force_reload_llm:
        logger.info(f"Setting up CombineDocsChain (Force Reload LLM: {force_reload_llm}).")
        try:
            template_path = Path("prompts/rag_agent.txt")
            if not template_path.is_file():
                logger.error(f"RAG Prompt template file not found at: {template_path}")
                raise FileNotFoundError(f"Prompt file not found: {template_path}")

            template_string = template_path.read_text(encoding='utf-8')

            # --- Pre-process the template string to escape literal braces --- 
            template_string = template_path.read_text(encoding='utf-8')
            safe_template_string = (
                template_string
                .replace("{", "{{")
                .replace("}", "}}")
                .replace("{{context}}", "{context}")
                .replace("{{input}}", "{input}")
            )
            # -------------------------------------------------------------
            # print("TEMPLATE STRING:\n", safe_template_string)

            # --- Use PromptTemplate with explicit variables AND pre-processed string ---
            prompt = PromptTemplate(
                template=safe_template_string,
                input_variables=["context", "input"] 
            )
            # -----------------------------------------------------------------------

            # Pass the PromptTemplate directly to the chain
            _combine_docs_chain = create_stuff_documents_chain(llm_instance, prompt)
            logger.info("CombineDocsChain setup complete.")

        except Exception as e:
            logger.error(f"Error setting up CombineDocs chain: {e}", exc_info=True)
            _combine_docs_chain = None # Reset on failure
            raise RuntimeError(f"Failed to setup CombineDocsChain: {e}") # Raise error

# Function to get the chain, ensuring it's set up
def get_combine_docs_chain() -> Runnable:
    """Returns the combine docs chain, setting it up if necessary."""
    if _combine_docs_chain is None:
        logger.warning("CombineDocsChain accessed before explicit setup. Setting up now.")
        setup_combine_docs_chain() # Use default (no force reload)

    if _combine_docs_chain is None: # Check again after setup attempt
         raise RuntimeError("CombineDocsChain could not be initialized.")

    return _combine_docs_chain