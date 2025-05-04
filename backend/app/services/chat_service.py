# app/services/chat_service.py

import json
import logging
from typing import Dict, Any, List, AsyncGenerator, Tuple, Union

# Langchain imports
from langchain_core.messages import AIMessageChunk, HumanMessage, AIMessage, BaseMessage
from langchain_core.agents import AgentAction, AgentFinish # Import AgentFinish
from langchain_core.runnables import RunnableConfig # For streaming config
from langchain_core.documents import Document # Added back if needed by context serialization

# App imports
from app import schemas, config
# Ensure serialize_documents is available if RAG context logging is added later
from app.utils import get_logger, serialize_intermediate_steps, serialize_documents
from app.core.ai.agents.executor import get_agent_executor # Agent executor function

# --- Make sure logger is active ---
logger = get_logger(__name__)
# ---------------------------------

# (AgentNotReadyError class definition if not in common.py)
class AgentNotReadyError(Exception):
    """Exception raised when the agent is not ready to stream."""
    pass

async def handle_chat_request(request: schemas.AskRequest) -> schemas.AskResponse:
    # ... (non-streaming implementation - keep as is for now) ...
    # NOTE: Add similar logging here if you test the non-streaming endpoint
    logger.warning("Non-streaming endpoint invoked. Logging is less detailed here for now.")
    # 1. Prepare filters based on request
    filters = {}
    if request.filenames: filters["source_file"] = request.filenames
    if request.tag_filter: filters["tag"] = request.tag_filter

    # 2. Format chat history (if any)
    base_question = request.question
    input_prefix = ""
    has_filenames = bool(request.filenames and len(request.filenames) > 0)
    has_tag = bool(request.tag_filter)
    if has_filenames and has_tag:
        filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"
        input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
    elif has_filenames:
        filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"
        input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
    elif has_tag:
        input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "

    agent_main_input = f"{input_prefix}{base_question}"
    agent_input: Dict[str, Any] = {"input": agent_main_input}

    if request.chat_history:
        langchain_history: List[BaseMessage] = []
        for msg in request.chat_history:
            sender = msg.get('sender')
            text = msg.get('text', '')
            if sender == 'user': langchain_history.append(HumanMessage(content=text))
            elif sender == 'ai': langchain_history.append(AIMessage(content=text))
        agent_input["chat_history"] = langchain_history

    logger.info(f"NON-STREAMING: Final Agent Input: {agent_input}")

    try:
        agent_executor = get_agent_executor()
        agent_response = await agent_executor.ainvoke(agent_input)
        logger.info(f"NON-STREAMING: Full Agent Response: {agent_response}") # Log full response

    except RuntimeError as rte:
        logger.error(f"NON-STREAMING: Runtime error during agent execution: {rte}", exc_info=True)
        raise AgentNotReadyError(f"Agent execution failed: {rte}")
    except Exception as e:
        logger.error(f"NON-STREAMING: Unexpected error invoking agent: {e}", exc_info=True)
        raise RuntimeError(f"An unexpected error occurred while communicating with the agent: {e}")

    answer = agent_response.get("output", "").strip() or "Sorry, I couldn't generate a response."
    intermediate_steps = []
    raw_steps = agent_response.get("intermediate_steps")
    if raw_steps:
        try:
            intermediate_steps = serialize_intermediate_steps(raw_steps)
        except Exception as e:
            logger.error(f"NON-STREAMING: Failed to serialize intermediate steps: {e}", exc_info=True)
            intermediate_steps = [{"error": "Failed to serialize agent steps."}]

    source_documents = [] # Placeholder

    return schemas.AskResponse(
        answer=answer,
        source_documents=source_documents,
        intermediate_steps=intermediate_steps
    )


