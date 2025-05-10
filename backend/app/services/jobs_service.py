# backend/app/services/jobs_service.py

import logging
import time
import uuid
import json
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, Union, List, Tuple

# App imports
from app.core.jobs.store import RedisJobStore, get_job_store_instance # Import class and getter
from app.utils import get_logger
from app.errors import JobExecutionError # Import custom error
from app.schemas import JOB_STATUS_RUNNING, JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELED, JOB_STATUS_PENDING # Import statuses

# --- Import ACTUAL Workflows ---
from app.core.workflows.deep_research import execute_deep_research_workflow # <<< Import the real workflow

logger = get_logger(__name__)

# --- Project Generator Import / Dummy ---
try:
    from app.core.project_generator.workflow import execute_project_generation_workflow
    PROJECT_GENERATOR_AVAILABLE = True
except ImportError:
    logger.warning("Project Generator workflow not found. 'generate_software_project' tool will be disabled.")
    PROJECT_GENERATOR_AVAILABLE = False
    async def execute_project_generation_workflow(request: str) -> AsyncGenerator[Dict[str, Any], None]:
         yield { "type": "final_status", "status": JOB_STATUS_FAILED, "message": "Error: Project Generator workflow component is not available.", "project_name": "Unavailable", "output_dir": None, "tests_passed": None, "errors": ["Project Generator workflow component is not available."], "total_time": 0 }
         await asyncio.sleep(0)
# ---

# --- Task Execution Wrappers ---

async def _run_actual_deep_research(job_id: str, job_store: RedisJobStore, input_params: Dict[str, Any]):
    """
    Wrapper to execute the deep research workflow and handle job updates.
    """
    logger.info(f"Job {job_id} (Deep Research): Task execution started with params {input_params}")
    start_time = time.time()
    await job_store.update_job(job_id, {"status": JOB_STATUS_RUNNING, "started_at": start_time}) # Mark as running immediately

    status = JOB_STATUS_RUNNING
    final_result_data = None
    error_message = None

    try:
        # Extract parameters for the workflow function
        topic = input_params.get("topic")
        if not topic:
            raise JobExecutionError("Missing required 'topic' parameter for deep research.")

        depth = input_params.get("depth", 2) # Default depth
        max_sources_per_query = input_params.get("max_sources_per_query", 5)
        max_total_sources = input_params.get("max_total_sources", 15)

        # Execute the actual workflow function
        final_result_data = await execute_deep_research_workflow(
            job_id=job_id,
            original_topic=topic,
            depth=depth,
            max_sources_per_query=max_sources_per_query,
            max_total_sources=max_total_sources
        )
        status = JOB_STATUS_COMPLETED
        logger.info(f"Job {job_id} (Deep Research): Workflow completed successfully.")

    except JobExecutionError as jee: # Catch specific workflow errors
        status = JOB_STATUS_FAILED
        error_message = str(jee)
        logger.error(f"Job {job_id} (Deep Research): Workflow failed: {error_message}", exc_info=False) # Log expected errors without full stack
    except Exception as e: # Catch unexpected errors
        status = JOB_STATUS_FAILED
        error_message = f"An unexpected error occurred during deep research: {str(e)}"
        logger.error(f"Job {job_id} (Deep Research): Unexpected error during workflow.", exc_info=True) # Log full stack for unexpected

    # Final job update in Redis
    end_time = time.time()
    duration = end_time - start_time

    # Check if the job was cancelled in the meantime
    current_job_data_before_final_update = await job_store.get_job(job_id)
    if current_job_data_before_final_update and current_job_data_before_final_update.get("status") == JOB_STATUS_CANCELED:
        logger.info(f"Job {job_id} (Deep Research): Task processing finished, but job was already CANCELED. Preserving CANCELED status.")
        # Optionally, we could update duration or other fields if needed, but for now, just log.
        # We might want to ensure 'ended_at' and 'duration_seconds' are recorded even for cancelled tasks if they ran.
        update_for_cancelled_ran_task = {
            "ended_at": end_time,
            "duration_seconds": round(duration, 2),
            "progress_message": "Task execution finished post-cancellation." # Or keep the "Cancellation requested."
        }
        await job_store.update_job(job_id, update_for_cancelled_ran_task) # This will NOT change status from CANCELED
    else:
        final_update_data = {
            "status": status,
            "ended_at": end_time,
            "duration_seconds": round(duration, 2),
            "result_data": final_result_data if status == JOB_STATUS_COMPLETED else None,
            "error_message": error_message if status == JOB_STATUS_FAILED else None,
            "progress_message": "Completed" if status == JOB_STATUS_COMPLETED else ("Failed" if status == JOB_STATUS_FAILED else "Unknown final state")
        }
        await job_store.update_job(job_id, final_update_data)
        logger.info(f"Job {job_id} (Deep Research): Final status '{status}' stored.")


