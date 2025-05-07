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
from langgraph.graph.state import END # Import END

# App imports
from app import schemas, config
from app.utils import get_logger # Removed unused serialize_intermediate_steps, serialize_documents
from app.core.ai.agents.executor import get_langgraph_app, AgentState 
from app.core.jobs.store import get_job_store_instance
logger = get_logger(__name__)

# --- Project Generator Import ---
try:
    from app.core.project_generator.workflow import execute_project_generation_workflow
    PROJECT_GENERATOR_AVAILABLE = True
except ImportError:
    logger.warning("Project Generator workflow not found. 'generate_software_project' tool will be disabled.")
    PROJECT_GENERATOR_AVAILABLE = False
    async def execute_project_generation_workflow(request: str) -> AsyncGenerator[Dict[str, Any], None]:
         yield { "type": "final_status", "status": "Failed", "message": "Error: Project Generator workflow component is not available.", "project_name": "Unavailable", "output_dir": None, "tests_passed": None, "errors": ["Project Generator workflow component is not available."], "total_time": 0 }

class AgentNotReadyError(Exception):
    pass

async def run_project_gen_in_background(job_id: str, project_request: str):
    # ... (Identical)
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
        async for update in execute_project_generation_workflow(project_request):
            if update.get("type") == "status": logger.info(f"BG Job [{job_id}] Workflow Status [{update.get('step')}]: {update.get('message')}")
            if update.get("type") == "final_status": final_result = update; break
        if final_result:
            final_status_str = final_result.get("status", "Unknown").lower()
            result_message = final_result.get("message", "No final message.")
            errors_from_workflow = final_result.get("errors", [])
            if "success" in final_status_str or ("completed" in final_status_str and not errors_from_workflow):
                status = "completed"; output_path = final_result.get("output_dir")
            else:
                 status = "failed"; error_details = result_message
                 if errors_from_workflow: error_details += f" | Workflow Errors: {'; '.join(errors_from_workflow)}"
        else:
             status = "failed"; error_details = "Project generation workflow finished without providing a final status update."
    except Exception as e:
        status = "failed"; error_details = f"An unexpected error: {str(e)}"
    end_time = time.time(); duration = end_time - start_time
    final_update = {"status": status, "ended_at": end_time, "duration_seconds": round(duration, 2), "result_message": result_message if status == "completed" else None, "error_message": error_details if status == "failed" else None, "output_path": output_path}
    await job_store.update_job(job_id, final_update)
    logger.info(f"BG Job [{job_id}]: Final status '{status}' updated in Redis.")


async def handle_chat_request(request: schemas.AskRequest, background_tasks: BackgroundTasks) -> schemas.AskResponse:
    # ... (Identical, but ensure serialize_intermediate_steps is imported or handled if used)
    from app.utils import serialize_intermediate_steps # Add back if used
    base_question = request.question; input_prefix = ""
    has_filenames = bool(request.filenames and len(request.filenames) > 0); has_tag = bool(request.tag_filter)
    if has_filenames and has_tag: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
    elif has_filenames: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
    elif has_tag: input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
    user_input_content = f"{input_prefix}{base_question}"
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
        final_state = await langgraph_app.ainvoke(graph_input, config=run_config_obj)
    except RuntimeError as rte: raise AgentNotReadyError(f"LangGraph App execution failed: {rte}") from rte
    except Exception as e: raise RuntimeError(f"An unexpected error: {e}") from e
    if not final_state or not final_state.get("messages"):
        return schemas.AskResponse(answer="Sorry, I couldn't process your request.", intermediate_steps=[])
    final_messages = final_state["messages"]
    final_answer_msg = final_messages[-1] if final_messages else None
    final_answer_content = "Sorry, the interaction ended unexpectedly."
    if isinstance(final_answer_msg, AIMessage): final_answer_content = final_answer_msg.content
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
                        tool_result = next_msg.content; tool_message_found = True
                        action_dict = { "tool": tool_call.get('name', 'UnknownTool'), "tool_input": tool_call.get('args', {}), "log": f"Tool Used: {tool_call.get('name')}" }
                        intermediate_steps_list.append((action_dict, tool_result))
                        processed_tool_call_ids.add(tool_call_id)
                        if action_dict["tool"] == "generate_software_project":
                            if not PROJECT_GENERATOR_AVAILABLE: final_answer_content = "Sorry, project generation unavailable."; project_gen_triggered = False
                            else: project_gen_triggered = True; project_request_arg = action_dict["tool_input"]
                        break
                 if not tool_message_found: logger.warning(f"No ToolMessage for call ID {tool_call_id}")
    serialized_steps = serialize_intermediate_steps(intermediate_steps_list) 
    if project_gen_triggered and project_request_arg is not None:
        request_str = json.dumps(project_request_arg) if isinstance(project_request_arg, dict) else str(project_request_arg)
        job_id = str(uuid.uuid4())
        try:
            job_store = get_job_store_instance()
            initial_job_data = { "submitted_at": time.time(), "request": request_str, "status": "pending" }
            await job_store.initialize_job(job_id, initial_job_data)
            background_tasks.add_task(run_project_gen_in_background, job_id, request_str)
            answer = f"Started project generation (Job ID: {job_id}). Check status later."
        except Exception as store_err:
             answer = "Error initiating project generation job."
    else:
        answer = final_answer_content.strip() or "Sorry, I couldn't generate a response."
    return schemas.AskResponse(answer=answer, source_documents=[], intermediate_steps=serialized_steps)


