# # backend/app/services/chat_service.py

# import json
# import logging
# import uuid
# import asyncio
# import time
# from typing import Dict, Any, List, AsyncGenerator, Tuple, Union, Optional

# from fastapi import BackgroundTasks

# # Langchain imports
# from langchain_core.messages import (
#     AIMessageChunk, HumanMessage, AIMessage, BaseMessage, ToolMessage, SystemMessage
# )
# from langchain_core.runnables import RunnableConfig
# from langgraph.graph.state import END # Import END

# # App imports
# from app import schemas, config
# from app.utils import get_logger, serialize_intermediate_steps # Ensure serialize_intermediate_steps is available if used
# from app.core.ai.agents.executor import get_langgraph_app, AgentState
# from app.core.jobs.store import get_job_store_instance
# logger = get_logger(__name__)

# # --- Project Generator Import ---
# try:
#     from app.core.project_generator.workflow import execute_project_generation_workflow
#     PROJECT_GENERATOR_AVAILABLE = True
# except ImportError:
#     logger.warning("Project Generator workflow not found. 'generate_software_project' tool will be disabled.")
#     PROJECT_GENERATOR_AVAILABLE = False
#     async def execute_project_generation_workflow(request: str) -> AsyncGenerator[Dict[str, Any], None]:
#          # Dummy implementation if not available
#          yield { "type": "final_status", "status": "Failed", "message": "Error: Project Generator workflow component is not available.", "project_name": "Unavailable", "output_dir": None, "tests_passed": None, "errors": ["Project Generator workflow component is not available."], "total_time": 0 }
#          await asyncio.sleep(0) # To make it a valid async generator

# class AgentNotReadyError(Exception):
#     pass

# async def run_project_gen_in_background(job_id: str, project_request: str):
#     """Runs the project generation workflow in the background and updates the job store."""
#     try:
#         job_store = get_job_store_instance()
#     except Exception as store_err:
#         logger.error(f"BG Job [{job_id}]: Failed to get Job Store instance: {store_err}", exc_info=True)
#         return

#     start_time = time.time()
#     logger.info(f"BG Job [{job_id}]: Starting generation for: '{project_request[:100]}...'")
#     await job_store.update_job(job_id, {"status": "running", "started_at": start_time})

#     status, result_message, output_path, error_details = "running", None, None, None
#     try:
#         final_result = None
#         async for update in execute_project_generation_workflow(project_request):
#             # Log progress updates from the workflow
#             if update.get("type") == "status":
#                  logger.info(f"BG Job [{job_id}] Workflow Status [{update.get('step')}]: {update.get('message')}")
#             # Check for the final result signal
#             if update.get("type") == "final_status":
#                  final_result = update
#                  break # Stop processing once final status is received

#         if final_result:
#             final_status_str = final_result.get("status", "Unknown").lower()
#             result_message = final_result.get("message", "No final message provided.")
#             errors_from_workflow = final_result.get("errors", [])

#             # Determine final job status based on workflow result
#             if "success" in final_status_str or ("completed" in final_status_str and not errors_from_workflow):
#                 status = "completed"
#                 output_path = final_result.get("output_dir")
#             else:
#                  status = "failed"
#                  error_details = result_message
#                  if errors_from_workflow:
#                       error_details += f" | Workflow Errors: {'; '.join(errors_from_workflow)}"
#         else:
#              # Handle case where workflow finishes without a final_status update
#              status = "failed"
#              error_details = "Project generation workflow finished unexpectedly without providing a final status."

#     except Exception as e:
#         status = "failed"
#         error_details = f"An unexpected error occurred during project generation: {str(e)}"
#         logger.error(f"BG Job [{job_id}]: Unexpected error during workflow execution.", exc_info=True)

#     # Update job store with the final status and details
#     end_time = time.time()
#     duration = end_time - start_time
#     final_update = {
#         "status": status,
#         "ended_at": end_time,
#         "duration_seconds": round(duration, 2),
#         "result_message": result_message if status == "completed" else None,
#         "error_message": error_details if status == "failed" else None,
#         "output_path": output_path
#     }
#     await job_store.update_job(job_id, final_update)
#     logger.info(f"BG Job [{job_id}]: Final status '{status}' updated in Redis.")


