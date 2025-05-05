# components/task_decomposer.py
"""
Handles the task decomposition step by calling the appropriate parser
for the LLM output (expected in Markdown checklist format).
"""

from typing import Optional, Tuple, List
from rich import print
import json
# Assuming the parser is in utils.output_parser
from app.core.project_generator.utils.output_parser import parse_task_decomposition_output
from json_repair import repair_json
from app.utils import get_logger
from typing import Dict, Any

logger = get_logger(__name__)



def decompose_tasks(
    llm_output: str
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]: # Correct return type hint
    """
    Orchestrates the parsing of the LLM's task decomposition output,
    returning the file structure and the PARSED task dictionary.
    """
    logger.debug("Decomposing tasks from LLM output...")
    file_structure_str, json_string = parse_task_decomposition_output(llm_output) # Assume this correctly extracts the JSON *string*

    if json_string is None:
        logger.error("Parsing failed to extract JSON string from LLM output.")
        return file_structure_str, None # Return None if extraction failed

    # --- Parse the extracted JSON string here ---
    try:
        logger.debug(f"Attempting to repair and load JSON string (length: {len(json_string)})...")
        repaired_json_string = repair_json(json_string)
        tasks_dict = json.loads(repaired_json_string)
        logger.info("Successfully parsed JSON string into dictionary.")
        # Basic validation after loading
        if not isinstance(tasks_dict, dict) or "task_checklist" not in tasks_dict:
             logger.error(f"Parsed JSON dict is invalid or missing 'task_checklist'. Parsed: {tasks_dict}")
             return file_structure_str, None
        if not isinstance(tasks_dict["task_checklist"], list):
             logger.error(f"Parsed 'task_checklist' is not a list. Type: {type(tasks_dict['task_checklist'])}")
             return file_structure_str, None

        return file_structure_str, tasks_dict # <<< Return the PARSED dictionary
    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError after repair: {e}")
        logger.debug(f"Repaired JSON string attempted: {repaired_json_string[:500]}...")
        return file_structure_str, None # Return None on parsing failure
    except Exception as e:
         logger.error(f"Unexpected error parsing JSON string: {e}", exc_info=True)
         logger.debug(f"Original JSON string attempted: {json_string[:500]}...")
         return file_structure_str, None
    #