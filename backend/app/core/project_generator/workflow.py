# app/core/project_generator/workflow.py

import os
import re
import json
import asyncio
from pathlib import Path
import datetime
import time
import traceback
import logging # <<< Use standard logging
from typing import List, Tuple, Optional, Dict, Any, AsyncGenerator
from pydantic import BaseModel, Field # <<< Use Pydantic for state
import randomname
# Langchain/LLM imports
from langchain_core.language_models import BaseChatModel
from langchain_core.exceptions import LangChainException


# --- App Component Imports ---
# Note: Assuming these components were also moved and imports updated
# within their own files to use the new get_llm() etc.
from app.core.project_generator.components import prd_generator, task_generator, code_generator, test_creator, task_decomposer
from app.core.project_generator.utils.output_parser import parse_task_decomposition_output # Assuming task_decomposer uses this
from app.core.ai.llm import get_llm # <<< Use the centralized getter
from app.utils import get_logger, ensure_directory_exists # App-level utils
from app.core.project_generator.testing import run_project_tests, _create_and_activate_venv # <<< Import venv creator
from app import config as app_config # App-level config

# --- Initialize Logger ---
logger = get_logger(__name__)

# --- Configuration ---
# Use a configurable base directory, potentially from app_config
# Defaulting to 'data/generated_projects' relative to backend base
PROJECT_GENERATOR_OUTPUT_BASE_DIR = getattr(app_config, "PROJECT_GENERATOR_OUTPUT_BASE_DIR_STR")
ensure_directory_exists(PROJECT_GENERATOR_OUTPUT_BASE_DIR)

print(f"Project Generator Output Base Directory: {PROJECT_GENERATOR_OUTPUT_BASE_DIR}")
logger.info(f"Project Generator Output Base Directory: {PROJECT_GENERATOR_OUTPUT_BASE_DIR}")
randomname = randomname.get_name()
# --- Workflow State Model ---

# Helper function to generate default name
def _generate_default_project_name() -> str:
    return f"{randomname}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

class ProjectWorkflowState(BaseModel):
    """Holds the state of the project generation workflow."""
    request: str
    start_time: float = Field(default_factory=time.time)
    llm_instance: BaseChatModel # LLM passed explicitly
    project_name: str = Field(default_factory=_generate_default_project_name) # <<< Use factory for default name
    project_output_dir: Optional[Path] = None
    prd_markdown: Optional[str] = None
    task_decomposition_raw: Optional[str] = None

    # --- Venv --- # <<< Added
    venv_creation_task: Optional[asyncio.Task] = None # <<< Added
    venv_python_path: Optional[str] = None # <<< Added

    # --- Test Results ---
    test_results_summary: Optional[str] = None
    tests_passed: Optional[bool] = None

    # --- Project Generation ---
    file_structure_str: Optional[str] = None
    tasks_dict: Optional[Dict[str, Any]] = None # Holds the parsed JSON checklist
    generated_files: Dict[str, str] = Field(default_factory=dict) # path -> content
    generated_tests: Dict[str, str] = Field(default_factory=dict) # test_path -> content
    errors: List[str] = Field(default_factory=list)
    status_updates: List[str] = Field(default_factory=list)
    current_step: str = "Initialized"
    is_complete: bool = False
    final_message: Optional[str] = None

    # --- Exclude LLM and Task from model serialization ---
    model_config = {
        "arbitrary_types_allowed": True,
        "exclude": {"llm_instance", "venv_creation_task"} # <<< Added venv_creation_task
    }

# --- Helper Functions (Adapted) ---

def _get_project_name_from_prd(prd_markdown: str) -> str:
    """Extracts project name from PRD title. Returns None if not found."""
    # Does not return default name here anymore, only extracts or returns None
    if not prd_markdown:
        return None
    match = re.search(r"^# PRD:\s*(.*)", prd_markdown, re.IGNORECASE | re.MULTILINE)
    if match:
        name = match.group(1).strip()
        if not name: # Handle empty name after title
             return None
        # Sanitize the extracted name
        name = re.sub(r'[^\w\s-]', '', name).strip()
        name = re.sub(r'[-\s]+', '_', name).lower()
        return name if name else None # Return None if name becomes empty after sanitization
    return None # Return None if regex doesn't match