# async def handle_chat_request(request: schemas.AskRequest, background_tasks: BackgroundTasks) -> schemas.AskResponse:
#     """Handles non-streaming chat requests."""
#     logger.info(f"Handling non-streaming request: {request.question[:50]}...")
#     base_question = request.question; input_prefix = ""
#     has_filenames = bool(request.filenames and len(request.filenames) > 0); has_tag = bool(request.tag_filter)
#     # Construct input prefix based on filters
#     if has_filenames and has_tag: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
#     elif has_filenames: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
#     elif has_tag: input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
#     user_input_content = f"{input_prefix}{base_question}"

#     # Prepare messages for LangGraph
#     messages: List[BaseMessage] = []
#     if request.chat_history:
#         for msg_data in request.chat_history:
#             sender = msg_data.get('sender'); text = msg_data.get('text', '')
#             if sender == 'user': messages.append(HumanMessage(content=text))
#             elif sender == 'ai': messages.append(AIMessage(content=text))
#     messages.append(HumanMessage(content=user_input_content))
#     graph_input: AgentState = {"messages": messages}

#     final_state: Optional[AgentState] = None
#     try:
#         langgraph_app = get_langgraph_app()
#         run_config_obj: RunnableConfig = {"recursion_limit": 25}
#         # Consider adding thread_id here if needed for state consistency in non-streaming
#         run_config_obj["configurable"] = {"thread_id": str(uuid.uuid4())} # Added thread_id example
#         final_state = await langgraph_app.ainvoke(graph_input, config=run_config_obj)
#     except RuntimeError as rte:
#         logger.error(f"LangGraph non-streaming execution failed: {rte}", exc_info=True)
#         raise AgentNotReadyError(f"Agent execution failed: {rte}") from rte
#     except Exception as e:
#         logger.error(f"Unexpected error during non-streaming agent invocation: {e}", exc_info=True)
#         raise RuntimeError(f"An unexpected error occurred: {e}") from e

#     if not final_state or not final_state.get("messages"):
#         logger.warning("Non-streaming agent invocation resulted in empty final state or messages.")
#         return schemas.AskResponse(answer="Sorry, I couldn't process your request.", intermediate_steps=[])

#     final_messages = final_state["messages"]
#     final_answer_msg = final_messages[-1] if final_messages else None
#     final_answer_content = "Sorry, the interaction ended unexpectedly."

#     # Extract final answer text
#     if isinstance(final_answer_msg, AIMessage):
#         final_answer_content = final_answer_msg.content
#         # If the last message had tool calls, parse the result for the answer
#         # This depends on how your agent handles tool output vs final response
#         if final_answer_msg.tool_calls:
#              logger.info("Final AI message in non-streaming has tool calls. Parsing last ToolMessage for answer.")
#              # Find the corresponding ToolMessage for the *last* tool call in the final AIMessage
#              last_tool_call_id = final_answer_msg.tool_calls[-1].get('id') if final_answer_msg.tool_calls else None
#              found_tool_answer = False
#              if last_tool_call_id:
#                  for msg in reversed(final_messages[:-1]): # Look in messages before the last one
#                       if isinstance(msg, ToolMessage) and msg.tool_call_id == last_tool_call_id:
#                            tool_name_called = ""
#                            # Find original tool name
#                            for prev_msg in final_messages:
#                                if isinstance(prev_msg, AIMessage) and prev_msg.tool_calls:
#                                    for tc in prev_msg.tool_calls:
#                                        if tc.get('id') == last_tool_call_id:
#                                            tool_name_called = tc.get('name', "")
#                                            break
#                                    if tool_name_called: break

#                            logger.debug(f"Found ToolMessage for last tool call {last_tool_call_id} (Tool: {tool_name_called}). Parsing content.")
#                            try:
#                                parsed_res = json.loads(msg.content)
#                                if isinstance(parsed_res, dict):
#                                     # Prefer 'answer' or 'summary' key based on known tool outputs
#                                     extracted_answer = parsed_res.get("answer", parsed_res.get("summary"))
#                                     if extracted_answer:
#                                          final_answer_content = extracted_answer # Overwrite if tool provides final answer
#                                          found_tool_answer = True
#                                          logger.info("Using parsed 'answer'/'summary' from tool result as final content.")
#                                     else:
#                                          logger.warning("Parsed tool JSON but no 'answer' or 'summary' key found.")
#                                          final_answer_content = msg.content # Fallback to raw content
#                                else:
#                                     final_answer_content = msg.content # Fallback if JSON is not a dict
#                            except (json.JSONDecodeError, TypeError):
#                                 logger.warning("Could not parse ToolMessage content as JSON, using raw content.")
#                                 final_answer_content = msg.content # Use raw content if not JSON
#                            break # Found the relevant ToolMessage
#              if not found_tool_answer:
#                  logger.warning("Final AIMessage had tool calls, but couldn't find/parse corresponding ToolMessage answer. Using AIMessage.content.")