# --- Streaming Function with ENHANCED LOGGING ---
async def handle_chat_request_stream(request: schemas.AskRequest) -> AsyncGenerator[Dict[str, str], None]:
    """
    Handles a chat request and streams the agent's response using Server-Sent Events,
    parsing events from Langchain's `astream_events`. Includes enhanced logging.
    """
    # --- Input Preparation (remains the same) ---
    filters = {}
    if request.filenames: filters["source_file"] = request.filenames
    if request.tag_filter: filters["tag"] = request.tag_filter

    filter_log = f"Filenames={request.filenames}" if request.filenames else "None"
    filter_log += f", Tag='{request.tag_filter}'" if request.tag_filter else ""
    logger.info(f"Streaming request. Question='{request.question[:100]}...' Filters=[{filter_log}]")

    base_question = request.question
    input_prefix = ""
    has_filenames = bool(request.filenames and len(request.filenames) > 0)
    has_tag = bool(request.tag_filter)

    if has_filenames and has_tag:
        filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"
        input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
    elif has_filenames:
        filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"
        input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
    elif has_tag:
        input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "

    agent_main_input = f"{input_prefix}{base_question}"
    agent_input: Dict[str, Any] = {"input": agent_main_input}

    if request.chat_history:
        langchain_history: List[BaseMessage] = []
        for msg in request.chat_history:
            sender = msg.get('sender')
            text = msg.get('text', '')
            if sender == 'user': langchain_history.append(HumanMessage(content=text))
            elif sender == 'ai': langchain_history.append(AIMessage(content=text))
        agent_input["chat_history"] = langchain_history
        # logger.info(f"Passing {len(langchain_history)} history turns to agent (streaming).")
    # else:
        # logger.info("No chat history provided (streaming).")

    # --- LOG THE FINAL INPUT TO THE AGENT ---
    # Use pretty printing for better readability of complex structures like history
    try:
        loggable_input = json.dumps(agent_input, default=str, indent=2) # Convert BaseMessages etc. to string
    except Exception:
        loggable_input = str(agent_input) # Fallback
    logger.debug(f"--- AGENT EXECUTOR INPUT ---\n{loggable_input}\n--------------------------")
    # ---------------------------------------

    # --- Streaming Logic ---
    current_action: AgentAction | None = None
    agent_executor = None

    try:
        # logger.info("Getting agent executor...")
        agent_executor = get_agent_executor() # Retrieve executor
        if not agent_executor:
             raise AgentNotReadyError("Failed to initialize agent executor.")

        logger.info(f"Invoking agent executor astream_events...")

        async for event in agent_executor.astream_events(agent_input, version="v1"):
            kind = event["event"]
            name = event.get("name", "")
            event_data = event.get("data", {})
            # run_id = event.get("run_id")
            # tags = event.get("tags", [])

            # Minimal logging for every event (optional)
            # logger.debug(f"[SSE Stream] Event: {kind}, Name: {name}")

            # --- Yield RAG Context Event (Keep for potential future use) ---
            if kind == "on_chain_start":
                chain_input = event_data.get("input", {})
                if isinstance(chain_input, dict) and "input" in chain_input and "context" in chain_input:
                    context_docs = chain_input.get("context")
                    if isinstance(context_docs, list) and (len(context_docs) == 0 or isinstance(context_docs[0], Document)):
                        logger.info(f"CombineDocsChain Start Detected. Input keys: {list(chain_input.keys())}. Context doc count: {len(context_docs)}")
                        try:
                            serialized_context = serialize_documents(context_docs)
                            if serialized_context:
                                logger.debug(f"Yielding rag_context event.")
                                yield {"event": "rag_context", "data": json.dumps({"context": serialized_context})}
                        except Exception as e:
                             logger.error(f"Failed to serialize/yield RAG context: {e}", exc_info=True)

            # --- Yield Token Event ---
            elif kind == "on_llm_stream" or kind == "on_chat_model_stream":
                chunk_content = event_data.get("chunk", "")
                token = None
                if isinstance(chunk_content, str) and chunk_content: token = chunk_content
                elif isinstance(chunk_content, AIMessageChunk) and chunk_content.content and isinstance(chunk_content.content, str): token = chunk_content.content
                if token: yield {"event": "token", "data": json.dumps({"token": token})}

            # --- Yield Partial Step Event ---
            elif kind == "on_tool_start":
                tool_name = event.get("name")
                tool_input_data = event_data.get("input")
                if tool_name and tool_input_data is not None:
                    logger.info(f"Tool Start: {tool_name}, Input: {tool_input_data}") # Log tool start
                    try:
                        current_action = AgentAction(tool=str(tool_name), tool_input=tool_input_data, log="...")
                        step_tuple: List[Tuple[AgentAction, str]] = [(current_action, "⏳ Processing...")]
                        serialized = serialize_intermediate_steps(step_tuple)
                        if serialized: yield {"event": "step", "data": json.dumps({"step": serialized[0]})}
                    except Exception as e: logger.error(f"Error processing on_tool_start: {e}"); current_action = None
                else: current_action = None

            # --- LOG FULL OBSERVATION and Yield Final Step Event ---
            elif kind == "on_tool_end":
                # Get the tool output (observation passed to the agent)
                observation = event_data.get("output")
                # --- LOG THE RAW OBSERVATION RECEIVED BY THE AGENT ---
                try:
                    loggable_observation = json.dumps(observation, default=str, indent=2) # Try pretty print
                except Exception:
                    loggable_observation = str(observation) # Fallback
                tool_name = current_action.tool if current_action else 'Unknown'
                logger.debug(f"--- TOOL OBSERVATION RECEIVED (Tool: {tool_name}) ---\n{loggable_observation}\n--------------------------------")
                # ------------------------------------------------------

                # --- Original logic: Yield step_final with the received observation --- 
                if current_action is not None:
                    logger.info(f"Tool End: {current_action.tool}") # Log tool end
                    try:
                        step_tuple: List[Tuple[AgentAction, Any]] = [(current_action, observation)]
                        serialized = serialize_intermediate_steps(step_tuple)
                        if serialized: yield {"event": "step_final", "data": json.dumps({"step": serialized[0]})}
                    except Exception as e:
                         logger.error(f"Error processing on_tool_end: {e}")
                         yield {"event": "error", "data": json.dumps({"error": f"Failed to process tool result: {e}"})}
                    current_action = None # Reset action
                # -------------------------------------------------------------------

            # --- LOG FINAL AGENT OUTPUT ---
            # Watch for on_agent_finish or relevant on_chain_end
            # Note: 'on_agent_finish' is more common with specific agent types like OpenAI Functions Agent
            # ReAct agents might just end the main chain.
            elif kind == "on_agent_finish" or (kind == "on_chain_end" and name == "AgentExecutor"): # Heuristic check
                final_output_data = event_data.get("output", {})
                try:
                    loggable_output = json.dumps(final_output_data, default=str, indent=2)
                except Exception:
                    loggable_output = str(final_output_data)
                logger.debug(f"--- AGENT EXECUTOR FINAL OUTPUT EVENT ({kind}, Name: {name}) ---\n{loggable_output}\n-------------------------------------")
            # ------------------------------

        # --- End of Stream ---
        logger.info("Agent event stream finished.")
        yield {"event": "end", "data": json.dumps({}) }

    except AgentNotReadyError as anre:
        logger.error(f"AgentNotReadyError during streaming setup: {anre}", exc_info=True)
        yield {"event": "error", "data": json.dumps({"error": f"Agent not ready: {anre}"})}
        yield {"event": "end", "data": json.dumps({}) }
    except Exception as e:
        logger.error(f"Unexpected error during streaming: {e}", exc_info=True)
        yield {"event": "error", "data": json.dumps({"error": f"An unexpected error occurred: {e}"})}
        yield {"event": "end", "data": json.dumps({}) }