async def _save_file_async(file_path: Path, content: str) -> bool:
    """Async wrapper for saving a file."""
    def _save():
        try:
            # Basic security check (can be enhanced)                      # if it's not already a Path
            base_dir  = Path(PROJECT_GENERATOR_OUTPUT_BASE_DIR).resolve()
            if not str(file_path.resolve()).startswith(str(base_dir)):
                 logger.error(f"Security Error: Attempted save outside designated output base: {file_path}")
                 return False
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.debug(f"Saved file: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving file {file_path}: {e}", exc_info=True)
            return False
    return await asyncio.to_thread(_save)

# --- Workflow Step Functions ---

async def generate_prd_step(state: ProjectWorkflowState, project_output_base_dir: Path) -> bool:
    """Generates the Product Requirements Document and attempts to update project name."""
    state.current_step = "Generating PRD"
    # Project name already has a default value from initialization
    logger.info(f"[{state.project_name}] Starting Step: {state.current_step}")

    try:
        prd_md = await asyncio.to_thread(
            prd_generator.generate_prd, state.request, state.llm_instance
        )
        if not prd_md or not isinstance(prd_md, str):
            raise ValueError("PRD generation returned invalid or empty content.")

        state.prd_markdown = prd_md

        # Attempt to extract a better name from PRD
        extracted_name = _get_project_name_from_prd(state.prd_markdown)
        if extracted_name:
            logger.info(f"[{state.project_name}] Extracted project name '{extracted_name}' from PRD. Updating.")
            state.project_name = extracted_name
        else:
             logger.info(f"[{state.project_name}] Could not extract specific name from PRD. Using default: {state.project_name}")

        # Ensure project output directory uses the potentially updated name
        state.project_output_dir = project_output_base_dir / state.project_name
        ensure_directory_exists(state.project_output_dir)
        logger.info(f"[{state.project_name}] PRD generated. Project Output Dir: {state.project_output_dir}")
        return True
    except Exception as e:
        error_msg = f"Error during PRD generation: {e}"
        logger.error(f"[{state.project_name}] {error_msg}", exc_info=True)
        state.errors.append(error_msg)
        # Ensure output dir is set even on failure IF name exists (it should always have default now)
        if state.project_name and not state.project_output_dir:
             state.project_output_dir = project_output_base_dir / state.project_name
             # Don't necessarily create it if PRD failed, maybe just log
             logger.warning(f"[{state.project_name}] Setting output dir path ({state.project_output_dir}) despite PRD failure for potential logging/cleanup.")
        return False