#     # Process intermediate steps for potential display (if feature exists)
#     project_gen_triggered = False; project_request_arg = None
#     intermediate_steps_list: List[Tuple[Dict, Any]] = []; processed_tool_call_ids = set()
#     for i, msg_item in enumerate(final_messages):
#         if isinstance(msg_item, AIMessage) and msg_item.tool_calls:
#             for tool_call in msg_item.tool_calls:
#                  tool_call_id = tool_call.get('id')
#                  if not tool_call_id or tool_call_id in processed_tool_call_ids: continue
#                  tool_message_found = False
#                  for next_msg_idx in range(i + 1, len(final_messages)):
#                     next_msg = final_messages[next_msg_idx]
#                     if isinstance(next_msg, ToolMessage) and next_msg.tool_call_id == tool_call_id:
#                         tool_result_content = next_msg.content; tool_message_found = True
#                         tool_name = tool_call.get('name', 'UnknownTool')
#                         tool_input_args = tool_call.get('args', {})
#                         display_result = tool_result_content # Default to raw result
#                         # Try to extract meaningful part for intermediate steps display
#                         try:
#                             parsed_res = json.loads(tool_result_content)
#                             if isinstance(parsed_res, dict):
#                                 # Show summary/answer preferentially, fallback to snippet, else raw
#                                 display_result = parsed_res.get("summary", parsed_res.get("answer", parsed_res.get("snippet", tool_result_content)))
#                             elif isinstance(parsed_res, list) and len(parsed_res) > 0 and isinstance(parsed_res[0], dict):
#                                 # Handle list output like from search_web_raw
#                                 display_result = f"Retrieved {len(parsed_res)} items. Example: {parsed_res[0].get('title', 'N/A')}"
#                         except: pass # Keep raw result if not valid JSON or doesn't have expected keys
#                         action_dict = { "tool": tool_name, "tool_input": tool_input_args, "log": f"Tool Used: {tool_name}" }
#                         intermediate_steps_list.append((action_dict, display_result))
#                         processed_tool_call_ids.add(tool_call_id)
#                         if action_dict["tool"] == "generate_software_project":
#                             if not PROJECT_GENERATOR_AVAILABLE: final_answer_content = "Sorry, project generation unavailable."; project_gen_triggered = False
#                             else: project_gen_triggered = True; project_request_arg = action_dict["tool_input"]
#                         break
#                  if not tool_message_found: logger.warning(f"No ToolMessage found for AIMessage tool call ID {tool_call_id}")

#     # Serialize intermediate steps if needed
#     serialized_steps = serialize_intermediate_steps(intermediate_steps_list) if intermediate_steps_list else []

#     # Handle project generation trigger
#     if project_gen_triggered and project_request_arg is not None:
#         request_str = json.dumps(project_request_arg) if isinstance(project_request_arg, dict) else str(project_request_arg)
#         job_id = str(uuid.uuid4())
#         try:
#             job_store = get_job_store_instance()
#             initial_job_data = { "submitted_at": time.time(), "request": request_str, "status": "pending" }
#             await job_store.initialize_job(job_id, initial_job_data)
#             background_tasks.add_task(run_project_gen_in_background, job_id, request_str)
#             answer = f"Started project generation (Job ID: {job_id}). Check status later."
#         except Exception as store_err:
#              logger.error(f"Failed to initialize background job {job_id}: {store_err}", exc_info=True)
#              answer = "Error initiating project generation job."
#     else:
#         answer = final_answer_content.strip() or "Sorry, I couldn't generate a response."

#     # Assuming source_documents are primarily handled via streaming UI events
#     return schemas.AskResponse(answer=answer, source_documents=[], intermediate_steps=serialized_steps)


