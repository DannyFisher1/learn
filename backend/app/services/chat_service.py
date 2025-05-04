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
    filter_log = f"Filenames={request.filenames}" if request.filenames else "None"
    filter_log += f", Tag='{request.tag_filter}'" if request.tag_filter else ""
    logger.info(f"Handling chat request. Question: '{request.question[:100]}...' Filters: {filter_log}")
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
        logger.info(f"Agent request filtered by Filenames: {request.filenames} AND Tag: '{request.tag_filter}'")
    elif has_filenames:
        filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"
        input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
        logger.info(f"Agent request filtered by Filenames: {request.filenames}")
    elif has_tag:
        input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
        logger.info(f"Agent request filtered by Tag: '{request.tag_filter}'")
    else:
        logger.info("Agent request applies to all documents (no specific filename or tag filter).")
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
            else:
                logger.warning(f"Unknown sender type in chat history: {sender}")
            # ---------------------------
        
        agent_input["chat_history"] = langchain_history
        logger.info(f"Passing {len(langchain_history)} mapped history turns to agent.")
    else:
        logger.info("No chat history provided.")
        # If your agent *requires* chat_history, uncomment the line below:
        # agent_input["chat_history"] = []
    # -------------------------------

    # ... (Alternative Input Strategy comment omitted) ...

    logger.debug(f"Final agent input dictionary (history mapped): {agent_input}")

    # --- Invoke Agent (Non-Streaming) ---
    try:
        agent_executor = get_agent_executor() # Retrieve the initialized executor
        logger.info(f"Invoking the agent executor with input: '{agent_main_input[:150]}...'")
        # Use invoke for the non-streaming version
        agent_response = await agent_executor.ainvoke(agent_input)
        logger.info("Agent invocation complete.")
        logger.debug(f"Full agent response: {agent_response}")
    except RuntimeError as rte:
        logger.error(f"Runtime error during agent execution: {rte}", exc_info=True)
        raise AgentNotReadyError(f"Agent execution failed: {rte}")
    except Exception as e:
        logger.error(f"Unexpected error invoking agent: {e}", exc_info=True)
        raise RuntimeError(f"An unexpected error occurred while communicating with the agent: {e}")

    # --- Process Agent Response ---
    answer = agent_response.get("output", "").strip()
    if not answer:
        logger.warning("Agent did not produce a final answer ('output' field missing or empty).")
        answer = "Sorry, I couldn't generate a response for that request."

    logger.info(f"Agent produced answer length: {len(answer)}")

    # Extract and serialize intermediate steps
    intermediate_steps = []
    raw_steps = agent_response.get("intermediate_steps")
    if raw_steps:
        logger.info(f"Agent returned {len(raw_steps)} intermediate steps.")
        try:
            intermediate_steps = serialize_intermediate_steps(raw_steps)
            logger.debug(f"Serialized intermediate steps: {intermediate_steps}")
        except Exception as e:
            logger.error(f"Failed to serialize intermediate steps: {e}", exc_info=True)
            intermediate_steps = [{"error": "Failed to serialize agent steps."}]
    else:
         logger.info("Agent did not return intermediate steps.")

    # Source documents placeholder
    source_documents = []
    logger.debug("Source document retrieval from agent response is currently not implemented.")

    # --- Format and Return Response ---
    return schemas.AskResponse(
        answer=answer,
        source_documents=source_documents,
        intermediate_steps=intermediate_steps
    )

