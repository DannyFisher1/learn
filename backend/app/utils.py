# app/utils.py

import os
import logging
import sys
from pathlib import Path
# --- Added imports for serialization ---
from typing import List, Dict, Any
from langchain_core.agents import AgentAction
# --------------------------------------
from typing import Union

# --- Logging Setup ---
# (Keep existing logging setup)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler = logging.StreamHandler(sys.stdout) # Log to stdout
log_handler.setFormatter(log_formatter)

# --- Set Default Level to DEBUG for more verbose logging during troubleshooting ---
def get_logger(name: str, level=logging.DEBUG) -> logging.Logger:
    """Gets a configured logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(log_handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger

root_logger = get_logger(__name__) # Root logger will also be DEBUG now

# --- Directory Management ---
# (Keep existing ensure_directory_exists function)
def ensure_directory_exists(dir_path: Union[str, Path]):
    """Checks if a directory exists and creates it if it doesn't."""
    path = Path(dir_path)
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
            root_logger.info(f"Created directory: {path}")
        except OSError as e:
            root_logger.error(f"Error creating directory {path}: {e}", exc_info=True)
            raise # Re-raise the exception as this is critical for storage
    elif not path.is_dir():
         error_msg = f"Path exists but is not a directory: {path}"
         root_logger.error(error_msg)
         raise NotADirectoryError(error_msg)


# --- NEW: Agent Step Serialization ---
def serialize_intermediate_steps(steps: List[Any]) -> List[Dict[str, Any]]:
    """
    Converts agent intermediate steps (tool calls and observations)
    into a JSON-serializable list of dictionaries for API responses.
    """
    serialized_steps = []
    if not isinstance(steps, list):
        root_logger.warning(f"Received non-list input for intermediate steps serialization: {type(steps)}")
        return []

    for step in steps:
        # Intermediate steps are often tuples: (AgentAction, observation: Any)
        if isinstance(step, tuple) and len(step) == 2:
            action, observation = step
            step_dict = {}
            if isinstance(action, AgentAction):
                # Ensure all parts of AgentAction are serializable
                tool_input = action.tool_input
                # Basic serialization for common types
                if not isinstance(tool_input, (str, int, float, bool, list, dict, type(None))):
                     tool_input_str = str(tool_input)
                     root_logger.debug(f"Serializing non-standard tool_input type {type(tool_input)} to string.")
                     tool_input = tool_input_str

                step_dict["action"] = {
                    "tool": action.tool,
                    "tool_input": tool_input,
                    "log": action.log.strip() if isinstance(action.log, str) else str(action.log) # Clean up log whitespace
                }
            else:
                 # Fallback if action is not an AgentAction object
                 step_dict["action"] = str(action)

            # Serialize observation similarly
            if not isinstance(observation, (str, int, float, bool, list, dict, type(None))):
                 observation_str = str(observation)
                 root_logger.debug(f"Serializing non-standard observation type {type(observation)} to string.")
                 observation = observation_str

            step_dict["observation"] = observation

            serialized_steps.append(step_dict)
        else:
            # Handle unexpected step format if necessary
            root_logger.warning(f"Unexpected intermediate step format: {type(step)}. Converting to string.")
            serialized_steps.append({"step_data": str(step)}) # Fallback

    return serialized_steps

# (Keep other utilities like format_metadata_source if you have them)