# # --- Event Formatting Helpers ---
# async def _yield_event(event_type_for_ui: str, data_payload_for_ui: Dict[str, Any]) -> Dict[str, str]:
#     """Formats custom UI events for SSE, compatible with sse-starlette."""
#     actual_payload_for_frontend = {
#         "type": event_type_for_ui,
#         "data": json.dumps(data_payload_for_ui, default=str) # Ensure payload data is JSON stringified
#     }
#     sse_dict_to_yield = {
#         "event": event_type_for_ui, # This sets the SSE `event: <name>` field
#         "data": json.dumps(actual_payload_for_frontend, default=str) # This sets the SSE `data: <json_string>` field
#     }
#     logger.debug(f"Yielding SSE Event: Name='{sse_dict_to_yield['event']}', SSE Data Field='{sse_dict_to_yield['data'][:200]}...'")
#     return sse_dict_to_yield

# def _prepare_debugger_event(event_data: Dict[str, Any], last_yielded_node_start_id: Optional[str]) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
#     """ Prepares debugger event and updates the last yielded node ID. """
#     new_last_yielded_id = last_yielded_node_start_id
#     event_to_yield = None
#     etype = event_data.get("type")
#     node_id = event_data.get("nodeId")
#     # Logic to prevent duplicate node_start and handle node_end reset
#     if etype == "node_start":
#         if node_id != last_yielded_node_start_id or node_id is None:
#             new_last_yielded_id = node_id
#             event_to_yield = {"event": "log_data", "data": json.dumps(event_data, default=str)}
#     elif etype == "node_end":
#         if node_id == last_yielded_node_start_id and node_id is not None:
#             new_last_yielded_id = None # Reset on node end
#         event_to_yield = {"event": "log_data", "data": json.dumps(event_data, default=str)}
#     else: # For other types like state_update, tool_call, etc., yield directly
#          event_to_yield = {"event": "log_data", "data": json.dumps(event_data, default=str)}
#     return event_to_yield, new_last_yielded_id
# # --- End Event Formatting Helpers ---


# async def handle_chat_request_stream(
#     request: schemas.AskRequest,
#     background_tasks: BackgroundTasks
# ) -> AsyncGenerator[Dict[str, Any], None]:
#     """Handles streaming chat requests with detailed UI events including RAG context."""

#     # --- Message Preparation ---
#     base_question = request.question; input_prefix = ""
#     has_filenames = bool(request.filenames and len(request.filenames) > 0); has_tag = bool(request.tag_filter)
#     if has_filenames and has_tag: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
#     elif has_filenames: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
#     elif has_tag: input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
#     user_input_content = f"{input_prefix}{base_question}"
#     initial_messages_for_graph: List[BaseMessage] = []
#     if request.chat_history:
#         for msg_data in request.chat_history:
#              sender = msg_data.get('sender'); text = msg_data.get('text', '')
#              if sender == 'user': initial_messages_for_graph.append(HumanMessage(content=text))
#              elif sender == 'ai': initial_messages_for_graph.append(AIMessage(content=text))
#     initial_messages_for_graph.append(HumanMessage(content=user_input_content))
#     graph_input: AgentState = {"messages": initial_messages_for_graph}

#     project_gen_triggered = False
#     project_request_arg: Optional[Union[str, Dict]] = None

#     # State Tracking
#     current_debugger_node_id: str = "agent"
#     last_yielded_node_start_id: Optional[str] = None
#     active_tool_call_info: Optional[Dict[str, Any]] = None
#     active_tool_name_for_ui: Optional[str] = None
#     agent_is_processing_tool_output = False
#     processed_driving_message_ids = set()

#     # --- Start Streaming ---
#     yield await _yield_event("thinking_started", {"message": "LearnMate is thinking..."})
#     logger.info(f"STREAMING V12.8 (Refactor): Starting graph stream for: {request.question[:50]}...") # Version Bump
#     logger.info(f"[V12.8_INIT_STATE] current_debugger_node_id='{current_debugger_node_id}', agent_is_processing_tool_output={agent_is_processing_tool_output}")

#     try:
#         langgraph_app = get_langgraph_app()
#         if not langgraph_app: raise AgentNotReadyError("LangGraph App not ready.")
#         run_config_obj: RunnableConfig = { "recursion_limit": 25, "configurable": {"thread_id": str(uuid.uuid4())} }
#         logger.info(f"Invoking LangGraph App astream_log V12.8 with config: {run_config_obj}")

#         # Yield initial debugger node start
#         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_start", "nodeId": current_debugger_node_id}, last_yielded_node_start_id)
#         if debugger_event: yield debugger_event