async def generate_tasks_step(state: ProjectWorkflowState) -> bool:
    """Generates and parses the task decomposition."""
    if not state.prd_markdown:
        state.errors.append("Cannot generate tasks without PRD.")
        return False
    state.current_step = "Generating Tasks"
    logger.info(f"[{state.project_name}] Starting Step: {state.current_step}")
    state.status_updates.append(f"{datetime.datetime.now()}: Starting Task Decomposition...")

    # --- Generate Raw Output ---
    try:
        # Assuming task_generator.generate_tasks is synchronous internally
        raw_output = await asyncio.to_thread(
            task_generator.generate_tasks,
            prd_markdown=state.prd_markdown,
            project_name=state.project_name,
            llm=state.llm_instance,
        )
        if not raw_output:
            raise ValueError("Task decomposition LLM call returned empty output.")
        state.task_decomposition_raw = raw_output
        logger.info(f"[{state.project_name}] Raw task decomposition generated.")
        state.status_updates.append(f"{datetime.datetime.now()}: Raw task list generated by LLM.")
    except Exception as e:
        error_msg = f"Error invoking LLM for Task Decomposition: {e}"
        logger.error(f"[{state.project_name}] {error_msg}", exc_info=True)
        state.errors.append(error_msg)
        state.status_updates.append(f"{datetime.datetime.now()}: Task Decomposition LLM call FAILED.")
        return False

    # --- Parse Raw Output ---
    try:
        logger.info(f"[{state.project_name}] Parsing task decomposition output...")
        # Assuming task_decomposer.decompose_tasks is synchronous
        f_struct, t_dict = await asyncio.to_thread(
            task_decomposer.decompose_tasks, state.task_decomposition_raw
        )

        # --- MORE DETAILED DEBUGGING ---
        logger.debug(f"[{state.project_name}] Type of parsed result (t_dict): {type(t_dict)}")
        if isinstance(t_dict, dict):
             logger.debug(f"[{state.project_name}] Keys in parsed dict (t_dict): {list(t_dict.keys())}")
             logger.debug(f"[{state.project_name}] Is 'task_checklist' key present? {'task_checklist' in t_dict}")
             # Try accessing it directly and log type if present
             if 'task_checklist' in t_dict:
                  logger.debug(f"[{state.project_name}] Type of t_dict['task_checklist']: {type(t_dict['task_checklist'])}")
             else:
                  logger.debug(f"[{state.project_name}] 'task_checklist' key confirmed NOT in t_dict.keys()")

        # Log the content again just before the check for comparison
        logger.debug(f"[{state.project_name}] Content of t_dict JUST BEFORE check: {t_dict}")
        # --------------------------------

        # --- Original Validation ---
        if not isinstance(t_dict, dict) or "task_checklist" not in t_dict:
             logger.error(f"[{state.project_name}] Parsed task dictionary is invalid or missing 'task_checklist'. Failing check.") # Modified log
             # Log content again right here when failing
             logger.error(f"[{state.project_name}] Content causing failure: {t_dict}")
             raise ValueError("Parsed task dictionary is invalid or missing 'task_checklist'.") # Keep original error type
        # ------------------------
        if not isinstance(t_dict["task_checklist"], list):
             logger.error(f"[{state.project_name}] 'task_checklist' in parsed dictionary is not a list. Type: {type(t_dict['task_checklist'])}")
             raise ValueError("'task_checklist' in parsed dictionary is not a list.")

        state.file_structure_str = f_struct
        state.tasks_dict = t_dict
        task_count = len(state.tasks_dict.get("task_checklist", []))
        logger.info(f"[{state.project_name}] Task decomposition parsed successfully. Found {task_count} tasks.")
        state.status_updates.append(f"{datetime.datetime.now()}: Task decomposition parsed ({task_count} tasks).")
        return True
    except Exception as e:
        error_msg = f"Error parsing Task Decomposition output: {e}"
        logger.error(f"[{state.project_name}] {error_msg}", exc_info=True)
        # Log snippet of raw output on parsing error
        logger.error(f"--- Raw Output Snippet on Parsing Error ---\n{state.task_decomposition_raw[:1000]}...\n---")
        state.errors.append(error_msg)
        state.status_updates.append(f"{datetime.datetime.now()}: Task Decomposition parsing FAILED.")
        return False

