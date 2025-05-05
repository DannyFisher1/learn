# app/services/chat_service.py

import json
import logging
import uuid
import asyncio
import time
from typing import Dict, Any, List, AsyncGenerator, Tuple, Union, Optional
from fastapi import BackgroundTasks

# Langchain imports
from langchain_core.messages import AIMessageChunk, HumanMessage, AIMessage, BaseMessage
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.runnables import RunnableConfig
from langchain_core.documents import Document

# App imports
from app import schemas, config
from app.utils import get_logger, serialize_intermediate_steps, serialize_documents
from app.core.ai.agents.executor import get_agent_executor
# --- Import Job Store ---
from app.core.jobs.store import get_job_store_instance # <<< Import Redis job store getter
# ------------------------

logger = get_logger(__name__)

# --- Import Project Generator Workflow ---
try:
    from app.core.project_generator.workflow import execute_project_generation_workflow # <<< Use correct function name
    PROJECT_GENERATOR_AVAILABLE = True
    logger.info("Project Generator workflow ('execute_project_generation_workflow') loaded successfully.")
except ImportError:
    logger.warning("Project Generator workflow ('execute_project_generation_workflow') not found. The 'generate_software_project' tool will not function.")
    PROJECT_GENERATOR_AVAILABLE = False
    async def execute_project_generation_workflow(request: str):
         raise NotImplementedError("Project Generator workflow is not available.")
# -----------------------------------------


class AgentNotReadyError(Exception):
    """Exception raised when the agent is not ready."""
    pass

# --- Removed In-Memory Job Store ---
# _background_jobs: Dict[str, Dict[str, Any]] = {}
# -----------------------------------


# --- Background Task Runner (Uses RedisJobStore) ---
async def run_project_gen_in_background(job_id: str, project_request: str):
    """Runs the project generation workflow, updating status in the RedisJobStore."""
    # --- Get Job Store Instance ---
    try:
        job_store = get_job_store_instance()
    except Exception as store_err:
         logger.error(f"Background Job [{job_id}]: CRITICAL - Failed to get Job Store instance: {store_err}", exc_info=True)
         # Cannot proceed without the store
         return
    # -----------------------------

    start_time = time.time()
    logger.info(f"Background Job [{job_id}]: Starting project generation for request: '{project_request[:100]}...'")

    # --- Update Job Status: Running ---
    status_update = {
        "status": "running",
        "started_at": start_time,
    }
    await job_store.update_job(job_id, status_update)
    # ---------------------------------

    status = "running" # Local status variable
    result_message = None
    output_path = None
    error_details = None

    if not PROJECT_GENERATOR_AVAILABLE:
        status = "failed"
        error_details = "Project Generator feature is not available in this deployment."
        logger.error(f"Background Job [{job_id}]: FAILED - Project Generator not available.")
    else:
        try:
            # Wrap the potentially synchronous workflow function
            final_message = await asyncio.to_thread(
                execute_project_generation_workflow, project_request
            )
            # --- Parse result ---
            if final_message and isinstance(final_message, str) and "generation finished" in final_message.lower():
                status = "completed"
                result_message = final_message
                try:
                    loc_marker = "Output Location: "; path_part = final_message.split(loc_marker, 1)
                    if len(path_part) > 1: output_path = path_part[1].strip()
                    elif "saved to:" in final_message.lower(): output_path = final_message.split("to:")[-1].strip()
                except Exception as parse_err: logger.warning(f"Background Job [{job_id}]: Could not parse output path: {parse_err}")
                logger.info(f"Background Job [{job_id}]: Project generation COMPLETED.")
            else:
                status = "failed"
                error_details = final_message if isinstance(final_message, str) else "Project generation failed with unknown error/format."
                logger.error(f"Background Job [{job_id}]: Project generation FAILED. Result: {error_details}")
        except Exception as e:
            status = "failed"
            error_details = f"An unexpected error occurred during project generation: {str(e)}"
            logger.exception(f"Background Job [{job_id}]: UNEXPECTED ERROR during project generation.")

    end_time = time.time()
    duration = end_time - start_time

    # --- Update Job Status & Store Final Result (Redis) ---
    final_update = {
        "status": status,
        "ended_at": end_time,
        "duration_seconds": round(duration, 2),
        "result_message": result_message,
        "error_message": error_details,
        "output_path": output_path,
    }
    await job_store.update_job(job_id, final_update)
    logger.info(f"Background Job [{job_id}]: Final status '{status}' updated in Redis job store.")
    # ----------------------------------------------------


