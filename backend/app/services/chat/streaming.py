# backend/app/services/chat/streaming.py

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
from langgraph.graph.state import END

# App imports
from app import schemas, config
from app.utils import get_logger
from app.errors import AgentNotReadyError # Import from new location
from app.core.ai.agents.executor import get_langgraph_app, AgentState
# --- Corrected Imports: Remove direct job function imports, they are handled by jobs_service now ---
# from app.services.jobs_service import initialize_project_generation_job, run_project_gen_in_background
# We will still import the service itself if needed to *initiate* jobs via API calls (but not execute directly)
from app.services import jobs_service # Import the service module to call its functions
# -------------------------------------------------------------------------------------------------------
from app.services.chat.events import yield_ui_event, prepare_debugger_event # Import from events module

logger = get_logger(__name__) # Logger specific to this module

# --- Main Streaming Handler ---
async def handle_chat_request_stream(
    request: schemas.AskRequest,
    background_tasks: BackgroundTasks # Keep BackgroundTasks for now, though ideally use job queue via jobs_service
) -> AsyncGenerator[Dict[str, Any], None]:
    """Handles streaming chat requests with detailed UI events including RAG context."""

    # --- Message Preparation ---
    base_question = request.question; input_prefix = ""
    has_filenames = bool(request.filenames and len(request.filenames) > 0); has_tag = bool(request.tag_filter)
    if has_filenames and has_tag: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}] with tag '{request.tag_filter}', answer this: "
    elif has_filenames: filenames_str = ", ".join(request.filenames) if len(request.filenames) <= 3 else f"{len(request.filenames)} selected files"; input_prefix = f"Regarding the document(s) [{filenames_str}], answer this: "
    elif has_tag: input_prefix = f"Regarding documents with the tag '{request.tag_filter}', answer this: "
    user_input_content = f"{input_prefix}{base_question}"
    initial_messages_for_graph: List[BaseMessage] = []
    if request.chat_history:
        for msg_data in request.chat_history:
             sender = msg_data.get('sender'); text = msg_data.get('text', '')
             if sender == 'user': initial_messages_for_graph.append(HumanMessage(content=text))
             elif sender == 'ai': initial_messages_for_graph.append(AIMessage(content=text))
    initial_messages_for_graph.append(HumanMessage(content=user_input_content))
    graph_input: AgentState = {"messages": initial_messages_for_graph}

    project_gen_triggered = False
    project_request_arg: Optional[Union[str, Dict]] = None

    # State Tracking
    current_debugger_node_id: str = "agent"
    last_yielded_node_start_id: Optional[str] = None
    active_tool_call_info: Optional[Dict[str, Any]] = None
    active_tool_name_for_ui: Optional[str] = None
    agent_is_processing_tool_output = False
    processed_driving_message_ids = set()

    # --- Start Streaming ---
    yield await yield_ui_event("thinking_started", {"message": "LearnMate is thinking..."})
    logger.info(f"STREAMING V12.9 (Corrected Imports): Starting graph stream for: {request.question[:50]}...") # Version Bump
    logger.info(f"[V12.9_INIT_STATE] current_debugger_node_id='{current_debugger_node_id}', agent_is_processing_tool_output={agent_is_processing_tool_output}")

    try:
        langgraph_app = get_langgraph_app()
        if not langgraph_app: raise AgentNotReadyError("LangGraph App not ready.")
        run_config_obj: RunnableConfig = { "recursion_limit": 25, "configurable": {"thread_id": str(uuid.uuid4())} }
        logger.info(f"Invoking LangGraph App astream_log V12.9 with config: {run_config_obj}")

        # Yield initial debugger node start
        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_start", "nodeId": current_debugger_node_id}, last_yielded_node_start_id)
        if debugger_event: yield debugger_event

        last_seen_message_count = len(initial_messages_for_graph)

        # --- Main Streaming Loop ---
        async for chunk in langgraph_app.astream_log(graph_input, config=run_config_obj):
            # 1. Process token streams
            for op_token in chunk.ops:
                path_token: str = op_token.get("path", "")
                value_token = op_token.get("value")
                if path_token.endswith(("/streamed_output_str/-", "/streamed_output/-")) and current_debugger_node_id == "agent":
                    token_content = None
                    if path_token.endswith("/streamed_output_str/-") and isinstance(value_token, str) and value_token: token_content = value_token
                    elif path_token.endswith("/streamed_output/-") and isinstance(value_token, AIMessageChunk) and value_token.content:
                         if not getattr(value_token, 'tool_call_chunks', None): token_content = value_token.content
                    if token_content: yield await yield_ui_event("ai_message_chunk", {"content_chunk": token_content})

            # 2. Check for new messages in state to drive logic (A, B, C)
            try:
                current_graph_state = langgraph_app.get_state(run_config_obj)
                all_current_messages_from_state = current_graph_state.values.get('messages', [])

                # Yield debugger state update
                if all_current_messages_from_state:
                    serializable_messages_for_history = []
                    for msg_val_hist in all_current_messages_from_state:
                        msg_dict_data_hist = {"type": getattr(msg_val_hist, 'type', 'unknown'), "content": getattr(msg_val_hist,'content', None)}
                        if hasattr(msg_val_hist, 'tool_calls'): msg_dict_data_hist['tool_calls'] = getattr(msg_val_hist,'tool_calls')
                        if hasattr(msg_val_hist, 'tool_call_id'): msg_dict_data_hist['tool_call_id'] = getattr(msg_val_hist,'tool_call_id')
                        serializable_messages_for_history.append(msg_dict_data_hist)
                    debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "state_update", "state": {"messages": serializable_messages_for_history}}, last_yielded_node_start_id)
                    if debugger_event: yield debugger_event

                # Check if a new message drives the main logic
                if len(all_current_messages_from_state) > last_seen_message_count:
                    new_message_from_state: BaseMessage = all_current_messages_from_state[-1]
                    last_seen_message_count = len(all_current_messages_from_state)
                    msg_id = getattr(new_message_from_state, 'id', None)
                    if msg_id and msg_id in processed_driving_message_ids: continue

                    logger.critical(f"[V12.9_NEW_STATE_MSG] Class: {new_message_from_state.__class__.__name__}, ID: {msg_id}")
                    message_tool_calls = getattr(new_message_from_state, 'tool_calls', getattr(new_message_from_state, 'tool_call_chunks', None))

                    # --- A. Agent decides to call a tool ---
                    if current_debugger_node_id == "agent" and not agent_is_processing_tool_output and \
                       isinstance(new_message_from_state, (AIMessage, AIMessageChunk)) and message_tool_calls and len(message_tool_calls) > 0:
                        logger.critical(f"[V12.9_LOGIC_A_HIT] Agent decides tool call.")
                        if msg_id: processed_driving_message_ids.add(msg_id)
                        tc_data = message_tool_calls[0]
                        args_data = getattr(tc_data, 'args', tc_data.get('args') if isinstance(tc_data, dict) else "{}")
                        try: parsed_args = json.loads(args_data) if isinstance(args_data, str) else args_data
                        except: parsed_args = args_data
                        active_tool_call_info = {"id": getattr(tc_data, 'id', tc_data.get('id') if isinstance(tc_data, dict) else None),"name": getattr(tc_data, 'name', tc_data.get('name') if isinstance(tc_data, dict) else None),"args": parsed_args}
                        active_tool_name_for_ui = active_tool_call_info.get('name')

                        # Emit Specific Status Updates based on Tool
                        tool_call_ui_msg = f"Using tool: {active_tool_name_for_ui}..."
                        if active_tool_name_for_ui == "search_web_raw":
                            query_arg = parsed_args.get('query', 'your query') if isinstance(parsed_args, dict) else "your query"
                            tool_call_ui_msg = f"[Search] Searching web for '{str(query_arg)[:50]}...'"
                            yield await yield_ui_event("status_update", {"message": "[Fetch] Looking for relevant pages..."})
                        elif active_tool_name_for_ui == "query_uploaded_documents":
                            query_arg = parsed_args.get('query', 'your query') if isinstance(parsed_args, dict) else "your query"
                            tool_call_ui_msg = f"[RAG] Searching documents for '{str(query_arg)[:50]}...'"
                        elif active_tool_name_for_ui == "summarize_document_content":
                            filename_arg = parsed_args.get('filename', 'unknown file') if isinstance(parsed_args, dict) else "unknown file"
                            tool_call_ui_msg = f"[Summarize Doc] Preparing summary for '{str(filename_arg)[:50]}...'"
                        elif active_tool_name_for_ui == "generate_software_project":
                            tool_call_ui_msg = "[Project] Starting software project generation..."
                            project_gen_triggered = True; project_request_arg = active_tool_call_info.get('args')

                        yield await yield_ui_event("tool_call_initiated", {"tool_name": active_tool_name_for_ui, "tool_input": parsed_args, "message": tool_call_ui_msg})

                        # Debugger Events & State Transition
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_output", "nodeId": "agent", "output": new_message_from_state.dict()}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_end", "nodeId": "agent"}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "tool_call", "toolCall": active_tool_call_info}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event
                        current_debugger_node_id = "action"
                        logger.critical(f"[V12.9_TRANSITION_A_POST] New cur_node='{current_debugger_node_id}', tool_proc='{agent_is_processing_tool_output}'")
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_start", "nodeId": current_debugger_node_id}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event

                    # --- B. Tool provides result ---
                    elif current_debugger_node_id == "action" and isinstance(new_message_from_state, ToolMessage):
                        logger.critical(f"[V12.9_LOGIC_B_HIT] Tool provides result.")
                        if msg_id: processed_driving_message_ids.add(msg_id)
                        tool_msg: ToolMessage = new_message_from_state
                        tool_result_data_for_dbg = {"id": tool_msg.tool_call_id, "result": tool_msg.content} # Raw content for debugger

                        yield await yield_ui_event("status_update", {"message": f"[Processing] Received results from {active_tool_name_for_ui or 'tool'}."})

                        # Process Tool Output for UI Events and Agent Context
                        agent_context_content = tool_msg.content # Default

                        # Handle RAG Tool Output
                        if active_tool_name_for_ui == "query_uploaded_documents":
                            try:
                                content_data = json.loads(tool_msg.content)
                                agent_context_content = content_data.get("answer", "Could not extract answer from RAG tool.")
                                rag_sources = content_data.get("rag_sources", [])
                                if rag_sources and isinstance(rag_sources, list):
                                    valid_rag_sources = []
                                    for src in rag_sources:
                                        if isinstance(src, dict) and "filename" in src and "snippet" in src:
                                             valid_rag_sources.append({ "filename": src.get("filename"), "page": src.get("page", "N/A"), "snippet": src.get("snippet") })
                                    if valid_rag_sources:
                                         yield await yield_ui_event("rag_context_found", {"context": valid_rag_sources})
                                         yield await yield_ui_event("status_update", {"message": f"[Analyzing] Found context in {len(valid_rag_sources)} document chunk(s)."})
                                    else: yield await yield_ui_event("status_update", {"message": "[Analyzing] RAG tool ran but returned no valid sources."})
                                else: yield await yield_ui_event("status_update", {"message": "[Analyzing] RAG tool ran, processing result..."})
                                yield await yield_ui_event("status_update", {"message": "[Generating] Preparing response based on documents..."})
                            except Exception as e:
                                logger.error(f"Error processing RAG tool '{active_tool_name_for_ui}' result: {e}", exc_info=True)
                                yield await yield_ui_event("status_update", {"message": "[Error] Could not process RAG results."})
                                yield await yield_ui_event("status_update", {"message": "[Generating] Preparing response..."})
                                agent_context_content = f"Error processing RAG result: {e}"

                        # Handle Refactored Web Search Tool Output
                        elif active_tool_name_for_ui == "search_web_raw":
                            try:
                                sources_from_tool = json.loads(tool_msg.content)
                                if sources_from_tool and isinstance(sources_from_tool, list):
                                    valid_sources_for_ui = []
                                    combined_content_for_agent = []
                                    for src in sources_from_tool:
                                        if isinstance(src, dict) and "url" in src and "title" in src and "cleaned_content" in src:
                                            valid_sources_for_ui.append({ "title": src.get("title", "Untitled"), "url": src.get("url"), "snippet": src.get("snippet", None) })
                                            combined_content_for_agent.append(f"Source URL: {src.get('url')}\nSource Title: {src.get('title')}\nContent:\n{src.get('cleaned_content', '')}\n---")
                                    if valid_sources_for_ui:
                                        yield await yield_ui_event("sources_found", {"sources": valid_sources_for_ui})
                                        yield await yield_ui_event("status_update", {"message": f"[Processing] Retrieved content from {len(valid_sources_for_ui)} web source(s)."})
                                        agent_context_content = "\n\n".join(combined_content_for_agent)
                                    else:
                                        yield await yield_ui_event("status_update", {"message": "[Processing] Web search complete (no valid sources found)."})
                                        agent_context_content = "Web search did not find relevant content."
                                else:
                                     yield await yield_ui_event("status_update", {"message": "[Processing] Web search results received (no sources list)."})
                                     agent_context_content = "Web search did not find relevant content."
                                yield await yield_ui_event("status_update", {"message": "[Generating] Preparing response based on web search..."})
                            except json.JSONDecodeError:
                                logger.error(f"Failed to parse JSON from web tool '{active_tool_name_for_ui}': {tool_msg.content[:200]}")
                                yield await yield_ui_event("status_update", {"message": "[Error] Could not process web search results."})
                                yield await yield_ui_event("status_update", {"message": "[Generating] Preparing response..."})
                                agent_context_content = f"Error processing web search result: Malformed JSON"
                            except Exception as e:
                                logger.error(f"Error processing web tool '{active_tool_name_for_ui}' result: {e}", exc_info=True)
                                yield await yield_ui_event("status_update", {"message": "[Error] Problem analyzing web search results."})
                                yield await yield_ui_event("status_update", {"message": "[Generating] Preparing response..."})
                                agent_context_content = f"Error processing web search result: {e}"

                        # Handle other tools
                        else:
                             if active_tool_name_for_ui == "summarize_document_content":
                                 agent_context_content = tool_msg.content # Agent gets summary string
                                 yield await yield_ui_event("status_update", {"message": "[Processing] Received document summary."})
                             yield await yield_ui_event("status_update", {"message": f"[Generating] Preparing response after {active_tool_name_for_ui}..."})

                        # Modify ToolMessage content for agent
                        tool_msg.content = agent_context_content

                        # Debugger Events and State Transition
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "tool_result", "toolResult": tool_result_data_for_dbg}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_output", "nodeId": "action", "output": tool_msg.content}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_end", "nodeId": "action"}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event
                        active_tool_call_info = None; active_tool_name_for_ui = None
                        current_debugger_node_id = "agent"; agent_is_processing_tool_output = True
                        logger.critical(f"[V12.9_TRANSITION_B_POST] New cur_node='{current_debugger_node_id}', tool_proc='{agent_is_processing_tool_output}'")
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_start", "nodeId": current_debugger_node_id}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event

                    # --- C. Agent gives final answer ---
                    elif current_debugger_node_id == "agent" and \
                         isinstance(new_message_from_state, (AIMessage, AIMessageChunk)) and \
                         not (message_tool_calls and len(message_tool_calls) > 0):
                        logger.critical(f"[V12.9_LOGIC_C_HIT] Agent provides AIMessage. tool_proc_flag: {agent_is_processing_tool_output}")
                        if msg_id: processed_driving_message_ids.add(msg_id)
                        yield await yield_ui_event("final_answer_turn_complete", {"message_id": msg_id})
                        # Debugger Events & State Transition
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_output", "nodeId": "agent", "output": new_message_from_state.dict()}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_end", "nodeId": "agent"}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event
                        current_debugger_node_id = END
                        agent_is_processing_tool_output = False
                        logger.critical(f"[V12.9_TRANSITION_C_POST] New cur_node='{current_debugger_node_id}', tool_proc='{agent_is_processing_tool_output}'")
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_start", "nodeId": current_debugger_node_id}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event
                        debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_end", "nodeId": current_debugger_node_id}, last_yielded_node_start_id);
                        if debugger_event: yield debugger_event

                    else:
                        logger.warning(f"[V12.9_MSG_UNHANDLED_LOGIC] Latest message from state ({new_message_from_state.__class__.__name__}, ID: {msg_id}) did not trigger A,B,C logic. Current Node: {current_debugger_node_id}, Tool Proc: {agent_is_processing_tool_output}")

            except Exception as e:
                    logger.error(f"Error processing latest message from state (V12.9): {e}", exc_info=True)
                    yield await yield_ui_event("error_message", {"error": "Error processing state update.", "details": str(e)})

        # --- End main async for chunk loop ---

        logger.info(f"[STREAMING_V12.9_DBG] LangGraph stream log loop FINISHED.")

        # Post-loop cleanup for debugger events
        if current_debugger_node_id and current_debugger_node_id != END:
            debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_end", "nodeId": current_debugger_node_id}, last_yielded_node_start_id)
            if debugger_event: yield debugger_event
            current_debugger_node_id = END
            if last_yielded_node_start_id != END :
                debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_start", "nodeId": current_debugger_node_id}, last_yielded_node_start_id)
                if debugger_event: yield debugger_event
            debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_end", "nodeId": current_debugger_node_id}, last_yielded_node_start_id)
            if debugger_event: yield debugger_event
        elif not current_debugger_node_id and current_debugger_node_id != END :
             debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_start", "nodeId": END}, last_yielded_node_start_id)
             if debugger_event: yield debugger_event
             debugger_event, last_yielded_node_start_id = prepare_debugger_event({"type": "node_end", "nodeId": END}, last_yielded_node_start_id)
             if debugger_event: yield debugger_event

        # Handle project generation job submission using jobs_service
        if project_gen_triggered and project_request_arg is not None:
            # Use the new service function to initialize and queue
            job_id = await jobs_service.initialize_project_generation_job(project_request_arg)
            if job_id:
                # Use BackgroundTasks for now, but ideally jobs_service.start_job would handle queueing
                background_tasks.add_task(jobs_service.run_project_gen_in_background, job_id, json.dumps(project_request_arg) if isinstance(project_request_arg, dict) else str(project_request_arg))
                yield await yield_ui_event("status_update", {"message": f"Project generation started (Job ID: {job_id})."})
            else:
                yield await yield_ui_event("error_message", {"error": "Failed to initiate background project generation job."})

    except AgentNotReadyError as anre:
        logger.error(f"[STREAMING_V12.9] AgentNotReadyError: {anre}", exc_info=True)
        yield await yield_ui_event("error_message", {"error": f"Agent not ready: {anre}"})
    except Exception as e:
        logger.error(f"[STREAMING_V12.9] Unexpected error: {e}", exc_info=True)
        yield await yield_ui_event("error_message", {"error": f"An unexpected error occurred: {e}"})
    finally:
        logger.info("[STREAMING_V12.9] Yielding stream_end.")
        yield await yield_ui_event("stream_end", {})