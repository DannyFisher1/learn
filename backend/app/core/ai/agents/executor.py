# app/core/ai/agents/executor.py

import logging
from typing import Optional
import os

# Langchain imports
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models import BaseChatModel
from langchain import hub
from langchain.agents import AgentExecutor, create_react_agent, create_openai_tools_agent

# App imports
from app import config
# --- Updated LLM import ---
from app.core.ai.llm import get_llm, clear_llm_instance_cache # <<< Import new functions
# --------------------------
from app.core.ai.agents.tools import tools
from app.core.ai.agents.chains import setup_combine_docs_chain # Keep this import
from app.utils import get_logger

logger = get_logger(__name__)

# --- Agent Executor Cache ---
# Stores the singleton instance for the current configuration
_cached_agent_executor: Optional[AgentExecutor] = None

# --- Agent Executor Setup ---
def get_agent_executor(force_reload: bool = False) -> AgentExecutor:
    """
    Initializes and returns the AgentExecutor. Uses cached instance unless
    force_reload is True. Handles LLM cache clearing on force_reload.
    """
    global _cached_agent_executor
    # Use a combined condition: reload if forced OR if no cached executor exists
    if force_reload or _cached_agent_executor is None:
        logger.info(f"Initializing Agent Executor (Force Reload: {force_reload})")

        # --- Clear LLM cache if forcing reload ---
        if force_reload:
            logger.debug("Force Reload requested: Clearing LLM instance cache first.")
            clear_llm_instance_cache()
            # Also clear the agent executor cache itself
            _cached_agent_executor = None
        # -----------------------------------------

        try:
            # --- Read System Prompt (No change here) ---
            system_prompt_content = "You are LearnMate, an advanced AI Learning Assistant..." # Use your full prompt
            prompt_file_path = os.path.join(config.BASE_DIR, "prompts", "system_prompt.txt")
            try:
                with open(prompt_file_path, "r", encoding='utf-8') as f: # Added encoding
                    raw_prompt_content = f.read()
                # system_prompt_content = raw_prompt_content.replace("{", "{{").replace("}", "}}") # Escaping might not be needed with ChatPromptTemplate
                system_prompt_content = raw_prompt_content # Use raw if ChatPromptTemplate handles it
                logger.info(f"Successfully loaded system prompt from {prompt_file_path}")
            except FileNotFoundError:
                logger.warning(f"System prompt file not found at {prompt_file_path}. Using default.")
                system_prompt_content = "You are a helpful assistant." # Fallback default
            except Exception as e:
                logger.error(f"Error reading system prompt file {prompt_file_path}: {e}. Using default.")
                system_prompt_content = "You are a helpful assistant." # Fallback default
            # --------------------------------------------

            # 1. Get the LLM instance using the new getter
            # This will now use the cached instance unless clear_llm_instance_cache() was called
            logger.debug("Getting LLM instance for Agent Executor...")
            llm = get_llm() # <<< Use the new getter
            logger.debug("LLM instance obtained.")

            # 2. Ensure the Combine Docs Chain is ready
            # Pass force_reload flag - setup_combine_docs_chain needs update
            # to use the new get_llm() and handle force_reload appropriately.
            # For now, assume it works correctly after its own refactor.
            logger.debug("Setting up Combine Docs Chain...")
            setup_combine_docs_chain(force_reload_llm=force_reload)
            logger.debug("Combine Docs Chain setup complete.")


            # 3. Select Agent Type and Prompt (No change here)
            if not tools:
                 logger.warning("No tools found/imported for the agent executor.")

            if config.ACTIVE_AI_PROVIDER == "openai":
                logger.info("Using OpenAI Tools Agent")
                # Use the loaded system prompt content
                prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt_content),
                    MessagesPlaceholder("chat_history", optional=True),
                    ("human", "{input}"),
                    MessagesPlaceholder("agent_scratchpad"),
                ])
                agent = create_openai_tools_agent(llm, tools, prompt)
            else: # Ollama uses ReAct agent
                logger.info("Using ReAct Agent")
                # ReAct prompt might need adjustment to include the detailed system prompt effectively
                react_prompt = hub.pull("hwchase17/react-chat")
                # Potentially modify react_prompt messages here if needed
                agent = create_react_agent(llm, tools, react_prompt)

            # 4. Create the Agent Executor instance
            logger.debug("Creating AgentExecutor instance...")
            agent_executor_instance = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True, # Keep verbose for debugging
                handle_parsing_errors="Check available tools and your input format, or ask me to try again.", # More user-friendly error
                max_iterations=5, # Keep max iterations reasonable
                return_intermediate_steps=True,
                # Consider adding memory if chat_history placeholder is used extensively
            )
            logger.info("Agent Executor initialized successfully (intermediate steps ENABLED).")

            # --- Cache the newly created instance ---
            _cached_agent_executor = agent_executor_instance
            # --------------------------------------

        except Exception as e:
            logger.error(f"Failed to initialize Agent Executor: {e}", exc_info=True)
            _cached_agent_executor = None # Reset cache on failure
            raise RuntimeError(f"Agent Executor initialization failed: {e}") from e

    # Final check before returning
    if _cached_agent_executor is None:
         logger.critical("Agent executor is None after initialization attempt!")
         raise RuntimeError("Agent Executor is not available after initialization attempt.")

    logger.debug("Returning Agent Executor instance.")
    return _cached_agent_executor

def clear_agent_executor_cache():
    """Clears the cached agent executor instance."""
    global _cached_agent_executor
    logger.info("Clearing cached Agent Executor instance.")
    _cached_agent_executor = None