# --- Non-Streaming Handler (Uses RedisJobStore) ---
async def handle_chat_request(
    request: schemas.AskRequest,
    background_tasks: BackgroundTasks
) -> schemas.AskResponse:
    """Handles non-streaming chat requests. If project generator is triggered,
       initializes job state in Redis and starts background task."""

    # ... (Input Preparation logic remains the same) ...
    base_question = request.question; input_prefix = ""
    has_filenames = bool(request.filenames and len(request.filenames) > 0); has_tag = bool(request.tag_filter)
    if has_filenames and has_tag: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
    elif has_filenames: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
    elif has_tag: input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
    agent_main_input = f"{input_prefix}{base_question}"; agent_input: Dict[str, Any] = {"input": agent_main_input}; langchain_history: List[BaseMessage] = []
    if request.chat_history:
        for msg in request.chat_history: sender = msg.get('sender'); text = msg.get('text', ''); (langchain_history.append(HumanMessage(content=text)) if sender == 'user' else langchain_history.append(AIMessage(content=text)) if sender == 'ai' else None) # type: ignore
        if langchain_history: agent_input["chat_history"] = langchain_history

    logger.info(f"NON-STREAMING: Final Agent Input Keys: {list(agent_input.keys())}")
    agent_response: Optional[Dict[str, Any]] = None
    # ... (Agent invocation try/except block remains the same) ...
    try:
        agent_executor = get_agent_executor()
        agent_response = await agent_executor.ainvoke(agent_input)
        logger.info(f"NON-STREAMING: Agent Response Keys: {list(agent_response.keys()) if agent_response else 'None'}")
    except RuntimeError as rte: raise AgentNotReadyError(f"Agent execution failed: {rte}") from rte
    except Exception as e: raise RuntimeError(f"An unexpected error occurred while communicating with the agent: {e}") from e

    if not agent_response: return schemas.AskResponse(answer="Sorry, I couldn't process your request.", intermediate_steps=[])

    # --- Check if Project Generator was called ---
    project_gen_triggered = False
    project_request_arg = None
    raw_steps = agent_response.get("intermediate_steps", [])
    final_answer = agent_response.get("output", "")

    if raw_steps:
        for step in raw_steps:
            if isinstance(step, tuple) and len(step) == 2:
                action, observation = step
                if isinstance(action, AgentAction) and action.tool == "generate_software_project":
                    if not PROJECT_GENERATOR_AVAILABLE: final_answer = "Sorry, the project generation feature is currently unavailable."; project_gen_triggered = False; break
                    project_gen_triggered = True
                    project_request_arg = action.tool_input
                    logger.info("NON-STREAMING: 'generate_software_project' tool detected.")
                    break

    # --- Handle Response based on Tool Call ---
    if project_gen_triggered and isinstance(project_request_arg, str):
        job_id = str(uuid.uuid4())
        logger.info(f"NON-STREAMING: Initializing project generation Job [{job_id}] in Redis and adding to background tasks.")
        # --- Initialize Job State in Redis ---
        try:
            job_store = get_job_store_instance()
            initial_job_data = {
                "submitted_at": time.time(),
                "request": project_request_arg,
                # Ensure all fields expected by schema are present or None initially
                "status": "pending", "started_at": None, "ended_at": None,
                "duration_seconds": None, "result_message": None,
                "error_message": None, "output_path": None
            }
            await job_store.initialize_job(job_id, initial_job_data)
        except Exception as store_err:
             logger.error(f"NON-STREAMING: Failed to initialize Job [{job_id}] in Redis: {store_err}", exc_info=True)
             # Return an error response to the user? Or allow agent's original response?
             # For now, let's return a specific error.
             return schemas.AskResponse(
                 answer="Sorry, there was an error initiating the project generation background job.",
                 intermediate_steps=serialize_intermediate_steps(raw_steps) if raw_steps else []
             )
        # -------------------------------------
        background_tasks.add_task(run_project_gen_in_background, job_id, project_request_arg)
        answer = f"Okay, I've started generating the project (Job ID: {job_id}). This might take some time. You can check the status using the job ID."
        intermediate_steps = serialize_intermediate_steps(raw_steps) if raw_steps else []
    else:
        answer = final_answer.strip() or "Sorry, I couldn't generate a response."
        intermediate_steps = serialize_intermediate_steps(raw_steps) if raw_steps else []

    source_documents = []

    return schemas.AskResponse(
        answer=answer,
        source_documents=source_documents,
        intermediate_steps=intermediate_steps
    )