async def _run_project_gen_task(job_id: str, job_store: RedisJobStore, project_request: str):
    """Runs the actual project generation workflow and updates job store."""
    logger.info(f"Job {job_id} (Project Gen): Task execution started...")
    start_time = time.time()
    await job_store.update_job(job_id, {"status": JOB_STATUS_RUNNING, "progress_message": "Initializing generator...", "started_at": start_time})

    status, result_message, output_path, error_details = JOB_STATUS_RUNNING, None, None, None
    final_result_dict = None # Store final result data
    try:
        if not PROJECT_GENERATOR_AVAILABLE:
             raise JobExecutionError("Project Generator workflow component is not available.")

        step_count = 0
        final_status_update = None
        async for update in execute_project_generation_workflow(project_request):
            step_count += 1
            progress_msg = update.get('message', f"Processing step {step_count}...")
            step_name = update.get('step', f"step_{step_count}")
            logger.info(f"Job [{job_id}] Workflow Status [{step_name}]: {progress_msg}")
            # Update progress message frequently
            await job_store.update_job(job_id, {"progress_message": f"[{step_name}] {progress_msg}"})

            if update.get("type") == "final_status":
                final_status_update = update; break # Capture final status

        if final_status_update:
            final_status_str = final_status_update.get("status", "Unknown").lower()
            result_message = final_status_update.get("message", "Completed.")
            errors_from_workflow = final_status_update.get("errors", [])
            if "success" in final_status_str or ("completed" in final_status_str and not errors_from_workflow):
                status = JOB_STATUS_COMPLETED
                output_path = final_status_update.get("output_dir")
                # Store structured result data
                final_result_dict = {"output_dir": output_path, "final_message": result_message}
            else:
                 status = JOB_STATUS_FAILED; error_details = result_message
                 if errors_from_workflow: error_details += f" | Workflow Errors: {'; '.join(errors_from_workflow)}"
        else:
             status = JOB_STATUS_FAILED; error_details = "Workflow finished without final status."

    except Exception as e:
        status = JOB_STATUS_FAILED; error_details = f"Unexpected error: {str(e)}"
        logger.error(f"Job [{job_id}] (Project Gen): Error during workflow.", exc_info=True)

    # Final job update in Redis
    end_time = time.time(); duration = end_time - start_time

    # Check if the job was cancelled in the meantime
    current_job_data_before_final_update = await job_store.get_job(job_id)
    if current_job_data_before_final_update and current_job_data_before_final_update.get("status") == JOB_STATUS_CANCELED:
        logger.info(f"Job {job_id} (Project Gen): Task processing finished, but job was already CANCELED. Preserving CANCELED status.")
        update_for_cancelled_ran_task = {
            "ended_at": end_time,
            "duration_seconds": round(duration, 2),
            "progress_message": "Task execution finished post-cancellation."
        }
        await job_store.update_job(job_id, update_for_cancelled_ran_task)
    else:
        final_update_data = {
            "status": status, "ended_at": end_time, "duration_seconds": round(duration, 2),
            "result_data": final_result_dict if status == JOB_STATUS_COMPLETED else None,
            "error_message": error_details if status == JOB_STATUS_FAILED else None,
            "progress_message": "Completed" if status == JOB_STATUS_COMPLETED else ("Failed" if status == JOB_STATUS_FAILED else "Unknown final state")
        }
        await job_store.update_job(job_id, final_update_data)
        logger.info(f"Job {job_id} (Project Gen): Finished with status '{status}'.")


# --- Job Management Service Functions ---

async def start_job(task_type: str, input_params: Dict[str, Any]) -> str:
    """
    Initializes a job in the store and queues it for background execution.
    Returns the Job ID.
    """
    job_store = get_job_store_instance()
    job_id = str(uuid.uuid4())
    # Ensure input_params are stored correctly (as JSON string)
    await job_store.initialize_job(job_id, task_type, input_params)

    # --- Queue Background Task ---
    # Replace asyncio.create_task with your actual task queue mechanism (Celery, Arq, etc.)
    logger.info(f"Queueing background task for Job ID: {job_id}, Task Type: {task_type}")
    if task_type == "deep_research":
        # Pass necessary arguments to the task wrapper
        asyncio.create_task(_run_actual_deep_research(job_id, job_store, input_params))
    elif task_type == "project_generation":
         # Project gen expects a single string usually
         project_request_str = json.dumps(input_params.get("request", input_params))
         asyncio.create_task(_run_project_gen_task(job_id, job_store, project_request_str))
    # Add elif for other task types (e.g., summarize_document)
    # elif task_type == "summarize_document":
    #      asyncio.create_task(_run_summarize_task(job_id, job_store, input_params))
    else:
         logger.error(f"Unknown task type '{task_type}' requested for Job ID: {job_id}. Marking as failed.")
         await job_store.update_job(job_id, {"status": JOB_STATUS_FAILED, "error_message": f"Unknown task type: {task_type}"})
         raise ValueError(f"Unknown task type: {task_type}")
    # -----------------------------

    return job_id

async def get_job_status_service(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves job status."""
    job_store = get_job_store_instance()
    return await job_store.get_job(job_id)

async def get_job_result_service(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves job result if completed/failed, otherwise returns current status info."""
    job_data = await get_job_status_service(job_id)
    return job_data # Return full data, API layer can decide what to expose

async def cancel_job_service(job_id: str) -> Tuple[bool, str]:
     """Requests job cancellation."""
     job_store = get_job_store_instance()
     return await job_store.cancel_job(job_id)

async def get_active_jobs_service(limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves active (PENDING, RUNNING) jobs."""
    job_store = get_job_store_instance()
    return await job_store.get_jobs_by_status([JOB_STATUS_PENDING, JOB_STATUS_RUNNING], limit, offset)

async def get_job_history_service(limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves completed, failed, or canceled jobs."""
    job_store = get_job_store_instance()
    return await job_store.get_jobs_by_status([JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELED], limit, offset)

async def delete_job_permanently_service(job_id: str) -> bool:
    """Deletes a job permanently from the job store."""
    job_store = get_job_store_instance()
    logger.info(f"Service request to permanently delete Job ID: {job_id}")
    deleted = await job_store.delete_job(job_id)
    if not deleted:
        # We might not raise JobNotFoundError here, as the store.delete_job already logs
        # and returns false if not found. The API layer can decide on 404.
        logger.warning(f"Job ID: {job_id} was not found or failed to delete in store.")
    return deleted