async def run_code_generation_step(state: ProjectWorkflowState) -> bool:
    """Generates code for each file in the task list."""
    if not state.tasks_dict or "task_checklist" not in state.tasks_dict:
        state.errors.append("Cannot generate code without a valid task list.")
        return False
    state.current_step = "Generating Code"
    logger.info(f"[{state.project_name}] Starting Step: {state.current_step}")
    state.status_updates.append(f"{datetime.datetime.now()}: Starting code generation...")

    task_checklist = state.tasks_dict["task_checklist"]
    if not task_checklist:
         logger.warning(f"[{state.project_name}] Task checklist is empty. Skipping code generation.")
         state.status_updates.append(f"{datetime.datetime.now()}: Code generation skipped (empty task list).")
         return True # Not an error if list is empty

    total_tasks = len(task_checklist)
    successful_gens = 0
    all_files_list = [task.get("file_path", "").lstrip('/') for task in task_checklist if task.get("file_path")]
    overall_context = task_checklist[0].get("task", {}).get("description", "Context unavailable.")

    for i, task in enumerate(task_checklist):
        file_path_str = task.get("file_path", "").lstrip('/')
        task_detail = task.get("task", {})
        task_desc = task_detail.get("description", "No description")
        tech_spec = task_detail.get("technical_spec", {})
        requirements = task_detail.get("requirements", [])

        if not file_path_str:
            logger.warning(f"[{state.project_name}] Skipping task {i+1}/{total_tasks} due to missing file path.")
            continue

        logger.info(f"[{state.project_name}] Generating code for: {file_path_str} ({i+1}/{total_tasks})")
        state.status_updates.append(f"{datetime.datetime.now()}: Generating code for {file_path_str}...")

        try:
            # --- Run individual code generation (assuming sync) ---
            # If code_generator.generate_code becomes async, remove to_thread
            generated_code = await asyncio.to_thread(
                code_generator.generate_code,
                file_path=file_path_str,
                task_description=task_desc,
                llm=state.llm_instance,
                overall_project_context=overall_context,
                adjacent_files_list=all_files_list,
                technical_spec=tech_spec,
                requirements=requirements,
                file_purpose=task_desc # Pass task_desc as file_purpose
            )
            # ---------------------------------------------------

            if generated_code is not None:
                state.generated_files[file_path_str] = generated_code
                successful_gens += 1
                logger.debug(f"[{state.project_name}] Successfully generated code for {file_path_str}.")
                state.status_updates.append(f"{datetime.datetime.now()}: Code generated for {file_path_str}.")
            else:
                # Placeholder generation handled within generate_code, log warning
                logger.warning(f"[{state.project_name}] Code generation returned None or failed for {file_path_str}. Placeholder might be used.")
                state.generated_files[file_path_str] = f"# Code generation failed for {file_path_str}\n# Task: {task_desc}" # Basic placeholder
                state.errors.append(f"Code generation failed for {file_path_str}")
                state.status_updates.append(f"{datetime.datetime.now()}: Code generation FAILED for {file_path_str}.")


        except Exception as e:
            error_msg = f"Error generating code for {file_path_str}: {e}"
            logger.error(f"[{state.project_name}] {error_msg}", exc_info=True)
            state.errors.append(error_msg)
            state.generated_files[file_path_str] = f"# Error during code generation: {e}\n# Task: {task_desc}\n"
            state.status_updates.append(f"{datetime.datetime.now()}: Code generation ERROR for {file_path_str}.")
        # Optional small delay between LLM calls if needed
        # await asyncio.sleep(0.1)

    logger.info(f"[{state.project_name}] Code generation step finished. {successful_gens}/{total_tasks} files generated successfully.")
    state.status_updates.append(f"{datetime.datetime.now()}: Code generation finished ({successful_gens}/{total_tasks} successful).")
    # Consider returning False only if a critical number of generations fail? For now, return True if loop completes.
    return True