# --- Streaming Handler (Uses RedisJobStore) ---
async def handle_chat_request_stream(
    request: schemas.AskRequest,
    background_tasks: BackgroundTasks
) -> AsyncGenerator[Dict[str, str], None]:
    """
    Handles streaming chat requests. If project generator is triggered,
    initializes job state in Redis, starts background task, yields job start message.
    """
    # ... (Input Preparation logic remains the same) ...
    base_question = request.question; input_prefix = ""; has_filenames = bool(request.filenames and len(request.filenames) > 0); has_tag = bool(request.tag_filter)
    if has_filenames and has_tag: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
    elif has_filenames: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
    elif has_tag: input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
    agent_main_input = f"{input_prefix}{base_question}"; agent_input: Dict[str, Any] = {"input": agent_main_input}; langchain_history: List[BaseMessage] = []
    if request.chat_history:
        for msg in request.chat_history: sender = msg.get('sender'); text = msg.get('text', ''); (langchain_history.append(HumanMessage(content=text)) if sender == 'user' else langchain_history.append(AIMessage(content=text)) if sender == 'ai' else None) # type: ignore
        if langchain_history: agent_input["chat_history"] = langchain_history

    try: loggable_input = json.dumps(agent_input, default=str, indent=2)
    except Exception: loggable_input = str(agent_input)
    logger.debug(f"--- AGENT EXECUTOR INPUT ---\n{loggable_input}\n--------------------------")

    # --- Streaming Logic ---
    agent_executor = None
    project_gen_triggered = False
    project_request_arg: Optional[str] = None
    job_id: Optional[str] = None
    final_event_processed = False

    try:
        agent_executor = get_agent_executor()
        if not agent_executor: raise AgentNotReadyError("Failed to initialize agent executor.")
        logger.info(f"Invoking agent executor astream_events...")

        # --- Process Events ---
        current_action: Optional[AgentAction] = None
        async for event in agent_executor.astream_events(agent_input, version="v1"):
            kind = event["event"]; name = event.get("name", ""); event_data = event.get("data", {})

            # --- Standard Event Yielding ---
            # ... (Keep handlers for on_chain_start, on_llm_stream, on_tool_start, on_agent_finish) ...
            if kind == "on_chain_start":
                 chain_input = event_data.get("input", {}); context_docs = chain_input.get("context")
                 if isinstance(chain_input, dict) and "context" in chain_input and isinstance(context_docs, list) and (len(context_docs) == 0 or isinstance(context_docs[0], Document)):
                      try: serialized_context = serialize_documents(context_docs); yield {"event": "rag_context", "data": json.dumps({"context": serialized_context})}
                      except Exception as e: logger.error(f"Failed to serialize/yield RAG context: {e}", exc_info=True)
            elif kind == "on_llm_stream" or kind == "on_chat_model_stream":
                chunk_content = event_data.get("chunk", ""); token = None
                if isinstance(chunk_content, str): token = chunk_content
                elif isinstance(chunk_content, AIMessageChunk): token = chunk_content.content
                if token and isinstance(token, str) and not project_gen_triggered:
                    yield {"event": "token", "data": json.dumps({"token": token})}
            elif kind == "on_tool_start":
                 tool_name = event.get("name"); tool_input_data = event_data.get("input")
                 if tool_name and tool_input_data is not None:
                     logger.info(f"Tool Start: {tool_name}, Input: {tool_input_data}")
                     try: current_action = AgentAction(tool=str(tool_name), tool_input=tool_input_data, log="..."); step_tuple = [(current_action, "⏳ Processing...")]; serialized = serialize_intermediate_steps(step_tuple); yield {"event": "step", "data": json.dumps({"step": serialized[0]})}
                     except Exception as e: logger.error(f"Error processing on_tool_start: {e}"); current_action = None
                 else: current_action = None
            elif kind == "on_agent_finish": # Log agent finish
                 logger.debug(f"--- AGENT EXECUTOR FINAL OUTPUT EVENT ({kind}) ---")

            # --- Yield Final Step & Check Project Gen ---
            elif kind == "on_tool_end":
                observation = event_data.get("output"); tool_name = current_action.tool if current_action else 'Unknown'
                logger.debug(f"--- TOOL OBSERVATION RECEIVED (Tool: {tool_name}) ---")
                if current_action is not None:
                    logger.info(f"Tool End: {current_action.tool}")
                    # Check for project generator tool
                    if current_action.tool == "generate_software_project":
                         if not PROJECT_GENERATOR_AVAILABLE: observation = "Error: Project Generation feature is unavailable."; project_gen_triggered = False; logger.warning("STREAMING: Agent called unavailable project generator.")
                         else: project_gen_triggered = True; project_request_arg = current_action.tool_input; logger.info("Detected 'generate_software_project' tool call completion.")
                    # Yield the step_final regardless of which tool it was
                    try: step_tuple = [(current_action, observation)]; serialized = serialize_intermediate_steps(step_tuple); yield {"event": "step_final", "data": json.dumps({"step": serialized[0]})}
                    except Exception as e: logger.error(f"Error processing on_tool_end: {e}"); yield {"event": "error", "data": json.dumps({"error": f"Failed to process tool result: {e}"})}
                    current_action = None


        # --- After Stream Loop ---
        logger.info("Agent event stream async for loop FINISHED.")
        final_event_processed = True

        # --- Trigger Background Task OR Finalize Normal Answer ---
        if project_gen_triggered and isinstance(project_request_arg, str):
            job_id = str(uuid.uuid4())
            logger.info(f"Initializing and adding project generation Job [{job_id}] to background tasks using Redis.")
            # --- Initialize Job State in Redis ---
            try:
                job_store = get_job_store_instance()
                initial_job_data = {
                    "submitted_at": time.time(), "request": project_request_arg,
                    "status": "pending", "started_at": None, "ended_at": None, "duration_seconds": None,
                    "result_message": None, "error_message": None, "output_path": None
                }
                await job_store.initialize_job(job_id, initial_job_data)
            except Exception as store_err:
                logger.error(f"STREAMING: Failed to initialize Job [{job_id}] in Redis: {store_err}", exc_info=True)
                # Yield an error event to the client
                yield {"event": "error", "data": json.dumps({"error": "Failed to initiate background job."})}
                # Still yield end event afterwards
            else:
                # Only add task if initialization succeeded
                background_tasks.add_task(run_project_gen_in_background, job_id, project_request_arg)
                # Yield specific final message
                yield {"event": "final_message", "data": json.dumps({"message": f"Okay, I've started generating the project (Job ID: {job_id}). This might take some time. You can check the status using the job ID."})}
        else:
            # If not project gen, the answer was streamed via tokens.
            logger.info("Project generator not triggered. Answer (if any) was streamed via tokens.")
            yield {"event": "final_message", "data": json.dumps({"message": "Processing complete."})}

        # --- End of Stream Event ---
        yield {"event": "end", "data": json.dumps({})}

    # --- Error Handling ---
    except AgentNotReadyError as anre:
        logger.error(f"AgentNotReadyError during streaming setup: {anre}", exc_info=True)
        if not final_event_processed: yield {"event": "error", "data": json.dumps({"error": f"Agent not ready: {anre}"})}; yield {"event": "end", "data": json.dumps({})}
    except Exception as e:
        logger.error(f"Unexpected error during streaming: {e}", exc_info=True)
        if not final_event_processed: yield {"event": "error", "data": json.dumps({"error": f"An unexpected error occurred: {e}"})}; yield {"event": "end", "data": json.dumps({})}


# --- Function to get job status (Uses RedisJobStore) ---
async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves status for a background job from the RedisJobStore."""
    # --- Get Job Store Instance ---
    try:
        job_store = get_job_store_instance()
    except Exception as store_err:
         logger.error(f"Failed to get Job Store instance for get_job_status: {store_err}", exc_info=True)
         return None # Cannot get status without store
    # -----------------------------
    # Retrieves the job data from Redis via the job store instance
    return await job_store.get_job(job_id)
# ---------------------------------------------------------