# --- REFACTORED Streaming Function using astream_events ---
async def handle_chat_request_stream(request: schemas.AskRequest) -> AsyncGenerator[Dict[str, str], None]:
    """
    Handles a chat request and streams the agent's response using Server-Sent Events,
    parsing events from Langchain's `astream_events`.

    Yields:
        Dict[str, str]: Dictionaries containing 'event' and 'data' keys for SSE.
                       The 'data' value must be a JSON-encoded string.
    """
    # --- Input Preparation (Same as non-streaming version) ---
    # ... (filter prep, logging, input prep, history mapping - unchanged) ...
    filters = {}
    if request.filenames:
        filters["source_file"] = request.filenames
    if request.tag_filter:
        filters["tag"] = request.tag_filter

    filter_log = f"Filenames={request.filenames}" if request.filenames else "None"
    filter_log += f", Tag='{request.tag_filter}'" if request.tag_filter else ""
    logger.info(f"Handling STREAMING chat request (astream_events). Question: '{request.question[:100]}...' Filters: {filter_log}")

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
            if sender == 'user':
                langchain_history.append(HumanMessage(content=text))
            elif sender == 'ai':
                langchain_history.append(AIMessage(content=text))
        agent_input["chat_history"] = langchain_history
        logger.info(f"Passing {len(langchain_history)} mapped history turns to agent (streaming/events).")
    else:
        logger.info("No chat history provided (streaming/events).")

    logger.debug(f"Final agent input dictionary for streaming/events: {agent_input}")

    # --- Streaming Logic using astream_events ---
    current_action: AgentAction | None = None # Store the action when tool starts
    agent_executor = None # Initialize agent_executor to None

    try:
        # --- Added Logging --- 
        logger.info("Attempting to get agent executor...")
        agent_executor = get_agent_executor()
        if agent_executor:
             logger.info("Successfully retrieved agent executor.")
        else:
             logger.error("Failed to retrieve agent executor (get_agent_executor returned None).")
             # Yield error and end if executor retrieval failed
             yield {"event": "error", "data": json.dumps({"error": "Failed to initialize AI agent."})}
             yield {"event": "end", "data": json.dumps({}) }
             return # Exit the generator
        # ---------------------

        logger.info(f"Invoking agent executor astream_events for: '{agent_main_input[:150]}...'" )
        logger.info("Entering astream_events loop...") # <<< Added Log
        
        # Use astream_events
        async for event in agent_executor.astream_events(agent_input, version="v1"):
            # --- Added Logging --- 
            # logger.debug(f"[astream_events] Received event: {event.get('event')}, Name: {event.get('name')}, Run ID: {event.get('run_id')}")
            # --- Re-enable more detailed logging --- 
            logger.debug(f"[astream_events] Event: {event['event']}, Name: {event.get('name', '')}, Run ID: {event.get('run_id')}, Data Keys: {list(event.get('data', {}).keys())}")
            # ---------------------------------------
            kind = event["event"]
            name = event.get("name", "") # Name of the runnable that emitted the event
            event_data = event.get("data", {}) # The actual data payload
            run_id = event.get("run_id") # ID of the specific run
            # logger.debug(f"[astream_events] Event: {kind}, Name: {name}, Run ID: {run_id}, Data: {event_data}")

            # --- Updated Condition --- 
            if kind == "on_llm_stream" or kind == "on_chat_model_stream":
            # -----------------------
                # Extract and yield token chunk
                chunk_content = event_data.get("chunk", "")
                if isinstance(chunk_content, str) and chunk_content:
                    # logger.debug(f"Yielding token: '{chunk_content}'")
                    # --- Added log before yielding token --- 
                    logger.debug(f"Yielding token event: {chunk_content[:50]}...") 
                    # ---------------------------------------
                    yield {"event": "token", "data": json.dumps({"token": chunk_content})}
                elif isinstance(chunk_content, AIMessageChunk): # Handle AIMessageChunk if present
                    if chunk_content.content and isinstance(chunk_content.content, str):
                        # logger.debug(f"Yielding token from AIMessageChunk: '{chunk_content.content}'")
                        # --- Added log before yielding token --- 
                        logger.debug(f"Yielding token event (from AIMessageChunk): {chunk_content.content[:50]}...") 
                        # ---------------------------------------
                        yield {"event": "token", "data": json.dumps({"token": chunk_content.content})}
            
            elif kind == "on_tool_start":
                # Tool execution is starting, capture the action
                # --- Log the raw event data for inspection ---
                logger.debug(f"[on_tool_start] Raw event: {event}")
                # ---------------------------------------------
                
                tool_name = event.get("name") # Often the tool name is here
                tool_input_data = event_data.get("input") # Often the input dict/str is here

                # --- Attempt to construct AgentAction --- 
                if tool_name and tool_input_data is not None: 
                    try:
                        # Create the AgentAction object
                        constructed_action = AgentAction(
                            tool=str(tool_name), 
                            tool_input=tool_input_data, 
                            log=f"Attempting tool {tool_name} with input {tool_input_data}" # Basic log message
                        )
                        current_action = constructed_action # Store the constructed action
                        logger.info(f"Tool Start (Constructed Action): {current_action.tool}, Input: {current_action.tool_input}")
                        
                        # Create and yield the partial step using the *constructed* action
                        step_tuple_with_placeholder: List[Tuple[AgentAction, str]] = [(current_action, "⏳ Processing...")]
                        serialized_steps = serialize_intermediate_steps(step_tuple_with_placeholder)
                        if serialized_steps:
                            logger.debug(f"Yielding step event (from constructed action): {serialized_steps[0]}")
                            yield {"event": "step", "data": json.dumps({"step": serialized_steps[0]})}
                        else:
                            logger.warning("Serialization resulted in empty partial step (constructed action), not yielding.")
                    except Exception as construction_error:
                        logger.error(f"Failed to construct AgentAction or serialize step: {construction_error}", exc_info=True)
                        current_action = None # Ensure it's None on error
                        yield {"event": "error", "data": json.dumps({"error": f"Failed processing tool start: {construction_error}"})}
                else:
                    # If we couldn't get name/input, log and set current_action to None
                    logger.warning(f"on_tool_start event missing tool name ('{tool_name}') or input data ('{tool_input_data}') in expected keys.")
                    current_action = None
            
            elif kind == "on_tool_end":
                # Tool execution finished, capture the observation
                # --- Add log to inspect event_data['output'] ---
                logger.debug(f"[on_tool_end] Event Data Output: {event_data.get('output')}") 
                # ---------------------------------------------
                observation = event_data.get("output") # Tool output is often here
                if observation is not None and current_action is not None:
                     logger.info(f"Tool End: {current_action.tool}, Observation: {str(observation)[:100]}...")
                     # Create the final step tuple
                     step_tuple: List[Tuple[AgentAction, Any]] = [(current_action, observation)]
                     
                     # --- Add finer logging around step_final --- 
                     logger.debug("Attempting to serialize final step...") 
                     try:
                         serialized_steps = serialize_intermediate_steps(step_tuple)
                         logger.debug("Final step serialized successfully.")
                         if serialized_steps:
                             # Yield the complete step data using 'step_final' event
                             step_final_data = {"event": "step_final", "data": json.dumps({"step": serialized_steps[0]})}
                             logger.debug(f"Prepared step_final_data: {step_final_data}")
                             # --- Wrap yield in try/except --- 
                             try:
                                 logger.debug("Attempting to yield step_final...")
                                 yield step_final_data
                                 logger.debug("Successfully yielded step_final.")
                             except Exception as yield_err:
                                 logger.error(f"Error *during* yield of step_final: {yield_err}", exc_info=True)
                             # ------------------------------
                         else:
                              logger.warning("Serialization resulted in empty final step, not yielding.")
                     except Exception as e:
                         logger.error(f"Serialization failed for final step: {e}", exc_info=True)
                         # --- Yield error if serialization fails --- 
                         try:
                             yield {"event": "error", "data": json.dumps({"error": f"Failed to process final step: {e}"})}
                         except Exception as yield_err_inner:
                             logger.error(f"Error *during* yield of serialization error: {yield_err_inner}", exc_info=True)
                         # -----------------------------------------
                     # Reset current_action after processing the observation
                     current_action = None 
                elif current_action is None:
                     logger.warning("on_tool_end event received but no corresponding action was stored.")
                else: # observation was None
                     logger.warning(f"on_tool_end event received for {name} but observation (data['output']) was None.")

            # --- Can add handling for other event types like on_agent_end if needed ---
            elif kind == "on_chain_end" and name == "AgentExecutor": # Check if this is the end of the main agent run
                # Could potentially extract final answer/steps here if needed, but tokens/tool events are preferred
                final_output = event_data.get("output", {})
                if isinstance(final_output, dict):
                    agent_outcome = final_output.get("output") # Final textual answer
                    # final_steps = final_output.get("intermediate_steps") # Steps might also be here
                    # logger.debug(f"AgentExecutor Finished. Final Answer: {agent_outcome}")
        
        # --- End of event loop ---
        logger.info("Agent event stream finished.")
        yield {"event": "end", "data": json.dumps({}) } # Signal end of stream

    except AgentNotReadyError as anre:
        # --- Added Logging --- 
        logger.error(f"AgentNotReadyError caught during streaming: {anre}", exc_info=True)
        # ---------------------
        yield {"event": "error", "data": json.dumps({"error": f"Agent not ready: {anre}"})} 
        yield {"event": "end", "data": json.dumps({}) } # Ensure stream ends
    except Exception as e:
        # --- Added Logging --- 
        logger.error(f"Generic Exception caught during streaming: {e}", exc_info=True)
        # ---------------------
        yield {"event": "error", "data": json.dumps({"error": f"An unexpected error occurred: {e}"})} 
        yield {"event": "end", "data": json.dumps({}) } # Ensure stream ends