async def run_test_generation_step(state: ProjectWorkflowState) -> bool:
    """Generates test files for eligible source files."""
    if not state.generated_files:
        logger.warning(f"[{state.project_name}] No source files generated. Skipping test generation.")
        state.status_updates.append(f"{datetime.datetime.now()}: Test generation skipped (no source files).")
        return True # Not an error

    state.current_step = "Generating Tests"
    logger.info(f"[{state.project_name}] Starting Step: {state.current_step}")
    state.status_updates.append(f"{datetime.datetime.now()}: Starting test generation...")

    # --- Identify Testable Files (Logic from original main) ---
    testable_source_files = {
        fp: content for fp, content in state.generated_files.items()
        if content and isinstance(content, str) and not fp.endswith('__init__.py') and
           ((fp.startswith("backend/src/") and fp.endswith(".py") and not any(ex in fp for ex in ["__init__", "config.", "settings.", "wsgi.", "asgi."])) or
            (fp.startswith("frontend/") and (fp.endswith(".ts") or fp.endswith(".tsx")) and not any(ex in fp for ex in ["/api/", "/pages/", "/app/", ".config.", ".d.", "types.", "layout.", "page.", "route.", "global.", "main.", "app."]) and not Path(fp).name.startswith(('_', '.'))))
    }
    # ------------------------------------------------------

    if not testable_source_files:
        logger.info(f"[{state.project_name}] No testable source files identified. Skipping test generation.")
        state.status_updates.append(f"{datetime.datetime.now()}: Test generation skipped (no testable files found).")
        return True

    total_testable = len(testable_source_files)
    successful_gens = 0
    logger.info(f"[{state.project_name}] Identified {total_testable} testable source files.")

    for i, (src_path, src_content) in enumerate(testable_source_files.items()):
        test_framework = ""
        test_path = ""
        p_src = Path(src_path)

        # Determine test path and framework
        try:
            if src_path.startswith(("backend/src/", "src/")): # Adjust prefix if needed
                 rel_path = p_src.relative_to(next(p for p in p_src.parents if p.name == 'src'))
                 test_path = f"tests/{rel_path.parent}/test_{rel_path.name}" # Simplified path
                 test_framework = "pytest"
            elif src_path.startswith("frontend/"):
                 rel_path = p_src.relative_to("frontend")
                 test_path = f"frontend/tests/{rel_path.parent}/{p_src.stem}.test{p_src.suffix}"
                 test_framework = "jest"
            else: # Handle other potential structures or root files
                 test_path = f"tests/test_{p_src.name}"
                 test_framework = "pytest" # Default assumption

            if not test_path: continue # Skip if path logic fails

        except ValueError as ve:
            logger.warning(f"[{state.project_name}] Path resolution failed for test generation on {src_path}: {ve}. Skipping.")
            continue

        logger.info(f"[{state.project_name}] Generating test for: {src_path} -> {test_path} ({i+1}/{total_testable})")
        state.status_updates.append(f"{datetime.datetime.now()}: Generating test for {src_path}...")

        # Find original task spec for context
        original_task = next(
            (task for task in state.tasks_dict.get("task_checklist", [])
             if task.get("file_path", "").lstrip('/') == src_path), None
        )
        task_detail = original_task.get("task", {}) if original_task else {}

        try:
             # --- Run test generation (assuming sync) ---
             # If test_creator.generate_tests becomes async, remove to_thread
             generated_test = await asyncio.to_thread(
                 test_creator.generate_tests,
                 source_code=src_content,
                 source_file_path=src_path,
                 test_file_path=test_path,
                 test_framework=test_framework,
                 llm=state.llm_instance,
                 original_task=task_detail,
                 technical_spec=task_detail.get("technical_spec"),
                 requirements=task_detail.get("requirements")
                 # Pass adjacent_files_list if needed by test_creator?
             )
             # ------------------------------------------

             if generated_test:
                 state.generated_tests[test_path] = generated_test
                 successful_gens += 1
                 logger.debug(f"[{state.project_name}] Successfully generated test: {test_path}")
                 state.status_updates.append(f"{datetime.datetime.now()}: Test generated for {src_path}.")
             else:
                 logger.warning(f"[{state.project_name}] Test generation returned None for {src_path}. Placeholder might be used.")
                 state.generated_tests[test_path] = f"# Test generation failed for {src_path}" # Basic placeholder
                 state.errors.append(f"Test generation failed for {src_path}")
                 state.status_updates.append(f"{datetime.datetime.now()}: Test generation FAILED for {src_path}.")

        except Exception as e:
            error_msg = f"Error generating test for {src_path}: {e}"
            logger.error(f"[{state.project_name}] {error_msg}", exc_info=True)
            state.errors.append(error_msg)
            state.generated_tests[test_path] = f"# Error during test generation for {src_path}: {e}\n"
            state.status_updates.append(f"{datetime.datetime.now()}: Test generation ERROR for {src_path}.")

        # await asyncio.sleep(0.1) # Optional delay

    logger.info(f"[{state.project_name}] Test generation step finished. {successful_gens}/{total_testable} tests generated successfully.")
    state.status_updates.append(f"{datetime.datetime.now()}: Test generation finished ({successful_gens}/{total_testable} successful).")
    return True


