# utils/output_parser.py
import re
import json # Import the json module
from typing import List, Optional, Tuple, Dict # Add Dict
from rich import print
from rich.panel import Panel
from json_repair import repair_json
import re 

def parse_task_decomposition_output(llm_output: str) -> Tuple[Optional[str], Optional[List[Dict]]]:
    """
    Parses LLM output containing file structure and task checklist JSON.
    Uses json_repair if available to handle malformed JSON.
    
    Args:
        llm_output (str): The complete LLM output containing both file structure
                          and task checklist JSON.
    
    Returns:
        tuple: (file_structure_str, tasks_list_json)
               file_structure_str - The file structure as a string
               tasks_list_json - The task checklist as a parsed JSON object
    """
    # Split the output into parts
    parts = llm_output.split('```')
    
    # The file structure is between the first set of backticks
    file_structure_str = parts[1].strip()
    
    # The JSON is between the second set of backticks (after 'json')
    json_str_raw = parts[3].strip()
    
    json_str = repair_json(json_str_raw)


    return file_structure_str, json_str


def extract_code_block(llm_output: str, language: Optional[str] = None) -> Optional[str]:
    """
    Extracts the first code block from LLM output, optionally matching language.
    Handles markdown code fences (```). More robust fallback.
    (This function might now be primarily used by code_generator/test_creator)
    """
    # Pattern to find fenced code blocks, optionally matching language
    if language:
        # Match specific language OR generic fence if language specified but not found
        patterns = [
            rf"```{language}\s*\n(.*?)\n```", # Specific language tag
            r"```\s*\n(.*?)\n```"            # Generic fence as fallback
        ]
    else:
        # Match any language or no language specified
        patterns = [r"```(?:\w+)?\s*\n(.*?)\n```"]

    code_content = None
    for pattern in patterns:
        match = re.search(pattern, llm_output, re.DOTALL | re.IGNORECASE)
        if match:
            code_content = match.group(1).strip()
            break # Found a match, stop searching

    # Fallback: If no fenced block found, check if the entire output might be code
    if code_content is None and "```" not in llm_output:
        stripped_output = llm_output.strip()
        lines = stripped_output.split('\n')
        common_code_chars = ['{', '}', '(', ')', '=', ':', ';', '<', '>']
        common_code_keywords = ['import ', 'def ', 'class ', 'const ', 'let ', 'function ', 'public ', 'private ', 'return ', 'if ', 'for ', 'while ', 'await ', 'async ']
        is_likely_code = len(lines) > 0 and \
                         (any(c in stripped_output for c in common_code_chars) or \
                          any(kw in stripped_output for kw in common_code_keywords))
        avg_line_len = sum(len(l) for l in lines) / len(lines) if lines else 0
        if is_likely_code and avg_line_len < 100: # Adjusted threshold
             # Avoid assuming long natural language is code
             if len(lines) > 1 or len(stripped_output) < 2000: # Avoid huge blocks of text
                 print(f"[yellow]Warning:[/yellow] No code fence '```' found. Assuming the entire output might be the intended code block.")
                 code_content = stripped_output

    if code_content is None:
        print(f"[bold red]Error:[/bold red] Could not extract code block from LLM output.")
        print("--- LLM Output Snippet (first 1000 chars) ---")
        print(llm_output[:1000] + ("..." if len(llm_output) > 1000 else ""))
        print("--------------------------")

    return code_content