#         last_seen_message_count = len(initial_messages_for_graph)

#         # --- Main Streaming Loop ---
#         async for chunk in langgraph_app.astream_log(graph_input, config=run_config_obj):
#             # 1. Process token streams
#             for op_token in chunk.ops:
#                 path_token: str = op_token.get("path", "")
#                 value_token = op_token.get("value")
#                 if path_token.endswith(("/streamed_output_str/-", "/streamed_output/-")) and current_debugger_node_id == "agent":
#                     token_content = None
#                     if path_token.endswith("/streamed_output_str/-") and isinstance(value_token, str) and value_token: token_content = value_token
#                     elif path_token.endswith("/streamed_output/-") and isinstance(value_token, AIMessageChunk) and value_token.content:
#                          if not getattr(value_token, 'tool_call_chunks', None): token_content = value_token.content
#                     if token_content: yield await _yield_event("ai_message_chunk", {"content_chunk": token_content})

#             # 2. Check for new messages in state to drive logic (A, B, C)
#             try:
#                 current_graph_state = langgraph_app.get_state(run_config_obj)
#                 all_current_messages_from_state = current_graph_state.values.get('messages', [])

#                 # Yield debugger state update
#                 if all_current_messages_from_state:
#                     serializable_messages_for_history = []
#                     for msg_val_hist in all_current_messages_from_state:
#                         msg_dict_data_hist = {"type": getattr(msg_val_hist, 'type', msg_val_hist.__class__.__name__.lower().replace("message","")), "content": getattr(msg_val_hist,'content', None), **({"tool_calls": getattr(msg_val_hist,'tool_calls', getattr(msg_val_hist, 'tool_call_chunks', None))} if isinstance(msg_val_hist, (AIMessage, AIMessageChunk)) else {}), **({"tool_call_id": getattr(msg_val_hist,'tool_call_id', None)} if isinstance(msg_val_hist, ToolMessage) else {})}
#                         serializable_messages_for_history.append({k: v_ for k, v_ in msg_dict_data_hist.items() if v_ is not None})
#                     debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "state_update", "state": {"messages": serializable_messages_for_history}}, last_yielded_node_start_id)
#                     if debugger_event: yield debugger_event

#                 # Check if a new message drives the main logic
#                 if len(all_current_messages_from_state) > last_seen_message_count:
#                     new_message_from_state: BaseMessage = all_current_messages_from_state[-1]
#                     last_seen_message_count = len(all_current_messages_from_state)
#                     msg_id = getattr(new_message_from_state, 'id', None)
#                     if msg_id and msg_id in processed_driving_message_ids: continue

#                     logger.critical(f"[V12.8_NEW_STATE_MSG] Class: {new_message_from_state.__class__.__name__}, ID: {msg_id}")
#                     message_tool_calls = getattr(new_message_from_state, 'tool_calls', getattr(new_message_from_state, 'tool_call_chunks', None))

#                     # --- A. Agent decides to call a tool ---
#                     if current_debugger_node_id == "agent" and not agent_is_processing_tool_output and \
#                        isinstance(new_message_from_state, (AIMessage, AIMessageChunk)) and message_tool_calls and len(message_tool_calls) > 0:
#                         logger.critical(f"[V12.8_LOGIC_A_HIT] Agent decides tool call.")
#                         if msg_id: processed_driving_message_ids.add(msg_id)
#                         tc_data = message_tool_calls[0]
#                         args_data = getattr(tc_data, 'args', tc_data.get('args') if isinstance(tc_data, dict) else "{}")
#                         try: parsed_args = json.loads(args_data) if isinstance(args_data, str) else args_data
#                         except: parsed_args = args_data
#                         active_tool_call_info = {"id": getattr(tc_data, 'id', tc_data.get('id') if isinstance(tc_data, dict) else None),"name": getattr(tc_data, 'name', tc_data.get('name') if isinstance(tc_data, dict) else None),"args": parsed_args}
#                         active_tool_name_for_ui = active_tool_call_info.get('name')