async def save_files_step(state: ProjectWorkflowState) -> bool:
    """Saves all generated source files and test files."""
    if not state.project_output_dir:
        state.errors.append("Project output directory not set. Cannot save files.")
        return False

    state.current_step = "Saving Files"
    logger.info(f"[{state.project_name}] Starting Step: {state.current_step}")
    state.status_updates.append(f"{datetime.datetime.now()}: Saving generated files...")

    all_files_to_save = {**state.generated_files, **state.generated_tests}
    # Add PRD and structure file if they exist
    if state.prd_markdown: all_files_to_save["PRD.md"] = state.prd_markdown
    if state.file_structure_str: all_files_to_save["project_structure.txt"] = state.file_structure_str

    if not all_files_to_save:
        logger.warning(f"[{state.project_name}] No files to save.")
        state.status_updates.append(f"{datetime.datetime.now()}: File saving skipped (no files generated).")
        return True

    total_files = len(all_files_to_save)
    successful_saves = 0
    save_tasks = []

    logger.info(f"[{state.project_name}] Attempting to save {total_files} files to {state.project_output_dir}...")

    for relative_path, content in all_files_to_save.items():
        # Basic path safety check
        if relative_path.startswith("/") or ".." in Path(relative_path).parts:
            logger.warning(f"[{state.project_name}] Skipping potentially unsafe file path: {relative_path}")
            state.errors.append(f"Skipped potentially unsafe file path: {relative_path}")
            continue

        full_path = state.project_output_dir / relative_path
        # Create task for saving each file asynchronously
        save_tasks.append(_save_file_async(full_path, content))

    # Run save tasks concurrently
    results = await asyncio.gather(*save_tasks)
    successful_saves = sum(1 for res in results if res is True)

    logger.info(f"[{state.project_name}] File saving step finished. {successful_saves}/{len(save_tasks)} files saved successfully.")
    state.status_updates.append(f"{datetime.datetime.now()}: File saving finished ({successful_saves}/{len(save_tasks)} successful).")

    if successful_saves != len(save_tasks):
         state.errors.append(f"Failed to save {len(save_tasks) - successful_saves} file(s).")
         return False # Indicate partial failure
    return True


# --- Orchestrator Function ---

async def run_project_tests_step(state: ProjectWorkflowState) -> bool:
    """Executes tests using the pre-created virtual environment."""
    # Check if venv setup was successful first
    if not state.venv_python_path:
        logger.warning(f"[{state.project_name}] Venv python path not available (venv setup likely failed or skipped). Skipping test execution.")
        state.status_updates.append(f"{datetime.datetime.now()}: Test execution skipped (venv unavailable).")
        state.tests_passed = None # Indicate tests didn't run
        # Returning True here because the failure wasn't in *this* step, but earlier.
        # The orchestrator handles the overall success state based on venv failure.
        return True

    # Check if project directory exists (sanity check)
    if not state.project_output_dir or not state.project_output_dir.is_dir():
        logger.warning(f"[{state.project_name}] Project directory not available ({state.project_output_dir}). Skipping test execution.")
        state.status_updates.append(f"{datetime.datetime.now()}: Test execution skipped (directory missing).")
        state.tests_passed = None
        return True # Directory missing might be due to earlier save errors

    state.current_step = "Executing Tests"
    logger.info(f"[{state.project_name}] Starting Step: {state.current_step} using Python: {state.venv_python_path}")
    state.status_updates.append(f"{datetime.datetime.now()}: Starting test execution...")

    try:
        # Pass the project dir and the venv python executable path
        tests_passed, test_log = await run_project_tests(
            project_dir=state.project_output_dir,
            venv_python_executable=state.venv_python_path
        )
        state.tests_passed = tests_passed
        state.test_results_summary = test_log # Store the detailed log
        logger.info(f"[{state.project_name}] Test execution finished. Passed: {tests_passed}")
        state.status_updates.append(f"{datetime.datetime.now()}: Test execution finished (Passed: {tests_passed}).")
        if not tests_passed:
             state.errors.append("Project tests failed or encountered errors during execution.")
             # Return False to indicate this specific step had issues (tests failed)
             # The orchestrator can decide if this constitutes overall failure.
             return False
        return True

    except Exception as e:
        error_msg = f"Error during test execution step: {e}"
        logger.error(f"[{state.project_name}] {error_msg}", exc_info=True)
        state.errors.append(error_msg)
        state.test_results_summary = f"ERROR during test execution:\n{traceback.format_exc()}"
        state.tests_passed = False
        state.status_updates.append(f"{datetime.datetime.now()}: Test execution step encountered an ERROR.")
        return False # Treat unexpected error during test run as failure


