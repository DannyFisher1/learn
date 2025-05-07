# app/services/chat_service.py

import json
import logging
import uuid
import asyncio
import time
from typing import Dict, Any, List, AsyncGenerator, Tuple, Union, Optional

from fastapi import BackgroundTasks

# Langchain imports
from langchain_core.messages import (
    AIMessageChunk, HumanMessage, AIMessage, BaseMessage, ToolMessage, SystemMessage
)
from langchain_core.runnables import RunnableConfig
from langchain_core.documents import Document

# App imports
from app import schemas, config
from app.utils import get_logger, serialize_intermediate_steps, serialize_documents
# --- Use LangGraph App ---
from app.core.ai.agents.executor import get_langgraph_app, AgentState
# -------------------------
from app.core.jobs.store import get_job_store_instance
logger = get_logger(__name__)

# --- Project Generator Import (No Change) ---
try:
    from app.core.project_generator.workflow import execute_project_generation_workflow
    PROJECT_GENERATOR_AVAILABLE = True
    logger.info("Project Generator workflow ('execute_project_generation_workflow') loaded successfully.")
except ImportError:
    logger.warning("Project Generator workflow ('execute_project_generation_workflow') not found. The 'generate_software_project' tool will not function.")
    PROJECT_GENERATOR_AVAILABLE = False
    async def execute_project_generation_workflow(request: str) -> AsyncGenerator[Dict[str, Any], None]:
         # This placeholder ensures the background task doesn't crash immediately if the import fails
         yield {
             "type": "final_status",
             "status": "Failed",
             "message": "Error: Project Generator workflow component is not available.",
             "project_name": "Unavailable",
             "output_dir": None,
             "tests_passed": None,
             "errors": ["Project Generator workflow component is not available."],
             "total_time": 0
         }
         # The 'raise' below was removed to allow the background task to report the error via the job store
         # raise NotImplementedError("Project Generator workflow is not available.")

# --- AgentNotReadyError (No Change) ---
class AgentNotReadyError(Exception):
    """Exception raised when the agent/graph is not ready."""
    pass

# --- Background Task Runner (Refined Result Handling) ---
async def run_project_gen_in_background(job_id: str, project_request: str):
    """Runs the project generation workflow, updating status in the RedisJobStore."""
    try:
        job_store = get_job_store_instance()
    except Exception as store_err:
        logger.error(f"BG Job [{job_id}]: Failed to get Job Store instance: {store_err}", exc_info=True)
        return

    start_time = time.time()
    logger.info(f"BG Job [{job_id}]: Starting generation for: '{project_request[:100]}...'")
    await job_store.update_job(job_id, {"status": "running", "started_at": start_time})

    status, result_message, output_path, error_details = "running", None, None, None

    try:
        final_result = None
        # Process the async generator from the workflow
        async for update in execute_project_generation_workflow(project_request):
            # Optional: Log progress updates if needed from the workflow
            if update.get("type") == "status":
                logger.info(f"BG Job [{job_id}] Workflow Status [{update.get('step')}]: {update.get('message')}")
            # Capture the final status update
            if update.get("type") == "final_status":
                final_result = update
                break # Stop processing after final status

        if final_result:
            final_status_str = final_result.get("status", "Unknown").lower()
            result_message = final_result.get("message", "No final message.")
            errors_from_workflow = final_result.get("errors", [])

            if "success" in final_status_str or "completed" in final_status_str and not errors_from_workflow:
                status = "completed"
                output_path = final_result.get("output_dir")
                logger.info(f"BG Job [{job_id}]: COMPLETED. Message: {result_message}")
            elif "warning" in final_status_str or errors_from_workflow:
                 status = "failed" # Treat completion with warnings/errors as failure for job status
                 error_details = result_message # Use the final message as error detail
                 if errors_from_workflow:
                      error_details += f" | Workflow Errors: {'; '.join(errors_from_workflow)}"
                 logger.warning(f"BG Job [{job_id}]: COMPLETED WITH ISSUES/FAILED. Message: {error_details}")
            else: # Explicit failure or unknown status
                status = "failed"
                error_details = result_message
                logger.error(f"BG Job [{job_id}]: FAILED. Message: {error_details}")
        else:
             # Handle case where generator finished without yielding final_status
             status = "failed"
             error_details = "Project generation workflow finished without providing a final status update."
             logger.error(f"BG Job [{job_id}]: FAILED - {error_details}")

    except Exception as e:
        status = "failed"
        error_details = f"An unexpected error occurred during project generation execution: {str(e)}"
        logger.exception(f"BG Job [{job_id}]: UNEXPECTED ERROR during workflow execution.")

    end_time = time.time()
    duration = end_time - start_time
    final_update = {
        "status": status,
        "ended_at": end_time,
        "duration_seconds": round(duration, 2),
        "result_message": result_message if status == "completed" else None, # Only store result message on success
        "error_message": error_details if status == "failed" else None, # Only store error on failure
        "output_path": output_path,
    }
    await job_store.update_job(job_id, final_update)
    logger.info(f"BG Job [{job_id}]: Final status '{status}' updated in Redis.")