#                         # Emit Specific Status Updates based on Tool
#                         tool_call_ui_msg = f"Using tool: {active_tool_name_for_ui}..."
#                         # *** Use the REFACTORED tool name 'search_web_raw' ***
#                         if active_tool_name_for_ui == "search_web_raw":
#                             query_arg = parsed_args.get('query', 'your query') if isinstance(parsed_args, dict) else "your query"
#                             tool_call_ui_msg = f"[Search] Searching web for '{str(query_arg)[:50]}...'"
#                             # Yielding sources_found will happen in Logic B now
#                         elif active_tool_name_for_ui == "query_uploaded_documents":
#                             query_arg = parsed_args.get('query', 'your query') if isinstance(parsed_args, dict) else "your query"
#                             tool_call_ui_msg = f"[RAG] Searching documents for '{str(query_arg)[:50]}...'"
#                         elif active_tool_name_for_ui == "summarize_document_content":
#                             filename_arg = parsed_args.get('filename', 'unknown file') if isinstance(parsed_args, dict) else "unknown file"
#                             tool_call_ui_msg = f"[Summarize Doc] Preparing summary for '{str(filename_arg)[:50]}...'"
#                         elif active_tool_name_for_ui == "generate_software_project":
#                             tool_call_ui_msg = "[Project] Starting software project generation..."
#                             project_gen_triggered = True; project_request_arg = active_tool_call_info.get('args')

#                         yield await _yield_event("tool_call_initiated", {"tool_name": active_tool_name_for_ui, "tool_input": parsed_args, "message": tool_call_ui_msg})

#                         # Debugger Events & State Transition
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_output", "nodeId": "agent", "output": new_message_from_state.dict()}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_end", "nodeId": "agent"}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "tool_call", "toolCall": active_tool_call_info}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event
#                         current_debugger_node_id = "action"
#                         logger.critical(f"[V12.8_TRANSITION_A_POST] New cur_node='{current_debugger_node_id}', tool_proc='{agent_is_processing_tool_output}'")
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_start", "nodeId": current_debugger_node_id}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event

#                     # --- B. Tool provides result ---
#                     elif current_debugger_node_id == "action" and isinstance(new_message_from_state, ToolMessage):
#                         logger.critical(f"[V12.8_LOGIC_B_HIT] Tool provides result.")
#                         if msg_id: processed_driving_message_ids.add(msg_id)
#                         tool_msg: ToolMessage = new_message_from_state
#                         tool_result_data_for_dbg = {"id": tool_msg.tool_call_id, "result": tool_msg.content} # Raw content for debugger

#                         yield await _yield_event("status_update", {"message": f"[Processing] Received results from {active_tool_name_for_ui or 'tool'}."})

#                         # --- Process Tool Output for UI Events and Agent Context ---
#                         agent_context_content = tool_msg.content # Default

#                         # --- Handle RAG Tool Output ---
#                         if active_tool_name_for_ui == "query_uploaded_documents":
#                             try:
#                                 content_data = json.loads(tool_msg.content)
#                                 agent_context_content = content_data.get("answer", "Could not extract answer from RAG tool.") # Agent gets pre-synthesized answer
#                                 rag_sources = content_data.get("rag_sources", [])
#                                 if rag_sources and isinstance(rag_sources, list):
#                                     valid_rag_sources = []
#                                     for src in rag_sources:
#                                         if isinstance(src, dict) and "filename" in src and "snippet" in src:
#                                              valid_rag_sources.append({ "filename": src.get("filename"), "page": src.get("page", "N/A"), "snippet": src.get("snippet") })
#                                     if valid_rag_sources:
#                                          yield await _yield_event("rag_context_found", {"context": valid_rag_sources})
#                                          yield await _yield_event("status_update", {"message": f"[Analyzing] Found context in {len(valid_rag_sources)} document chunk(s)."})
#                                     else: yield await _yield_event("status_update", {"message": "[Analyzing] RAG tool ran but returned no valid sources."})
#                                 else: yield await _yield_event("status_update", {"message": "[Analyzing] RAG tool ran, processing result..."})
#                                 yield await _yield_event("status_update", {"message": "[Generating] Preparing response based on documents..."})
#                             except Exception as e:
#                                 logger.error(f"Error processing RAG tool '{active_tool_name_for_ui}' result: {e}", exc_info=True)
#                                 yield await _yield_event("status_update", {"message": "[Error] Could not process RAG results."})
#                                 yield await _yield_event("status_update", {"message": "[Generating] Preparing response..."})
#                                 agent_context_content = f"Error processing RAG result: {e}"