# --- Orchestrator Function (Updated) ---

async def execute_project_generation_workflow(request: str) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Orchestrates the project generation by calling steps sequentially
    and managing the workflow state. Yields status updates.
    Includes early venv creation and test execution.
    """
    start_overall_time = time.time()
    yield {"type": "status", "message": "Workflow starting...", "step": "Initialization"}
    logger.info(f"Starting project generation workflow for request: '{request[:100]}...'" )

    # --- Resolve Output Directory --- # <<< Moved resolution here
    output_base_str = getattr(app_config, "PROJECT_GENERATOR_OUTPUT_BASE_DIR_STR", os.getenv("DEFAULT_OUTPUT_BASE"))
    if not output_base_str:
        error_msg = "Error: Project output base directory is not configured (DEFAULT_OUTPUT_BASE env var or config)."
        logger.critical(error_msg)
        yield {"type": "error", "message": error_msg, "step": "Initialization"}
        return
    try:
        project_output_base_dir = Path(output_base_str).resolve()
        ensure_directory_exists(project_output_base_dir)
        logger.info(f"Project Generator Output Base Directory: {project_output_base_dir}")
    except Exception as e:
        error_msg = f"Error resolving or creating project output base directory '{output_base_str}': {e}"
        logger.critical(error_msg, exc_info=True)
        yield {"type": "error", "message": error_msg, "step": "Initialization"}
        return
    # --------------------------------

    try:
        llm = get_llm()
    except Exception as e:
        error_msg = f"Error: Failed to initialize Language Model - {e}"
        logger.critical(error_msg, exc_info=True)
        yield {"type": "error", "message": error_msg, "step": "Initialization"}
        return

    state = ProjectWorkflowState(request=request, llm_instance=llm)

    # Define steps (excluding venv creation/awaiting, handled explicitly)
    generation_steps = [
        generate_prd_step,
        generate_tasks_step,
        run_code_generation_step,
        run_test_generation_step,
        save_files_step,
        # test execution step is handled after explicit venv await
    ]

    final_success = True
    for step_func in generation_steps:
        step_name = step_func.__name__.replace('_step', '').replace('_', ' ').title()
        yield {"type": "status", "message": f"Starting step: {step_name}", "step": step_name}
        
        # Call step function with appropriate arguments
        if step_func is generate_prd_step:
            step_success = await step_func(state, project_output_base_dir)
        else:
            step_success = await step_func(state)
        
        yield {"type": "progress", "step": step_name, "success": step_success}

        # --- Start Venv Creation Early --- # <<< Added
        if step_func is generate_prd_step and step_success and state.project_output_dir:
            yield {"type": "status", "message": "Starting virtual environment creation in background...", "step": "Venv Setup"}
            state.venv_creation_task = asyncio.create_task(
                _create_and_activate_venv(state.project_output_dir),
                name=f"VenvCreation-{state.project_name}" # Optional: Name the task
            )
        # ------------------------------------

        if not step_success:
            logger.error(f"[{state.project_name}] Workflow step '{step_name}' failed. Halting further generation.")
            final_success = False
            state.errors.append(f"Step '{step_name}' failed.")
            yield {"type": "error", "message": f"Workflow halted due to failure in step: {step_name}", "step": step_name}
            break # Halt on first critical failure

    # --- Await Venv Creation & Run Tests (if generation succeeded so far) --- # <<< Added
    if final_success and state.venv_creation_task:
        yield {"type": "status", "message": "Waiting for virtual environment setup to complete...", "step": "Venv Setup"}
        try:
            venv_python = await state.venv_creation_task
            if venv_python:
                state.venv_python_path = venv_python
                logger.info(f"[{state.project_name}] Virtual environment setup complete. Python: {venv_python}")
                yield {"type": "status", "message": f"Virtual environment ready: {venv_python}", "step": "Venv Setup"}

                # Now run the test execution step
                step_name = run_project_tests_step.__name__.replace('_step', '').replace('_', ' ').title()
                yield {"type": "status", "message": f"Starting step: {step_name}", "step": step_name}
                test_step_success = await run_project_tests_step(state)
                yield {"type": "progress", "step": step_name, "success": test_step_success}
                if not test_step_success:
                     # Decide if test failure is a final failure
                     # final_success = False # Uncomment if test failure should mark overall failure
                     logger.warning(f"[{state.project_name}] Test execution step failed or tests did not pass.")
                     # Yield a specific warning for test failure?
                     yield {"type": "warning", "message": "Test execution step failed or tests did not pass.", "step": step_name}
            else:
                logger.error(f"[{state.project_name}] Virtual environment creation failed. Skipping test execution.")
                state.errors.append("Virtual environment creation failed.")
                yield {"type": "error", "message": "Virtual environment setup failed. Skipping tests.", "step": "Venv Setup"}
                # final_success = False # Treat venv failure as overall failure?

        except asyncio.CancelledError:
            logger.warning(f"[{state.project_name}] Venv creation task was cancelled.")
            state.errors.append("Venv creation cancelled.")
            yield {"type": "warning", "message": "Venv creation task was cancelled. Skipping tests.", "step": "Venv Setup"}
            # final_success = False
        except Exception as e:
            error_msg = f"Error awaiting virtual environment creation: {e}"
            logger.error(f"[{state.project_name}] {error_msg}", exc_info=True)
            state.errors.append(error_msg)
            yield {"type": "error", "message": f"Error during venv setup: {e}. Skipping tests.", "step": "Venv Setup"}
            # final_success = False
    elif final_success:
         yield {"type": "warning", "message": "Venv creation task not started (likely PRD step failed or no output dir). Skipping tests.", "step": "Venv Setup"}
    # -------------------------------------------------------------------------

    # --- Finalize --- # <<< Updated
    state.is_complete = True
    end_overall_time = time.time()
    total_time = end_overall_time - start_overall_time

    status_prefix = "Success" if final_success and not state.errors else "Failed"
    if final_success and state.errors and not any("failed" in e.lower() for e in state.errors):
        status_prefix = "Completed with warnings"

    test_suffix = ""
    if state.tests_passed is True:
        test_suffix = "\nTests Passed: Yes"
    elif state.tests_passed is False:
        test_suffix = "\nTests Passed: No"
        if status_prefix == "Success": # Downgrade success if tests failed
            status_prefix = "Completed with Test Failures"
    elif state.venv_python_path: # Tests were expected to run
         test_suffix = "\nTests Passed: Unknown (Error during execution)"
    else: # Tests were skipped
         test_suffix = "\nTests: Skipped"

    error_summary = "; ".join(state.errors)
    final_message = (
        f"{status_prefix}: Project '{state.project_name}' generation finished in {total_time:.2f} seconds.\n"
        f"Output: {str(state.project_output_dir.resolve()) if state.project_output_dir else 'N/A'}"
        f"{test_suffix}"
    )
    if error_summary:
         final_message += f"\nIssues: {error_summary}"

    state.final_message = final_message # Store for potential future access

    # Yield final status
    yield {
        "type": "final_status",
        "status": status_prefix,
        "message": final_message,
        "project_name": state.project_name,
        "output_dir": str(state.project_output_dir.resolve()) if state.project_output_dir else None,
        "tests_passed": state.tests_passed,
        "errors": state.errors,
        "total_time": total_time
    }

    if final_success and not state.errors:
        logger.info(f"[{state.project_name}] Workflow completed successfully. {final_message}")
    else:
        logger.error(f"[{state.project_name}] Workflow finished with issues. {final_message}")

    # Optionally log full test results summary if needed
    # if state.test_results_summary:
    #     logger.info(f"[{state.project_name}] Full Test Results:\n{state.test_results_summary}")