# --- Non-Streaming Handler (LangGraph - Checked) ---
async def handle_chat_request(
    request: schemas.AskRequest,
    background_tasks: BackgroundTasks
) -> schemas.AskResponse:
    """
    Handles non-streaming chat requests using the LangGraph App.
    Triggers background job if project generator tool is called.
    """
    # --- Prepare Input Messages for Graph State ---
    base_question = request.question; input_prefix = ""
    has_filenames = bool(request.filenames and len(request.filenames) > 0); has_tag = bool(request.tag_filter)
    if has_filenames and has_tag: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
    elif has_filenames: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
    elif has_tag: input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
    user_input_content = f"{input_prefix}{base_question}"
    messages: List[BaseMessage] = []
    if request.chat_history:
        for msg in request.chat_history:
            sender = msg.get('sender'); text = msg.get('text', '')
            if sender == 'user': messages.append(HumanMessage(content=text))
            elif sender == 'ai': messages.append(AIMessage(content=text))
    messages.append(HumanMessage(content=user_input_content))
    graph_input: AgentState = {"messages": messages}
    logger.info(f"NON-STREAMING (LangGraph): Invoking graph with {len(messages)} messages.")
    # -------------------------------------------

    final_state: Optional[AgentState] = None
    try:
        langgraph_app = get_langgraph_app()
        config: RunnableConfig = {"recursion_limit": 15} # Slightly increased limit
        final_state = await langgraph_app.ainvoke(graph_input, config=config)
        logger.info(f"NON-STREAMING (LangGraph): Graph invocation completed.")
    except RuntimeError as rte: raise AgentNotReadyError(f"LangGraph App execution failed: {rte}") from rte
    except Exception as e: raise RuntimeError(f"An unexpected error occurred communicating with LangGraph App: {e}") from e

    if not final_state or not final_state.get("messages"):
        logger.error("NON-STREAMING (LangGraph): Final state or messages missing.")
        return schemas.AskResponse(answer="Sorry, I couldn't process your request.", intermediate_steps=[])

    # --- Process Final State ---
    final_messages = final_state["messages"]
    final_answer_msg = final_messages[-1] if final_messages else None
    final_answer_content = "Sorry, the interaction ended unexpectedly."
    if isinstance(final_answer_msg, AIMessage): final_answer_content = final_answer_msg.content

    # --- Extract Intermediate Steps & Check for Project Gen ---
    project_gen_triggered = False
    project_request_arg = None
    intermediate_steps_list: List[Tuple[Dict, Any]] = []
    processed_tool_call_ids = set() # Ensure we only process each call+result once

    for i, msg in enumerate(final_messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tool_call in msg.tool_calls:
                 tool_call_id = tool_call.get('id')
                 if not tool_call_id or tool_call_id in processed_tool_call_ids: continue

                 tool_message_found = False
                 for next_msg_idx in range(i + 1, len(final_messages)):
                    next_msg = final_messages[next_msg_idx]
                    if isinstance(next_msg, ToolMessage) and next_msg.tool_call_id == tool_call_id:
                        tool_result = next_msg.content
                        tool_message_found = True
                        action_dict = {
                            "tool": tool_call.get('name', 'UnknownTool'),
                            "tool_input": tool_call.get('args', {}),
                            "log": f"Tool Used: {tool_call.get('name')}" # Simplified log
                        }
                        intermediate_steps_list.append((action_dict, tool_result))
                        processed_tool_call_ids.add(tool_call_id) # Mark as processed

                        if action_dict["tool"] == "generate_software_project":
                            if not PROJECT_GENERATOR_AVAILABLE:
                                final_answer_content = "Sorry, the project generation feature is currently unavailable."
                                project_gen_triggered = False
                                logger.warning("NON-STREAMING (LangGraph): Project generator tool called but not available.")
                            else:
                                project_gen_triggered = True
                                project_request_arg = action_dict["tool_input"]
                                logger.info("NON-STREAMING (LangGraph): 'generate_software_project' tool call detected.")
                        break # Found the matching ToolMessage
                 if not tool_message_found: logger.warning(f"NON-STREAMING (LangGraph): No ToolMessage found for call ID {tool_call_id}")

    serialized_steps = serialize_intermediate_steps(intermediate_steps_list)

    # --- Handle Response based on Tool Call ---
    if project_gen_triggered and project_request_arg is not None:
        request_str = json.dumps(project_request_arg) if isinstance(project_request_arg, dict) else str(project_request_arg)
        job_id = str(uuid.uuid4())
        logger.info(f"NON-STREAMING (LangGraph): Initializing project generation Job [{job_id}] in Redis.")
        try:
            job_store = get_job_store_instance()
            initial_job_data = { "submitted_at": time.time(), "request": request_str, "status": "pending", "started_at": None, "ended_at": None, "duration_seconds": None, "result_message": None, "error_message": None, "output_path": None }
            await job_store.initialize_job(job_id, initial_job_data)
            background_tasks.add_task(run_project_gen_in_background, job_id, request_str)
            answer = f"Okay, I've started generating the project (Job ID: {job_id}). This might take some time. You can check the status using the job ID."
        except Exception as store_err:
             logger.error(f"NON-STREAMING (LangGraph): Failed to initialize Job [{job_id}] in Redis: {store_err}", exc_info=True)
             answer = "Sorry, there was an error initiating the project generation background job."
    else:
        answer = final_answer_content.strip() or "Sorry, I couldn't generate a response."

    source_documents = [] # RAG context not easily extracted here

    return schemas.AskResponse(
        answer=answer,
        source_documents=source_documents,
        intermediate_steps=serialized_steps
    )


# --- Streaming Handler (LangGraph - Revised Parsing) ---
async def handle_chat_request_stream(
    request: schemas.AskRequest,
    background_tasks: BackgroundTasks
) -> AsyncGenerator[Dict[str, str], None]:
    """
    Handles streaming chat requests using LangGraph App's astream_log.
    Triggers background job if project generator tool is called.
    Maps graph log events to SSE events for the frontend.
    """
    # --- Prepare Input Messages ---
    base_question = request.question; input_prefix = ""
    has_filenames = bool(request.filenames and len(request.filenames) > 0); has_tag = bool(request.tag_filter)
    if has_filenames and has_tag: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
    elif has_filenames: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
    elif has_tag: input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
    user_input_content = f"{input_prefix}{base_question}"
    messages: List[BaseMessage] = []
    if request.chat_history:
        for msg in request.chat_history:
             sender = msg.get('sender'); text = msg.get('text', '')
             if sender == 'user': messages.append(HumanMessage(content=text))
             elif sender == 'ai': messages.append(AIMessage(content=text))
    messages.append(HumanMessage(content=user_input_content))
    graph_input: AgentState = {"messages": messages}
    logger.info(f"STREAMING (LangGraph): Starting graph stream with {len(messages)} messages.")
    # -----------------------------

    # --- Streaming Logic Variables ---
    langgraph_app = None
    project_gen_triggered = False
    project_request_arg: Optional[Union[str, Dict]] = None
    job_id: Optional[str] = None
    final_event_processed = False
    # Track tool calls and their results via IDs
    pending_tool_calls: Dict[str, Dict] = {} # Store call details {tool_call_id: call_dict}
    processed_step_pairs: set = set() # Store (tool_call_id, is_final) to prevent duplicate yields

    try:
        langgraph_app = get_langgraph_app()
        if not langgraph_app: raise AgentNotReadyError("Failed to initialize LangGraph App.")

        config: RunnableConfig = {"recursion_limit": 15} # Slightly increased limit
        logger.info("Invoking LangGraph App astream_log...")

        # --- Process LangGraph Log Stream ---
        async for chunk in langgraph_app.astream_log(graph_input, config=config, include_types=["llm", "tool"]):
            # logger.debug(f"Raw Log Chunk: {chunk.ops}") # Optional: Intense debugging

            for op in chunk.ops:
                path = op.get("path", "")
                value = op.get("value")

                # --- Check for AIMessage containing Token Chunk (Streaming Output) ---
                # Paths might involve indices like '/logs/agent/streamed_output_chunk' or updates to messages
                # A reliable way is to check the *type* of the value when it modifies the messages list
                if path.startswith("/messages/") and isinstance(value, AIMessageChunk):
                     token = value.content
                     if token and not project_gen_triggered:
                         # logger.debug(f"Token Stream: {token}") # Debug
                         yield {"event": "token", "data": json.dumps({"token": token})}
                     continue # Handled this op

                # --- Check for Agent Output containing Tool Calls ---
                # This typically appears when the agent node finishes
                # Look for an AIMessage added to the state
                if path == "/messages/-" and isinstance(value, AIMessage) and value.tool_calls:
                     logger.info(f"STREAMING: Agent node output contains {len(value.tool_calls)} tool call(s).")
                     for tool_call in value.tool_calls:
                         tool_call_id = tool_call.get('id')
                         if not tool_call_id: continue

                         action_dict = { "tool": tool_call.get('name'), "tool_input": tool_call.get('args'), "log": f"Starting tool {tool_call.get('name')}" }
                         pending_tool_calls[tool_call_id] = action_dict # Store for matching with result

                         # Yield partial step event if not already yielded for this ID
                         step_key = (tool_call_id, False) # False indicates partial step
                         if step_key not in processed_step_pairs:
                             step_tuple = [(action_dict, "⏳ Processing...")]
                             try:
                                 serialized = serialize_intermediate_steps(step_tuple)
                                 yield {"event": "step", "data": json.dumps({"step": serialized[0]})}
                                 processed_step_pairs.add(step_key)
                             except Exception as e: logger.error(f"Error serializing partial step for {tool_call_id}: {e}")
                     continue # Handled this op

                # --- Check for Tool Output (ToolMessage) ---
                # This typically appears when the tool node finishes
                if path == "/messages/-" and isinstance(value, ToolMessage):
                     tool_call_id = value.tool_call_id
                     observation = value.content
                     logger.info(f"STREAMING: Received ToolMessage result for call ID {tool_call_id}.")

                     original_action = pending_tool_calls.pop(tool_call_id, None) # Get and remove pending call
                     if original_action:
                         original_action["log"] = f"Completed tool {original_action.get('tool')}" # Update log
                         step_tuple = [(original_action, observation)]

                         # Check specifically for project generator completion
                         if original_action.get("tool") == "generate_software_project":
                             if not PROJECT_GENERATOR_AVAILABLE:
                                 # Overwrite observation with error message
                                 step_tuple = [(original_action, "Error: Project Generation feature is unavailable.")]
                                 project_gen_triggered = False
                                 logger.warning("STREAMING (LangGraph): Project generator tool finished but not available.")
                             else:
                                 project_gen_triggered = True
                                 project_request_arg = original_action.get("tool_input") # Store input args
                                 logger.info("STREAMING (LangGraph): 'generate_software_project' tool call finished.")

                         # Yield final step event if not already yielded for this ID
                         step_key = (tool_call_id, True) # True indicates final step
                         if step_key not in processed_step_pairs:
                             try:
                                 serialized = serialize_intermediate_steps(step_tuple)
                                 yield {"event": "step_final", "data": json.dumps({"step": serialized[0]})}
                                 processed_step_pairs.add(step_key)
                             except Exception as e: logger.error(f"Error serializing final step for {tool_call_id}: {e}")
                     else:
                          logger.warning(f"STREAMING (LangGraph): Received ToolMessage for ID {tool_call_id}, but no pending call found.")
                     continue # Handled this op


        # --- After Stream Loop ---
        logger.info("LangGraph stream log async for loop FINISHED.")
        final_event_processed = True

        # --- Trigger Background Task OR Finalize Normal Answer ---
        if project_gen_triggered and project_request_arg is not None:
            request_str = json.dumps(project_request_arg) if isinstance(project_request_arg, dict) else str(project_request_arg)
            job_id = str(uuid.uuid4())
            logger.info(f"STREAMING (LangGraph): Initializing and adding project generation Job [{job_id}] to background tasks.")
            try:
                job_store = get_job_store_instance()
                initial_job_data = { "submitted_at": time.time(), "request": request_str, "status": "pending", "started_at": None, "ended_at": None, "duration_seconds": None, "result_message": None, "error_message": None, "output_path": None }
                await job_store.initialize_job(job_id, initial_job_data)
                background_tasks.add_task(run_project_gen_in_background, job_id, request_str)
                yield {"event": "final_message", "data": json.dumps({"message": f"Okay, I've started generating the project (Job ID: {job_id}). This might take some time. You can check the status using the job ID."})}
            except Exception as store_err:
                logger.error(f"STREAMING (LangGraph): Failed to initialize Job [{job_id}] in Redis: {store_err}", exc_info=True)
                yield {"event": "error", "data": json.dumps({"error": "Failed to initiate background job."})}
        else:
            # If project gen wasn't triggered, the answer was streamed via tokens.
            logger.info("STREAMING (LangGraph): Project generator not triggered. Yielding final message.")
            yield {"event": "final_message", "data": json.dumps({"message": "Processing complete."})}

        # --- End of Stream Event ---
        yield {"event": "end", "data": json.dumps({})}

    # --- Error Handling ---
    except AgentNotReadyError as anre:
        logger.error(f"AgentNotReadyError during streaming setup: {anre}", exc_info=True)
        if not final_event_processed: yield {"event": "error", "data": json.dumps({"error": f"Agent not ready: {anre}"})}; yield {"event": "end", "data": json.dumps({})}
    except Exception as e:
        logger.error(f"Unexpected error during LangGraph streaming: {e}", exc_info=True)
        if not final_event_processed: yield {"event": "error", "data": json.dumps({"error": f"An unexpected error occurred: {e}"})}; yield {"event": "end", "data": json.dumps({})}


# --- Get Job Status (No Change) ---
async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves status for a background job from the RedisJobStore."""
    try: job_store = get_job_store_instance()
    except Exception as store_err: logger.error(f"Failed to get Job Store instance for get_job_status: {store_err}", exc_info=True); return None
    return await job_store.get_job(job_id)