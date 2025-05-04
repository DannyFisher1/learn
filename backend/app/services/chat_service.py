# app/services/chat_service.py

import json
import logging
from typing import Dict, Any, List, AsyncGenerator, Tuple, Union

# Langchain imports
from langchain_core.messages import AIMessageChunk, HumanMessage, AIMessage, BaseMessage
from langchain_core.agents import AgentAction, AgentFinish # Import AgentFinish
from langchain_core.runnables import RunnableConfig # For streaming config

# App imports
from app import schemas, config
from app.utils import get_logger, serialize_intermediate_steps # Import serializer from utils
from app.core.ai.agents.executor import get_agent_executor # Agent executor function
# logger = get_logger(__name__) # Keep logger import commented out if needed elsewhere

from langchain_core.documents import Document


logger = get_logger(__name__)


# (AgentNotReadyError class definition if not in common.py)
class AgentNotReadyError(Exception):
    """Exception raised when the agent is not ready to stream."""
    pass

async def handle_chat_request(request: schemas.AskRequest) -> schemas.AskResponse:
    """
    Orchestrates the process of handling a chat question: prepares input
    (including filter context), invokes the AI agent, and formats the response.

    Args:
        request: The AskRequest object containing the question and optional context/filters.

    Returns:
        An AskResponse object with the answer and intermediate steps.

    Raises:
        AgentNotReadyError: If the agent executor cannot be retrieved.
        ValueError: If the input request is invalid.
        RuntimeError: For unexpected errors during agent invocation.
    """
    # 1. Prepare filters based on request
    filters = {}
    if request.filenames: # Check if list is not empty
        filters["source_file"] = request.filenames # Pass the list directly for $in operator
    # --- Pass tag_filter if provided ---
    if request.tag_filter:
        filters["tag"] = request.tag_filter
    # -------------------------------

    # --- Log corrected filters ---
    # filter_log = f"Filenames={request.filenames}" if request.filenames else "None"
    # filter_log += f", Tag='{request.tag_filter}'" if request.tag_filter else ""
    # logger.info(f"Handling chat request. Question: '{request.question[:100]}...' Filters: {filter_log}")
    # ---------------------------

    # 2. Format chat history (if any)

    # --- Prepare Agent Input ---
    base_question = request.question
    input_prefix = "" # Context to prepend to the question for the agent

    # --- Build context prefix based on new `filenames` list and `tag_filter` ---
    has_filenames = bool(request.filenames and len(request.filenames) > 0)
    has_tag = bool(request.tag_filter)

    if has_filenames and has_tag:
        filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"
        input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
        # logger.info(f"Agent request filtered by Filenames: {request.filenames} AND Tag: '{request.tag_filter}'")
    elif has_filenames:
        filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"
        input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
        # logger.info(f"Agent request filtered by Filenames: {request.filenames}")
    elif has_tag:
        input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
        # logger.info(f"Agent request filtered by Tag: '{request.tag_filter}'")
    # else:
        # logger.info("Agent request applies to all documents (no specific filename or tag filter).")
    # --------------------------------------------------------------------------

    # Combine prefix and base question for the main agent input
    agent_main_input = f"{input_prefix}{base_question}"

    # Prepare the final input dictionary for the agent executor
    agent_input: Dict[str, Any] = {"input": agent_main_input}

    # --- Map and Add Chat History ---
    if request.chat_history:
        langchain_history: List[BaseMessage] = []
        for msg in request.chat_history:
            # --- Use dictionary access --- 
            sender = msg.get('sender')
            text = msg.get('text', '') # Use get with default for safety

            if sender == 'user':
                langchain_history.append(HumanMessage(content=text))
            elif sender == 'ai':
                langchain_history.append(AIMessage(content=text))
            # else:
                # logger.warning(f"Unknown sender type in chat history: {sender}")
            # ---------------------------
        
        agent_input["chat_history"] = langchain_history
        # logger.info(f"Passing {len(langchain_history)} mapped history turns to agent.")
    # else:
        # logger.info("No chat history provided.")
        # If your agent *requires* chat_history, uncomment the line below:
        # agent_input["chat_history"] = []
    # -------------------------------

    # ... (Alternative Input Strategy comment omitted) ...

    # logger.debug(f"Final agent input dictionary (history mapped): {agent_input}")

    # --- Invoke Agent (Non-Streaming) ---
    try:
        agent_executor = get_agent_executor() # Retrieve the initialized executor
        # logger.info(f"Invoking the agent executor with input: '{agent_main_input[:150]}...'")
        # Use invoke for the non-streaming version
        agent_response = await agent_executor.ainvoke(agent_input)
        # logger.info("Agent invocation complete.")
        # logger.debug(f"Full agent response: {agent_response}")
    except RuntimeError as rte:
        # logger.error(f"Runtime error during agent execution: {rte}", exc_info=True)
        raise AgentNotReadyError(f"Agent execution failed: {rte}")
    except Exception as e:
        # logger.error(f"Unexpected error invoking agent: {e}", exc_info=True)
        raise RuntimeError(f"An unexpected error occurred while communicating with the agent: {e}")

    # --- Process Agent Response ---
    answer = agent_response.get("output", "").strip()
    if not answer:
        # logger.warning("Agent did not produce a final answer ('output' field missing or empty).")
        answer = "Sorry, I couldn't generate a response for that request."

    # logger.info(f"Agent produced answer length: {len(answer)}")

    # Extract and serialize intermediate steps
    intermediate_steps = []
    raw_steps = agent_response.get("intermediate_steps")
    if raw_steps:
        # logger.info(f"Agent returned {len(raw_steps)} intermediate steps.")
        try:
            intermediate_steps = serialize_intermediate_steps(raw_steps)
            # logger.debug(f"Serialized intermediate steps: {intermediate_steps}")
        except Exception as e:
            # logger.error(f"Failed to serialize intermediate steps: {e}", exc_info=True)
            intermediate_steps = [{"error": "Failed to serialize agent steps."}]
    # else:
         # logger.info("Agent did not return intermediate steps.")

    # Source documents placeholder
    source_documents = []
    # logger.debug("Source document retrieval from agent response is currently not implemented.")

    # --- Format and Return Response ---
    return schemas.AskResponse(
        answer=answer,
        source_documents=source_documents,
        intermediate_steps=intermediate_steps
    )

