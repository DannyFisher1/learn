# backend/app/services/chat/events.py

import json
import logging
from typing import Dict, Any, Optional, Tuple

# App imports
from app.utils import get_logger

logger = get_logger(__name__) # Use specific logger for this module

# --- Event Formatting Helpers (Moved from chat_service.py) ---
async def yield_ui_event(event_type_for_ui: str, data_payload_for_ui: Dict[str, Any]) -> Dict[str, str]:
    """Formats custom UI events for SSE, compatible with sse-starlette."""
    actual_payload_for_frontend = {
        "type": event_type_for_ui,
        "data": json.dumps(data_payload_for_ui, default=str)
    }
    sse_dict_to_yield = {
        "event": event_type_for_ui,
        "data": json.dumps(actual_payload_for_frontend, default=str)
    }
    # Use the specific logger instance for this module
    logger.debug(f"Yielding SSE Event: Name='{sse_dict_to_yield['event']}', SSE Data Field='{sse_dict_to_yield['data'][:200]}...'")
    return sse_dict_to_yield

def prepare_debugger_event(event_data: Dict[str, Any], last_yielded_node_start_id: Optional[str]) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """ Prepares debugger event and updates the last yielded node ID. """
    new_last_yielded_id = last_yielded_node_start_id
    event_to_yield = None
    etype = event_data.get("type")
    node_id = event_data.get("nodeId")
    # Logic to prevent duplicate node_start and handle node_end reset
    if etype == "node_start":
        if node_id != last_yielded_node_start_id or node_id is None:
            new_last_yielded_id = node_id
            event_to_yield = {"event": "log_data", "data": json.dumps(event_data, default=str)}
    elif etype == "node_end":
        if node_id == last_yielded_node_start_id and node_id is not None:
            new_last_yielded_id = None # Reset on node end
        event_to_yield = {"event": "log_data", "data": json.dumps(event_data, default=str)}
    else: # For other types like state_update, tool_call, etc., yield directly
         event_to_yield = {"event": "log_data", "data": json.dumps(event_data, default=str)}
    return event_to_yield, new_last_yielded_id
# --- End Event Formatting Helpers ---