#                         # --- Handle Refactored Web Search Tool Output ---
#                         elif active_tool_name_for_ui == "search_web_raw": # <<< USE NEW TOOL NAME
#                             try:
#                                 sources_from_tool = json.loads(tool_msg.content)
#                                 if sources_from_tool and isinstance(sources_from_tool, list):
#                                     valid_sources_for_ui = []
#                                     combined_content_for_agent = []
#                                     for src in sources_from_tool:
#                                         if isinstance(src, dict) and "url" in src and "title" in src and "cleaned_content" in src:
#                                             valid_sources_for_ui.append({ "title": src.get("title", "Untitled"), "url": src.get("url"), "snippet": src.get("snippet", None) })
#                                             combined_content_for_agent.append(f"Source URL: {src.get('url')}\nSource Title: {src.get('title')}\nContent:\n{src.get('cleaned_content', '')}\n---")
#                                     if valid_sources_for_ui:
#                                         yield await _yield_event("sources_found", {"sources": valid_sources_for_ui}) # Yield sources for UI (title, url, snippet)
#                                         yield await _yield_event("status_update", {"message": f"[Processing] Retrieved content from {len(valid_sources_for_ui)} web source(s)."})
#                                         agent_context_content = "\n\n".join(combined_content_for_agent) # Agent gets COMBINED CLEANED CONTENT
#                                     else:
#                                         yield await _yield_event("status_update", {"message": "[Processing] Web search complete (no valid sources found)."})
#                                         agent_context_content = "Web search did not find relevant content."
#                                 else:
#                                      yield await _yield_event("status_update", {"message": "[Processing] Web search results received (no sources list)."})
#                                      agent_context_content = "Web search did not find relevant content."
#                                 yield await _yield_event("status_update", {"message": "[Generating] Preparing response based on web search..."})
#                             except json.JSONDecodeError:
#                                 logger.error(f"Failed to parse JSON from web tool '{active_tool_name_for_ui}': {tool_msg.content[:200]}")
#                                 yield await _yield_event("status_update", {"message": "[Error] Could not process web search results."})
#                                 yield await _yield_event("status_update", {"message": "[Generating] Preparing response..."})
#                                 agent_context_content = f"Error processing web search result: Malformed JSON"
#                             except Exception as e:
#                                 logger.error(f"Error processing web tool '{active_tool_name_for_ui}' result: {e}", exc_info=True)
#                                 yield await _yield_event("status_update", {"message": "[Error] Problem analyzing web search results."})
#                                 yield await _yield_event("status_update", {"message": "[Generating] Preparing response..."})
#                                 agent_context_content = f"Error processing web search result: {e}"

#                         # --- Handle other tools (pass raw content to agent) ---
#                         else:
#                              # Example: Summarize document tool returns string directly
#                              if active_tool_name_for_ui == "summarize_document_content":
#                                  agent_context_content = tool_msg.content # Agent gets the summary string
#                                  yield await _yield_event("status_update", {"message": "[Processing] Received document summary."})
#                              # Else, just pass raw content
#                              yield await _yield_event("status_update", {"message": f"[Generating] Preparing response after {active_tool_name_for_ui}..."})

#                         # Modify the ToolMessage content before LangGraph state update
#                         tool_msg.content = agent_context_content # Agent sees formatted context or processed result

#                         # Debugger Events and State Transition
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "tool_result", "toolResult": tool_result_data_for_dbg}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_output", "nodeId": "action", "output": tool_msg.content}, last_yielded_node_start_id); # Debugger sees processed content
#                         if debugger_event: yield debugger_event
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_end", "nodeId": "action"}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event
#                         active_tool_call_info = None; active_tool_name_for_ui = None
#                         current_debugger_node_id = "agent"; agent_is_processing_tool_output = True
#                         logger.critical(f"[V12.8_TRANSITION_B_POST] New cur_node='{current_debugger_node_id}', tool_proc='{agent_is_processing_tool_output}'")
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_start", "nodeId": current_debugger_node_id}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event

