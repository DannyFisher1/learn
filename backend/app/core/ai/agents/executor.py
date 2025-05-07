# app/core/ai/agents/executor.py

import logging
import os
from typing import Optional, TypedDict, Annotated, Sequence, List, Union, Dict, Any
# import operator # Not used
import json

# Langchain & LangGraph imports
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage # HumanMessage, AIMessage, ToolMessage removed as not directly used here for construction
# from langchain_core.agents import AgentAction, AgentFinish # Not directly used
# from langchain_community.tools.convert_to_openai import format_tool_to_openai_tool # Not used

# --- LangGraph Imports ---
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.runnables import RunnableLambda # RunnablePassthrough removed as not used

# ***** V_SCRATCH_FIX: Import MemorySaver *****
from langgraph.checkpoint.memory import MemorySaver
# *********************************************

# App imports
from app import config
from app.core.ai.llm import get_llm, clear_llm_instance_cache
from app.core.ai.agents.tools import tools # Assuming this correctly lists your tools
from app.utils import get_logger

logger = get_logger(__name__)

# --- Define LangGraph State ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# --- Helper Function to Log Agent Output ---
def log_agent_output(llm_response: BaseMessage) -> BaseMessage:
    """Logs the raw output from the LLM within the agent node before formatting."""
    try:
        if hasattr(llm_response, 'dict'): # For Pydantic models like AIMessage
            log_output = json.dumps(llm_response.dict(), indent=2)
        elif isinstance(llm_response, BaseMessage): # Fallback for other BaseMessage types
             log_output = f"Type: {type(llm_response).__name__}\nContent Snippet: {str(llm_response.content)[:200]}...\nTool Calls: {getattr(llm_response, 'tool_calls', 'N/A')}"
        else:
            log_output = str(llm_response) # General fallback
    except Exception as log_err:
        logger.warning(f"Could not serialize LLM response for agent output logging: {log_err}")
        log_output = str(llm_response) # Fallback on serialization error
    logger.debug(f"--- AGENT NODE RAW LLM OUTPUT ---\n{log_output}\n------------------------------")
    return llm_response

# --- Helper Function to format agent output ---
def format_agent_output_for_state(llm_response: BaseMessage) -> Dict[str, Any]:
    """Wraps the LLM response in the dictionary structure expected by AgentState for update."""
    return {"messages": [llm_response]}

# --- Agent Node Factory ---
def create_agent_node(llm: BaseChatModel, system_prompt: str):
    """
    Factory function to create the agent node runnable.
    Logs the LLM output before formatting it for state update.
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    # Bind tools if OpenAI and tools are provided. Other models might handle tools differently or via agent/executor.
    llm_with_tools = llm
    if config.ACTIVE_AI_PROVIDER == "openai" and tools: # Ensure tools list is not empty
        logger.debug(f"Agent Node: Binding {len(tools)} tools directly to OpenAI LLM.")
        llm_with_tools = llm.bind_tools(tools)
    elif tools: # For Ollama or other providers, a different binding mechanism might be used by the agent itself.
        logger.debug(f"Agent Node: Tools available, but direct LLM binding is specific to OpenAI. Provider: {config.ACTIVE_AI_PROVIDER}")


    agent_runnable = (
        prompt
        | llm_with_tools
        | RunnableLambda(log_agent_output) 
        | RunnableLambda(format_agent_output_for_state)
    )
    return agent_runnable


# --- Tool Execution Node (Using Prebuilt) ---
tool_node = ToolNode(tools) # This uses the 'tools' list imported from app.core.ai.agents.tools

# --- Graph Definition ---
_cached_langgraph_app: Optional[any] = None
_memory_saver: Optional[MemorySaver] = None # Cache the checkpointer instance

def get_langgraph_app(force_reload: bool = False) -> any:
    """
    Initializes and returns the compiled LangGraph application.
    Uses cached instance unless force_reload is True.
    Includes a MemorySaver checkpointer to enable get_state().
    """
    global _cached_langgraph_app, _memory_saver
    if force_reload or _cached_langgraph_app is None:
        logger.info(f"Initializing LangGraph App (Force Reload: {force_reload})")

        if force_reload:
            logger.debug("Force Reload requested: Clearing LLM instance cache first.")
            clear_llm_instance_cache() # Assuming this clears the LLM used by the agent
            _cached_langgraph_app = None
            _memory_saver = None # Also clear the checkpointer if reloading graph

        try:
            # --- Load System Prompt ---
            system_prompt_content = "You are LearnMate, an advanced AI assistant." # Default
            # Assuming config.BASE_DIR points to the 'backend' directory
            prompt_file_path = os.path.join(config.BASE_DIR, "prompts", "system_prompt.txt")
            try:
                with open(prompt_file_path, "r", encoding='utf-8') as f: 
                    system_prompt_content = f.read()
                logger.info(f"Successfully loaded system prompt from {prompt_file_path}")
            except FileNotFoundError:
                logger.warning(f"System prompt file not found at {prompt_file_path}. Using default.")
            except Exception as e:
                 logger.warning(f"Error loading system prompt file {prompt_file_path}: {e}. Using default.")
            
            # --- Get LLM ---
            logger.debug("Getting LLM instance for LangGraph...")
            llm = get_llm() # This gets the currently configured LLM (OpenAI or Ollama)
            logger.debug("LLM instance obtained.")
            
            # --- Create Agent Node ---
            agent_runnable = create_agent_node(llm, system_prompt_content)
            
            # --- Define the Graph Workflow ---
            workflow = StateGraph(AgentState)
            workflow.add_node("agent", agent_runnable)
            
            # 'tool_node' is already defined globally using ToolNode(tools)
            logger.debug("Graph Nodes: Using prebuilt 'ToolNode' for the 'action' node.")
            workflow.add_node("action", tool_node) 
            
            workflow.set_entry_point("agent")
            
            logger.debug("Graph Edge: Using standard 'tools_condition' for routing from 'agent'.")
            workflow.add_conditional_edges(
                "agent",
                tools_condition, # This prebuilt condition checks for tool_calls in AIMessage
                {"tools": "action", END: END} # If tool_calls, go to "action"; otherwise, go to END
            )
            
            workflow.add_edge("action", "agent") # Edge back from tool execution to agent for processing results

            # --- Initialize MemorySaver Checkpointer ---
            if _memory_saver is None:
                logger.debug("Initializing new MemorySaver for LangGraph checkpointer.")
                _memory_saver = MemorySaver()
            
            logger.debug("Compiling LangGraph with MemorySaver checkpointer...")
            compiled_app = workflow.compile(checkpointer=_memory_saver) # Compile with the checkpointer
            logger.info("LangGraph App compiled successfully with MemorySaver.")
            _cached_langgraph_app = compiled_app
            
        except Exception as e:
            logger.error(f"Failed to initialize LangGraph App: {e}", exc_info=True)
            _cached_langgraph_app = None
            _memory_saver = None # Clear on failure
            raise RuntimeError(f"LangGraph App initialization failed: {e}") from e

    if _cached_langgraph_app is None:
         logger.critical("LangGraph App is None after initialization attempt!")
         raise RuntimeError("LangGraph App is not available after initialization attempt.")

    logger.debug("Returning compiled LangGraph App instance.")
    return _cached_langgraph_app

# --- Cache Clearing ---
def clear_langgraph_cache():
    """Clears the cached LangGraph app instance and its checkpointer."""
    global _cached_langgraph_app, _memory_saver
    logger.info("Clearing cached LangGraph App instance and MemorySaver.")
    _cached_langgraph_app = None
    _memory_saver = None