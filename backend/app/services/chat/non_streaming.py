# backend/app/services/chat/non_streaming.py

import json
import logging
import uuid
from typing import Dict, Any, List, Tuple, Union, Optional

from fastapi import BackgroundTasks # Still needed if project gen trigger remains here (though ideally handled by API layer calling jobs_service)

# Langchain imports
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

# App imports
from app import schemas, config
from app.errors import AgentNotReadyError # Import from new location
from app.utils import get_logger, serialize_intermediate_steps
from app.core.ai.agents.executor import get_langgraph_app, AgentState
# --- REMOVED Job Service Direct Imports ---
# from app.services.jobs_service import initialize_project_generation_job, run_project_gen_in_background, PROJECT_GENERATOR_AVAILABLE
# --- Check Project Generator availability directly if needed ---
from app.services.jobs_service import PROJECT_GENERATOR_AVAILABLE # Keep this check if needed

logger = get_logger(__name__)

async def handle_chat_request(
    request: schemas.AskRequest,
    background_tasks: BackgroundTasks # Keep for now if triggering jobs here
) -> schemas.AskResponse:
    """
    Handles non-streaming chat requests.
    Processes agent response and potentially identifies project generation requests.
    """
    logger.info(f"Handling non-streaming request: {request.question[:50]}...")
    base_question = request.question; input_prefix = ""
    has_filenames = bool(request.filenames and len(request.filenames) > 0); has_tag = bool(request.tag_filter)
    # Construct input prefix based on filters
    if has_filenames and has_tag: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
    elif has_filenames: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
    elif has_tag: input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
    user_input_content = f"{input_prefix}{base_question}"

    # Prepare messages for LangGraph
    messages: List[BaseMessage] = []
    if request.chat_history:
        for msg_data in request.chat_history:
            sender = msg_data.get('sender'); text = msg_data.get('text', '')
            if sender == 'user': messages.append(HumanMessage(content=text))
            elif sender == 'ai': messages.append(AIMessage(content=text))
    messages.append(HumanMessage(content=user_input_content))
    graph_input: AgentState = {"messages": messages}

    final_state: Optional[AgentState] = None
    try:
        langgraph_app = get_langgraph_app()
        run_config_obj: RunnableConfig = {"recursion_limit": 25}
        run_config_obj["configurable"] = {"thread_id": str(uuid.uuid4())} # Use unique thread ID
        final_state = await langgraph_app.ainvoke(graph_input, config=run_config_obj)
    except RuntimeError as rte:
        logger.error(f"LangGraph non-streaming execution failed: {rte}", exc_info=True)
        raise AgentNotReadyError(f"Agent execution failed: {rte}") from rte
    except Exception as e:
        logger.error(f"Unexpected error during non-streaming agent invocation: {e}", exc_info=True)
        raise RuntimeError(f"An unexpected error occurred: {e}") from e

    if not final_state or not final_state.get("messages"):
        logger.warning("Non-streaming agent invocation resulted in empty final state or messages.")
        return schemas.AskResponse(answer="Sorry, I couldn't process your request.", intermediate_steps=[])

    final_messages = final_state["messages"]
    final_answer_msg = final_messages[-1] if final_messages else None
    final_answer_content = "Sorry, the interaction ended unexpectedly."

    # Extract final answer text, potentially parsing last tool message
    if isinstance(final_answer_msg, AIMessage):
        final_answer_content = final_answer_msg.content # Default to the AIMessage content
        if final_answer_msg.tool_calls:
             logger.info("Final AI message in non-streaming has tool calls. Parsing last ToolMessage for answer.")
             last_tool_call_id = final_answer_msg.tool_calls[-1].get('id') if final_answer_msg.tool_calls else None
             found_tool_answer = False
             if last_tool_call_id:
                 for msg in reversed(final_messages[:-1]):
                      if isinstance(msg, ToolMessage) and msg.tool_call_id == last_tool_call_id:
                           logger.debug(f"Found ToolMessage for last tool call {last_tool_call_id}. Parsing content.")
                           try:
                               parsed_res = json.loads(msg.content)
                               if isinstance(parsed_res, dict):
                                    extracted_answer = parsed_res.get("answer", parsed_res.get("summary"))
                                    if extracted_answer and isinstance(extracted_answer, str):
                                         final_answer_content = extracted_answer
                                         found_tool_answer = True
                                         logger.info("Using parsed 'answer'/'summary' from tool result as final content.")
                                    else: logger.warning("Parsed tool JSON dict but no valid 'answer' or 'summary' key found.")
                               else: logger.warning("Parsed tool JSON but it wasn't a dictionary.")
                           except (json.JSONDecodeError, TypeError): logger.warning("Could not parse ToolMessage content as JSON, using raw content.")
                           # If parsing fails, final_answer_content remains the original AIMessage.content
                           found_tool_answer = True # Mark as processed, even if using raw/fallback
                           break
             if not found_tool_answer:
                 logger.warning("Final AIMessage had tool calls, but couldn't find corresponding ToolMessage. Using AIMessage.content.")

    # Process intermediate steps
    project_gen_triggered = False; project_request_arg = None
    intermediate_steps_list: List[Tuple[Dict, Any]] = []; processed_tool_call_ids = set()
    for i, msg_item in enumerate(final_messages):
        if isinstance(msg_item, AIMessage) and msg_item.tool_calls:
            for tool_call in msg_item.tool_calls:
                 tool_call_id = tool_call.get('id')
                 if not tool_call_id or tool_call_id in processed_tool_call_ids: continue
                 tool_message_found = False
                 for next_msg_idx in range(i + 1, len(final_messages)):
                    next_msg = final_messages[next_msg_idx]
                    if isinstance(next_msg, ToolMessage) and next_msg.tool_call_id == tool_call_id:
                        tool_result_content = next_msg.content; tool_message_found = True
                        tool_name = tool_call.get('name', 'UnknownTool')
                        tool_input_args = {}
                        try: tool_input_args = json.loads(tool_call.get('args', '{}')) if isinstance(tool_call.get('args'), str) else tool_call.get('args', {})
                        except: logger.warning(f"Could not parse tool args for {tool_name}: {tool_call.get('args')}")

                        display_result = tool_result_content
                        try:
                            parsed_res = json.loads(tool_result_content)
                            if isinstance(parsed_res, dict): display_result = parsed_res.get("summary", parsed_res.get("answer", parsed_res.get("snippet", tool_result_content)))
                            elif isinstance(parsed_res, list) and len(parsed_res) > 0 and isinstance(parsed_res[0], dict): display_result = f"Retrieved {len(parsed_res)} items. Example: {parsed_res[0].get('title', 'N/A')}"
                        except: pass

                        action_dict = { "tool": tool_name, "tool_input": tool_input_args, "log": f"Tool Used: {tool_name}" }
                        intermediate_steps_list.append((action_dict, display_result))
                        processed_tool_call_ids.add(tool_call_id)

                        # Check for project generation trigger
                        if action_dict["tool"] == "generate_software_project":
                            if not PROJECT_GENERATOR_AVAILABLE:
                                logger.warning("Project generation tool called but feature is unavailable.")
                                final_answer_content = "Sorry, project generation is currently unavailable."
                                project_gen_triggered = False
                            else:
                                project_gen_triggered = True
                                project_request_arg = tool_input_args
                        break
                 if not tool_message_found:
                     logger.warning(f"No ToolMessage found for AIMessage tool call ID {tool_call_id}")

    serialized_steps = serialize_intermediate_steps(intermediate_steps_list) if intermediate_steps_list else []

    # --- Handle project generation trigger ---
    # Note: Ideally, the *API layer* (`api/chat.py`) should detect this intent
    # and call the `/jobs/project_generation/start` endpoint instead of this service handling it directly.
    # Keeping it here for now based on previous structure, but consider moving trigger logic to API.
    if project_gen_triggered and project_request_arg is not None:
        logger.warning("Non-streaming handler detected project gen request. Ideally, this should trigger job via API, not BackgroundTasks.")
        # --- Placeholder: Manually trigger job start (Needs refactoring) ---
        # This section should ideally call the jobs API endpoint or service.
        # For now, it mimics the old direct triggering with BackgroundTasks.
        try:
            from app.services.jobs_service import start_job # Temporary direct import (avoid this)
            job_id = await start_job("project_generation", {"request": project_request_arg}) # Simulate payload
            answer = f"Started project generation (Job ID: {job_id}). Check status later."
        except Exception as e:
            logger.error(f"Failed to trigger project generation job from non-streaming handler: {e}", exc_info=True)
            answer = "Error initiating project generation job."
        # ---------------------------------------------------------------
    else:
        # Use the final answer content determined earlier
        answer = final_answer_content.strip() or "Sorry, I couldn't generate a response."

    # Ensure source_documents is always returned
    source_documents_list = []

    return schemas.AskResponse(
        answer=answer,
        source_documents=source_documents_list,
        intermediate_steps=serialized_steps
    )