# --- Streaming Handler (REVISED V12.2 - Simplified op loop, focus on get_state after /messages op) ---
async def handle_chat_request_stream(
    request: schemas.AskRequest,
    background_tasks: BackgroundTasks
) -> AsyncGenerator[Dict[str, str], None]:
    logger.info(f"STREAMING V12.2 (Diag): Starting graph stream for request: {request.question[:50]}...")
    
    # --- Message Preparation ---
    base_question = request.question; input_prefix = ""
    has_filenames = bool(request.filenames and len(request.filenames) > 0); has_tag = bool(request.tag_filter)
    if has_filenames and has_tag: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
    elif has_filenames: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
    elif has_tag: input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
    user_input_content = f"{input_prefix}{base_question}"
    initial_messages_for_graph: List[BaseMessage] = [] # For graph input
    if request.chat_history:
        for msg_data in request.chat_history:
             sender = msg_data.get('sender'); text = msg_data.get('text', '')
             if sender == 'user': initial_messages_for_graph.append(HumanMessage(content=text))
             elif sender == 'ai': initial_messages_for_graph.append(AIMessage(content=text))
    initial_messages_for_graph.append(HumanMessage(content=user_input_content))
    graph_input: AgentState = {"messages": initial_messages_for_graph}

    project_gen_triggered = False
    project_request_arg: Optional[Union[str, Dict]] = None
    
    current_debugger_node_id: str = "agent" 
    last_yielded_node_start_id: Optional[str] = None
    active_tool_call_info: Optional[Dict[str, Any]] = None 
    agent_is_processing_tool_output = False 
    processed_driving_message_ids = set() # To avoid re-processing the same logical message

    logger.info(f"[V12.2_INIT_STATE] current_debugger_node_id='{current_debugger_node_id}', agent_is_processing_tool_output={agent_is_processing_tool_output}")

    def _prepare_event(event_data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        nonlocal last_yielded_node_start_id
        etype = event_data.get("type")
        node_id = event_data.get("nodeId")
        if etype == "node_start":
            if node_id == last_yielded_node_start_id and node_id is not None: return None
            last_yielded_node_start_id = node_id
        elif etype == "node_end" and node_id == last_yielded_node_start_id and node_id is not None:
            last_yielded_node_start_id = None
        return {"event": "log_data", "data": json.dumps(event_data, default=str)}

    try:
        langgraph_app = get_langgraph_app() # This should now have the checkpointer
        if not langgraph_app: raise AgentNotReadyError("LangGraph App not ready.")

        run_config_obj: RunnableConfig = {
            "recursion_limit": 25, 
            "configurable": {"thread_id": str(uuid.uuid4())} # Essential for checkpointer & get_state
        }
        logger.info(f"Invoking LangGraph App astream_log V12.2 with config: {run_config_obj}")

        event = _prepare_event({"type": "node_start", "nodeId": current_debugger_node_id})
        if event: yield event

        # Keep track of the number of messages we've seen in the state to detect new ones
        last_seen_message_count = len(initial_messages_for_graph)

        chunk_idx = 0 
        async for chunk in langgraph_app.astream_log(graph_input, config=run_config_obj):
            # logger.debug(f"[V12.2_CHUNK] START CHUNK {chunk_idx}")
            
            # 1. Process token streams first from any op in this chunk
            for op_idx_token, op_token in enumerate(chunk.ops):
                path_token: str = op_token.get("path", "")
                value_token = op_token.get("value")
                if path_token.endswith(("/streamed_output_str/-", "/streamed_output/-")) and current_debugger_node_id == "agent":
                    token_content = None
                    if path_token.endswith("/streamed_output_str/-") and isinstance(value_token, str) and value_token:
                        token_content = value_token
                    elif path_token.endswith("/streamed_output/-") and isinstance(value_token, AIMessageChunk) and value_token.content:
                        token_content = value_token.content
                    if token_content:
                        event = _prepare_event({"type": "token", "token": token_content, "nodeId": "agent"})
                        if event: yield event
            
            # 2. After processing all ops in a chunk, check if the graph's message state has grown.
            # This is a more robust way to detect that a new AIMessage or ToolMessage has been fully added.
            try:
                # Essential: Use the *same* run_config_obj for get_state
                current_graph_state = langgraph_app.get_state(run_config_obj) 
                all_current_messages_from_state = current_graph_state.values.get('messages', [])
                
                # Always yield state_update for the message history panel
                if all_current_messages_from_state:
                    serializable_messages_for_history = []
                    for msg_val_hist in all_current_messages_from_state:
                        msg_dict_data_hist = {"type": getattr(msg_val_hist, 'type', msg_val_hist.__class__.__name__.lower().replace("message","")), "content": getattr(msg_val_hist,'content', None), **({"tool_calls": getattr(msg_val_hist,'tool_calls', getattr(msg_val_hist, 'tool_call_chunks', None))} if isinstance(msg_val_hist, (AIMessage, AIMessageChunk)) else {}), **({"tool_call_id": getattr(msg_val_hist,'tool_call_id', None)} if isinstance(msg_val_hist, ToolMessage) else {})}
                        serializable_messages_for_history.append({k: v_ for k, v_ in msg_dict_data_hist.items() if v_ is not None})
                    event = _prepare_event({"type": "state_update", "state": {"messages": serializable_messages_for_history}})
                    if event: yield event

                if len(all_current_messages_from_state) > last_seen_message_count:
                    new_message_from_state: BaseMessage = all_current_messages_from_state[-1]
                    last_seen_message_count = len(all_current_messages_from_state)
                    
                    msg_id = getattr(new_message_from_state, 'id', None)
                    if msg_id and msg_id in processed_driving_message_ids:
                        # logger.debug(f"[V12.2_MSG_ALREADY_PROCESSED] ID {msg_id}. Skipping logic.")
                        continue 

                    logger.critical(f"[V12.2_NEW_STATE_MSG] === New Message Detected in State ===")
                    logger.critical(f"[V12.2_NEW_STATE_MSG] Class: {new_message_from_state.__class__.__name__}, ID: {msg_id}")
                    logger.critical(f"[V12.2_NEW_STATE_MSG] Current Debugger Node: {current_debugger_node_id}, Agent Processing Tool Output Flag: {agent_is_processing_tool_output}")
                    
                    message_tool_calls = getattr(new_message_from_state, 'tool_calls', getattr(new_message_from_state, 'tool_call_chunks', None))
                    logger.critical(f"[V12.2_NEW_STATE_MSG] Extracted tool_calls: {message_tool_calls}")

                    # --- A. Agent decides to call a tool ---
                    if current_debugger_node_id == "agent" and not agent_is_processing_tool_output and \
                       isinstance(new_message_from_state, (AIMessage, AIMessageChunk)) and message_tool_calls and len(message_tool_calls) > 0:
                        logger.critical(f"[V12.2_LOGIC_A_HIT] Agent decides tool call.")
                        if msg_id: processed_driving_message_ids.add(msg_id)
                        # ... (event yielding and state transition for A - same as V11.6)
                        event = _prepare_event({"type": "node_output", "nodeId": "agent", "output": new_message_from_state.dict()}); 
                        if event: yield event
                        event = _prepare_event({"type": "node_end", "nodeId": "agent"}); 
                        if event: yield event
                        tc_data = message_tool_calls[0] 
                        args_data = getattr(tc_data, 'args', tc_data.get('args') if isinstance(tc_data, dict) else "{}")
                        try: parsed_args = json.loads(args_data) if isinstance(args_data, str) else args_data
                        except: parsed_args = args_data
                        active_tool_call_info = {"id": getattr(tc_data, 'id', tc_data.get('id') if isinstance(tc_data, dict) else None),"name": getattr(tc_data, 'name', tc_data.get('name') if isinstance(tc_data, dict) else None),"args": parsed_args}
                        logger.critical(f"[V12.2_LOGIC_A] Tool call details: {active_tool_call_info}")
                        event = _prepare_event({"type": "tool_call", "toolCall": active_tool_call_info}); 
                        if event: yield event
                        if active_tool_call_info.get('name') == "generate_software_project": project_gen_triggered = True; project_request_arg = active_tool_call_info.get('args')
                        current_debugger_node_id = "action" 
                        logger.critical(f"[V12.2_TRANSITION_A_POST] New cur_node='{current_debugger_node_id}', tool_proc='{agent_is_processing_tool_output}'")
                        event = _prepare_event({"type": "node_start", "nodeId": current_debugger_node_id}); 
                        if event: yield event

                    # --- B. Tool provides result ---
                    elif current_debugger_node_id == "action" and isinstance(new_message_from_state, ToolMessage):
                        logger.critical(f"[V12.2_LOGIC_B_HIT] Tool provides result.")
                        if msg_id: processed_driving_message_ids.add(msg_id)
                        # ... (event yielding and state transition for B - same as V11.6)
                        tool_msg: ToolMessage = new_message_from_state
                        tool_result_data = {"id": tool_msg.tool_call_id, "result": tool_msg.content}
                        event = _prepare_event({"type": "tool_result", "toolResult": tool_result_data}); 
                        if event: yield event
                        event = _prepare_event({"type": "node_output", "nodeId": "action", "output": tool_msg.content}); 
                        if event: yield event
                        event = _prepare_event({"type": "node_end", "nodeId": "action"}); 
                        if event: yield event
                        active_tool_call_info = None 
                        current_debugger_node_id = "agent" 
                        agent_is_processing_tool_output = True 
                        logger.critical(f"[V12.2_TRANSITION_B_POST] New cur_node='{current_debugger_node_id}', tool_proc='{agent_is_processing_tool_output}'")
                        event = _prepare_event({"type": "node_start", "nodeId": current_debugger_node_id}); 
                        if event: yield event
                            
                    # --- C. Agent gives final answer ---
                    elif current_debugger_node_id == "agent" and \
                         isinstance(new_message_from_state, (AIMessage, AIMessageChunk)) and \
                         not (message_tool_calls and len(message_tool_calls) > 0):
                        logger.critical(f"[V12.2_LOGIC_C_HIT] Agent final answer. tool_proc_flag: {agent_is_processing_tool_output}")
                        if msg_id: processed_driving_message_ids.add(msg_id)
                        # ... (event yielding and state transition for C - same as V11.6)
                        event = _prepare_event({"type": "node_output", "nodeId": "agent", "output": new_message_from_state.dict()}); 
                        if event: yield event 
                        event = _prepare_event({"type": "node_end", "nodeId": "agent"}); 
                        if event: yield event
                        current_debugger_node_id = END 
                        agent_is_processing_tool_output = False 
                        logger.critical(f"[V12.2_TRANSITION_C_POST] New cur_node='{current_debugger_node_id}', tool_proc='{agent_is_processing_tool_output}'")
                        event = _prepare_event({"type": "node_start", "nodeId": current_debugger_node_id}); 
                        if event: yield event
                        event = _prepare_event({"type": "node_end", "nodeId": current_debugger_node_id}); 
                        if event: yield event
                            
                    else:
                        logger.warning(f"[V12.2_MSG_UNHANDLED_LOGIC] Latest message from state ({new_message_from_state.__class__.__name__}) did not trigger A,B,C logic.")

            except Exception as e:
                    logger.error(f"Error processing latest message from state (V12.2): {e}", exc_info=True)
            
            # logger.debug(f"[V12.2_CHUNK_END] END CHUNK {chunk_idx}. Debugger state: node='{current_debugger_node_id}', tool_proc='{agent_is_processing_tool_output}'")
            chunk_idx +=1

        logger.info(f"[STREAMING_V12.2_DBG] LangGraph stream log loop FINISHED. Final debugger node: '{current_debugger_node_id}', tool_proc: {agent_is_processing_tool_output}")
        
        # --- Post-loop cleanup (identical) ---
        if current_debugger_node_id and current_debugger_node_id != END:
            logger.info(f"[STREAMING_V12.2_DBG] Post-loop cleanup. Current node: {current_debugger_node_id}. Transitioning to END.")
            event = _prepare_event({"type": "node_end", "nodeId": current_debugger_node_id})
            if event: yield event
            current_debugger_node_id = END 
            if last_yielded_node_start_id != END : 
                event = _prepare_event({"type": "node_start", "nodeId": current_debugger_node_id})
                if event: yield event
            event = _prepare_event({"type": "node_end", "nodeId": current_debugger_node_id})
            if event: yield event
        elif not current_debugger_node_id and current_debugger_node_id != END : 
            logger.warning("[STREAMING_V12.2_DBG] Post-loop: current_debugger_node_id is None and not END. Emitting END sequence.")
            event = _prepare_event({"type": "node_start", "nodeId": END})
            if event: yield event
            event = _prepare_event({"type": "node_end", "nodeId": END})
            if event: yield event

        # --- Final Message/Job Submission (identical) ---
        if project_gen_triggered and project_request_arg is not None:
            # ... (project gen logic)
            request_str = json.dumps(project_request_arg) if isinstance(project_request_arg, dict) else str(project_request_arg)
            job_id = str(uuid.uuid4())
            logger.info(f"STREAMING_V12.2: Initializing project generation Job [{job_id}].")
            try:
                job_store = get_job_store_instance()
                initial_job_data = { "submitted_at": time.time(), "request": request_str, "status": "pending" }
                await job_store.initialize_job(job_id, initial_job_data)
                background_tasks.add_task(run_project_gen_in_background, job_id, request_str)
                prepared_event = _prepare_event({"type": "final_message", "message": f"Okay, I've started generating the project (Job ID: {job_id}). You can check the status using the job ID."})
                if prepared_event: yield prepared_event
            except Exception as store_err:
                logger.error(f"STREAMING_V12.2: Failed to initialize Job [{job_id}] in Redis: {store_err}", exc_info=True)
                prepared_event = _prepare_event({"type": "error", "error": "Failed to initiate background job."})
                if prepared_event: yield prepared_event
        else: 
             prepared_event = _prepare_event({"type": "final_message", "message": "Processing complete."})
             if prepared_event: yield prepared_event

    except AgentNotReadyError as anre:
        logger.error(f"[STREAMING_V12.2] AgentNotReadyError: {anre}", exc_info=True)
        event = _prepare_event({"type": "error", "error": f"Agent not ready: {anre}"})
        if event: yield event
    except Exception as e:
        logger.error(f"[STREAMING_V12.2] Unexpected error: {e}", exc_info=True)
        event = _prepare_event({"type": "error", "error": f"An unexpected error occurred: {e}"})
        if event: yield event
    finally:
        logger.info("[STREAMING_V12.2] Yielding stream_end.")
        event = _prepare_event({"type": "stream_end"})
        if event: yield event

# --- Get Job Status ---
async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    try: job_store = get_job_store_instance()
    except Exception as store_err: logger.error(f"Failed to get Job Store instance for get_job_status: {store_err}", exc_info=True); return None
    return await job_store.get_job(job_id)