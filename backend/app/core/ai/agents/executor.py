# app/core/ai/agents/executor.py

import logging
from typing import Optional
import os # <-- Add os import for path joining

# Langchain imports
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
# REMOVED: from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.language_models import BaseChatModel
# REMOVED: from langchain_core.runnables import Runnable
from langchain import hub
from langchain.agents import AgentExecutor, create_react_agent, create_openai_tools_agent

# App imports
from app import config
from app.core.ai.llm import _get_llm
from app.core.ai.agents.tools import tools # Import the list of tools
# --- Import the setup function from the new chains module ---
from app.core.ai.agents.chains import setup_combine_docs_chain
# -----------------------------------------------------------
from app.utils import get_logger

logger = get_logger(__name__)

# --- Global for Agent Executor Caching ---
_agent_executor: Optional[AgentExecutor] = None
# --- REMOVED: _combine_docs_chain global variable ---

# --- REMOVED: setup_combine_docs_chain function definition ---


# --- Agent Executor Setup ---
def get_agent_executor(force_reload: bool = False) -> AgentExecutor:
    """Initializes and returns the AgentExecutor."""
    global _agent_executor
    if _agent_executor is None or force_reload:
        logger.info(f"Initializing Agent Executor (Force Reload: {force_reload})")
        try:
            # --- Read System Prompt ---
            system_prompt_content = "You are a helpful assistant." # Default prompt
            prompt_file_path = os.path.join(config.BASE_DIR, "prompts", "system_prompt.txt") # Use BASE_DIR
            try:
                with open(prompt_file_path, "r") as f:
                    raw_prompt_content = f.read()
                # --- Escape curly braces for LangChain ---
                system_prompt_content = raw_prompt_content.replace("{", "{{").replace("}", "}}")
                # -----------------------------------------
                logger.info(f"Successfully loaded and escaped system prompt from {prompt_file_path}")
            except FileNotFoundError:
                logger.warning(f"System prompt file not found at {prompt_file_path}. Using default prompt.")
            except Exception as e:
                logger.error(f"Error reading system prompt file {prompt_file_path}: {e}. Using default prompt.")
            # -------------------------

            # 1. Get the LLM (handles its own reloading/caching)
            # Pass the force_reload flag down, as LLM might need reloading
            llm = _get_llm(force_reload=force_reload)

            # 2. Ensure the Combine Docs Chain (for RAG tool) is ready
            # Call the setup function imported from chains.py
            # Pass the force_reload flag in case the LLM it uses needed reloading
            setup_combine_docs_chain(force_reload_llm=force_reload)
            # If setup_combine_docs_chain fails, it raises an error.

            # 3. Select Agent Type and Prompt based on Provider
            if not tools:
                 logger.warning("No tools found/imported for the agent executor.")

            if config.ACTIVE_AI_PROVIDER == "openai":
                logger.info("Using OpenAI Tools Agent")
                prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt_content), # <-- Use the loaded prompt
                    MessagesPlaceholder("chat_history", optional=True),
                    ("human", "{input}"),
                    MessagesPlaceholder("agent_scratchpad"),
                ])
                agent = create_openai_tools_agent(llm, tools, prompt)
            else: # Ollama uses ReAct agent
                logger.info("Using ReAct Agent")
                prompt = hub.pull("hwchase17/react-chat")
                agent = create_react_agent(llm, tools, prompt)

            # 4. Create the Agent Executor instance
            _agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True,
                handle_parsing_errors="Check available tools and your input format.",
                max_iterations=5,
                return_intermediate_steps=True,
            )
            logger.info("Agent Executor initialized successfully (intermediate steps ENABLED).")

        except Exception as e:
            logger.error(f"Failed to initialize Agent Executor: {e}", exc_info=True)
            _agent_executor = None # Reset on failure
            # Wrap the original error for clarity
            raise RuntimeError(f"Agent Executor initialization failed: {e}")

    if _agent_executor is None:
         # This case should ideally be covered by the exception above, but defensive check
         raise RuntimeError("Agent Executor is not available after initialization attempt.")

    return _agent_executor