async def handle_chat_request_stream(request: schemas.AskRequest) -> AsyncGenerator[Dict[str, str], None]:
    """
    Handles a chat request and streams the agent's response using Server-Sent Events,
    parsing events from Langchain's `astream_events`. Now includes yielding RAG context.

    Yields:
        Dict[str, str]: Dictionaries containing 'event' and 'data' keys for SSE.
                       Includes 'token', 'step', 'step_final', 'rag_context', 'error', 'end'.
    """
    # --- Input Preparation (remains the same) ---
    filters = {}
    if request.filenames: filters["source_file"] = request.filenames
    if request.tag_filter: filters["tag"] = request.tag_filter

    filter_log = f"Filenames={request.filenames}" if request.filenames else "None"
    filter_log += f", Tag='{request.tag_filter}'" if request.tag_filter else ""
    logger.info(f"Streaming request. Question: '{request.question[:100]}...' Filters: {filter_log}")

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

    def serialize_documents(documents: List[Document]) -> List[Dict[str, Any]]:
        return [doc.to_dict() for doc in documents]

    if request.chat_history:
        langchain_history: List[BaseMessage] = []
        for msg in request.chat_history:
            sender = msg.get('sender')
            text = msg.get('text', '')
            if sender == 'user': langchain_history.append(HumanMessage(content=text))
            elif sender == 'ai': langchain_history.append(AIMessage(content=text))
        agent_input["chat_history"] = langchain_history
        logger.info(f"Passing {len(langchain_history)} history turns to agent (streaming).")
    else:
        logger.info("No chat history provided (streaming).")

    logger.debug(f"Agent input for streaming: {agent_input}")

    # --- Streaming Logic ---
    current_action: AgentAction | None = None
    agent_executor = None
    combine_docs_chain_name = "RunnableAssign<context>|RunnableParallel<input,context>|RunnableAssign<answer>" # Default name often complex, adjust if needed

    try:
        logger.info("Getting agent executor...")
        agent_executor = get_agent_executor() # Retrieve executor
        if not agent_executor:
             raise AgentNotReadyError("Failed to initialize agent executor.") # Raise specific error

        logger.info(f"Invoking agent executor astream_events for: '{agent_main_input[:150]}...'")

        async for event in agent_executor.astream_events(agent_input, version="v1"):
            kind = event["event"]
            name = event.get("name", "")
            event_data = event.get("data", {})
            run_id = event.get("run_id") # For correlation if needed
            tags = event.get("tags", []) # Tags might help identify chains

            # logger.debug(f"[SSE Stream] Event: {kind}, Name: {name}, Tags: {tags}, Data Keys: {list(event_data.keys())}")

            # --- Yield RAG Context Event ---
            # Identify the start of the combine docs chain.
            # The exact name/tags might vary based on LangChain version and agent setup.
            # Check if the chain that 'create_stuff_documents_chain' creates is starting.
            # Often the input data structure is a good clue ('input' and 'context' keys).
            if kind == "on_chain_start":
                chain_input = event_data.get("input", {})
                # Check if input looks like what combine_docs_chain expects
                if isinstance(chain_input, dict) and "input" in chain_input and "context" in chain_input:
                    context_docs = chain_input.get("context")
                    # Verify it's a list and likely contains Document objects
                    if isinstance(context_docs, list) and (len(context_docs) == 0 or isinstance(context_docs[0], Document)):
                        logger.info(f"Detected start of potential CombineDocsChain (Name: {name}). Found {len(context_docs)} context docs.")
                        try:
                            serialized_context = serialize_documents(context_docs) # Use the helper
                            if serialized_context:
                                logger.debug(f"Yielding rag_context event with {len(serialized_context)} serialized docs.")
                                yield {"event": "rag_context", "data": json.dumps({"context": serialized_context})}
                            else:
                                logger.info("No context documents to yield for rag_context event.")
                        except Exception as e:
                             logger.error(f"Failed to serialize/yield RAG context: {e}", exc_info=True)
                             # Optionally yield an error event for context failure
                             # yield {"event": "error", "data": json.dumps({"error": f"Failed to process RAG context: {e}"})}

            # --- Yield Token Event ---
            elif kind == "on_llm_stream" or kind == "on_chat_model_stream":
                chunk_content = event_data.get("chunk", "")
                token = None
                if isinstance(chunk_content, str) and chunk_content:
                    token = chunk_content
                elif isinstance(chunk_content, AIMessageChunk) and chunk_content.content and isinstance(chunk_content.content, str):
                     token = chunk_content.content

                if token:
                    # logger.debug(f"Yielding token: {token[:50]}...") # Less verbose logging
                    yield {"event": "token", "data": json.dumps({"token": token})}

            # --- Yield Partial Step Event ---
            elif kind == "on_tool_start":
                tool_name = event.get("name")
                tool_input_data = event_data.get("input")
                if tool_name and tool_input_data is not None:
                    try:
                        current_action = AgentAction(tool=str(tool_name), tool_input=tool_input_data, log="...")
                        step_tuple: List[Tuple[AgentAction, str]] = [(current_action, "⏳ Processing...")]
                        serialized = serialize_intermediate_steps(step_tuple)
                        if serialized: yield {"event": "step", "data": json.dumps({"step": serialized[0]})}
                    except Exception as e:
                        logger.error(f"Error processing on_tool_start: {e}")
                        current_action = None
                else: current_action = None

            # --- Yield Final Step Event ---
            elif kind == "on_tool_end":
                observation = event_data.get("output")
                if observation is not None and current_action is not None:
                    try:
                        step_tuple: List[Tuple[AgentAction, Any]] = [(current_action, observation)]
                        serialized = serialize_intermediate_steps(step_tuple)
                        if serialized: yield {"event": "step_final", "data": json.dumps({"step": serialized[0]})}
                    except Exception as e:
                         logger.error(f"Error processing on_tool_end: {e}")
                         yield {"event": "error", "data": json.dumps({"error": f"Failed to process tool result: {e}"})}
                    current_action = None # Reset action

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