#                     # --- C. Agent gives final answer ---
#                     elif current_debugger_node_id == "agent" and \
#                          isinstance(new_message_from_state, (AIMessage, AIMessageChunk)) and \
#                          not (message_tool_calls and len(message_tool_calls) > 0):
#                         logger.critical(f"[V12.8_LOGIC_C_HIT] Agent provides AIMessage. tool_proc_flag: {agent_is_processing_tool_output}")
#                         if msg_id: processed_driving_message_ids.add(msg_id)
#                         yield await _yield_event("final_answer_turn_complete", {"message_id": msg_id})
#                         # Debugger Events & State Transition
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_output", "nodeId": "agent", "output": new_message_from_state.dict()}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_end", "nodeId": "agent"}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event
#                         current_debugger_node_id = END
#                         agent_is_processing_tool_output = False
#                         logger.critical(f"[V12.8_TRANSITION_C_POST] New cur_node='{current_debugger_node_id}', tool_proc='{agent_is_processing_tool_output}'")
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_start", "nodeId": current_debugger_node_id}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event
#                         debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_end", "nodeId": current_debugger_node_id}, last_yielded_node_start_id);
#                         if debugger_event: yield debugger_event

#                     else:
#                         logger.warning(f"[V12.8_MSG_UNHANDLED_LOGIC] Latest message from state ({new_message_from_state.__class__.__name__}, ID: {msg_id}) did not trigger A,B,C logic. Current Node: {current_debugger_node_id}, Tool Proc: {agent_is_processing_tool_output}")

#             except Exception as e:
#                     logger.error(f"Error processing latest message from state (V12.8): {e}", exc_info=True)
#                     yield await _yield_event("error_message", {"error": "Error processing state update.", "details": str(e)})

#         # --- End main async for chunk loop ---

#         logger.info(f"[STREAMING_V12.8_DBG] LangGraph stream log loop FINISHED. Final debugger node: '{current_debugger_node_id}', tool_proc: {agent_is_processing_tool_output}")

#         # Post-loop cleanup for debugger events
#         if current_debugger_node_id and current_debugger_node_id != END:
#             debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_end", "nodeId": current_debugger_node_id}, last_yielded_node_start_id)
#             if debugger_event: yield debugger_event
#             current_debugger_node_id = END
#             if last_yielded_node_start_id != END :
#                 debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_start", "nodeId": current_debugger_node_id}, last_yielded_node_start_id)
#                 if debugger_event: yield debugger_event
#             debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_end", "nodeId": current_debugger_node_id}, last_yielded_node_start_id)
#             if debugger_event: yield debugger_event
#         elif not current_debugger_node_id and current_debugger_node_id != END :
#              debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_start", "nodeId": END}, last_yielded_node_start_id)
#              if debugger_event: yield debugger_event
#              debugger_event, last_yielded_node_start_id = _prepare_debugger_event({"type": "node_end", "nodeId": END}, last_yielded_node_start_id)
#              if debugger_event: yield debugger_event

#         # Handle project generation job submission
#         if project_gen_triggered and project_request_arg is not None:
#             request_str = json.dumps(project_request_arg) if isinstance(project_request_arg, dict) else str(project_request_arg)
#             job_id = str(uuid.uuid4())
#             try:
#                 job_store = get_job_store_instance()
#                 initial_job_data = { "submitted_at": time.time(), "request": request_str, "status": "pending" }
#                 await job_store.initialize_job(job_id, initial_job_data)
#                 background_tasks.add_task(run_project_gen_in_background, job_id, request_str)
#                 yield await _yield_event("status_update", {"message": f"Project generation started (Job ID: {job_id})."})
#             except Exception as store_err:
#                 logger.error(f"STREAMING_V12.8: Failed to initialize Job [{job_id}] in Redis: {store_err}", exc_info=True)
#                 yield await _yield_event("error_message", {"error": "Failed to initiate background project generation job."})

#     except AgentNotReadyError as anre:
#         logger.error(f"[STREAMING_V12.8] AgentNotReadyError: {anre}", exc_info=True)
#         yield await _yield_event("error_message", {"error": f"Agent not ready: {anre}"})
#     except Exception as e:
#         logger.error(f"[STREAMING_V12.8] Unexpected error: {e}", exc_info=True)
#         yield await _yield_event("error_message", {"error": f"An unexpected error occurred: {e}"})
#     finally:
#         logger.info("[STREAMING_V12.8] Yielding stream_end.")
#         yield await _yield_event("stream_end", {})

# async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
#     """Retrieves the status of a background job."""
#     try: job_store = get_job_store_instance()
#     except Exception as store_err:
#         logger.error(f"Failed to get Job Store instance for get_job_status: {store_err}", exc_info=True)
#         return None
#     return await job_store.get_job(job_id)