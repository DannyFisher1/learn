# backend/app/api/jobs.py

import logging
from fastapi import APIRouter, HTTPException, status, Depends, Body
from typing import Any, Dict, Optional, List, Union
from pydantic import BaseModel

# App imports
from app import schemas # Import job schemas
from app.services import jobs_service # Import our new service functions
from app.utils import get_logger
from app.errors import JobNotFoundError

logger = get_logger(__name__)
router = APIRouter(prefix="/jobs", tags=["Background Jobs"])

# --- Dependency for pagination ---
class PaginationParams:
    def __init__(self, offset: int = 0, limit: int = 50):
        self.offset = offset
        self.limit = limit

# --- API Endpoints ---

@router.post(
    "/{task_type}/start",
    response_model=schemas.StartJobResponse,
    status_code=status.HTTP_202_ACCEPTED, # Use 202 for accepted background tasks
    summary="Start a Background Job",
    description="Initiates a background job of the specified type (e.g., 'deep_research')."
)
async def start_background_job(
    task_type: str, # Get type from path
    # Use Body(...) for generic payload, or define specific Pydantic models per task type
    # input_params: Dict[str, Any] = Body(...)
    # Example using specific model:
    input_params: Union[schemas.StartDeepResearchPayload, Dict[str, Any]] = Body(...)
):
    """
    Starts a background task.

    - **task_type**: The type of job to start (e.g., `deep_research`, `project_generation`).
    - **Request Body**: Contains parameters specific to the `task_type`.
        - For `deep_research`: requires `topic`, optionally `depth`, `max_sources`, etc.
        - For `project_generation`: requires `request` field containing the project details.
    """
    logger.info(f"Received request to start job of type '{task_type}'")

    # Basic validation or dispatch based on task_type
    # More robust validation could happen in the service layer or via specific Pydantic models
    valid_task_types = ["deep_research", "project_generation"] # Add other valid types
    if task_type not in valid_task_types:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid task type specified: {task_type}")

    # If using specific Pydantic models, FastAPI handles validation
    # If using Dict[str, Any], perform basic validation here if needed
    input_data_dict = {}
    if isinstance(input_params, BaseModel): # Handle Pydantic model case
        input_data_dict = input_params.model_dump()
    elif isinstance(input_params, dict):
         input_data_dict = input_params
    else:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input parameters format.")


    try:
        job_id = await jobs_service.start_job(task_type, input_data_dict)
        return schemas.StartJobResponse(job_id=job_id)
    except ValueError as ve: # Catch unknown task type from service
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except ConnectionError as ce:
         logger.error(f"Job Store connection error during start: {ce}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Job store unavailable.")
    except Exception as e:
        logger.error(f"Failed to start job type '{task_type}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to start job.")


@router.get(
    "/status/{job_id}",
    response_model=schemas.JobStatusResponse,
    summary="Get Job Status by ID",
    description="Retrieves the current status and metadata for a specific job."
)
async def get_job_status_endpoint(job_id: str):
    """
    Retrieves the status for a background job.

    - **job_id**: The unique identifier of the job.
    """
    logger.info(f"Request received for status of Job ID: {job_id}")
    job_data = await jobs_service.get_job_status_service(job_id)
    if not job_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    # Pydantic model validation happens automatically on return
    return job_data


@router.get(
    "/result/{job_id}",
    response_model=schemas.JobResultResponse,
    summary="Get Job Result by ID",
    description="Retrieves the final result for a completed job."
)
async def get_job_result_endpoint(job_id: str):
    """
    Retrieves the result for a completed background job.

    - **job_id**: The unique identifier of the job.
    """
    logger.info(f"Request received for result of Job ID: {job_id}")
    job_data = await jobs_service.get_job_result_service(job_id)
    if not job_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")

    if job_data.get("status") != schemas.JOB_STATUS_COMPLETED:
         # Return status info instead of raising error if job is not complete/failed?
         # Or raise 409 Conflict / 400 Bad Request? Let's return status for now.
          logger.warning(f"Result requested for job '{job_id}' but status is {job_data.get('status')}")
          # Return status info using the result schema (result_data will be null)
          return job_data
          # raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job '{job_id}' is not yet completed (status: {job_data.get('status')}).")

    # Pydantic model validation happens automatically on return
    return job_data


@router.post(
    "/cancel/{job_id}",
    response_model=schemas.CancelJobResponse,
    summary="Request Job Cancellation",
    description="Attempts to cancel a PENDING or RUNNING job. Actual termination depends on task queue support."
)
async def cancel_job_endpoint(job_id: str):
    """
    Requests cancellation of a background job.

    - **job_id**: The unique identifier of the job.
    """
    logger.info(f"Request received to cancel Job ID: {job_id}")
    success, message = await jobs_service.cancel_job_service(job_id)
    status_msg = "CANCEL_REQUESTED" if success else "CANCEL_FAILED"
    if "not found" in message.lower(): status_code = status.HTTP_404_NOT_FOUND
    elif "cannot be canceled" in message.lower(): status_code = status.HTTP_409_CONFLICT
    elif not success: status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else: status_code = status.HTTP_200_OK

    if not success:
        raise HTTPException(status_code=status_code, detail=message)

    return schemas.CancelJobResponse(job_id=job_id, status=status_msg, message=message)


@router.get(
    "/active",
    response_model=schemas.JobListResponse,
    summary="List Active Jobs",
    description="Retrieves a list of jobs currently in PENDING or RUNNING state."
)
async def list_active_jobs_endpoint(pagination: PaginationParams = Depends()):
    """
    Lists active background jobs. Supports pagination via query parameters:
    - `offset`: Number of jobs to skip (default 0).
    - `limit`: Maximum number of jobs to return (default 50).
    """
    # logger.info(f"Request received to list active jobs (limit={pagination.limit}, offset={pagination.offset})")
    jobs_list, total = await jobs_service.get_active_jobs_service(limit=pagination.limit, offset=pagination.offset)
    return schemas.JobListResponse(jobs=jobs_list, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get(
    "/history",
    response_model=schemas.JobListResponse,
    summary="List Job History",
    description="Retrieves a list of COMPLETED, FAILED, or CANCELED jobs."
)
async def list_job_history_endpoint(pagination: PaginationParams = Depends()):
    """
    Lists historical background jobs. Supports pagination via query parameters:
    - `offset`: Number of jobs to skip (default 0).
    - `limit`: Maximum number of jobs to return (default 50).
    """
    logger.info(f"Request received for job history (limit={pagination.limit}, offset={pagination.offset})")
    jobs_list, total = await jobs_service.get_job_history_service(limit=pagination.limit, offset=pagination.offset)
    return schemas.JobListResponse(jobs=jobs_list, total=total, limit=pagination.limit, offset=pagination.offset)

@router.delete(
    "/delete/{job_id}",
    status_code=status.HTTP_200_OK, # Or 204 No Content if not returning a body on success
    summary="Permanently Delete Job by ID",
    description="Permanently deletes a job record from the system (Redis). Use with caution."
)
async def permanently_delete_job_endpoint(job_id: str):
    """
    Permanently deletes a job from the system.

    - **job_id**: The unique identifier of the job to delete.
    """
    logger.info(f"API request received to PERMANENTLY DELETE Job ID: {job_id}")
    
    # Optional: Add authentication/authorization checks here for production
    # if not current_user_is_admin():
    #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete jobs.")

    deleted = await jobs_service.delete_job_permanently_service(job_id)
    
    if not deleted:
        # Check if it was not found vs. other deletion failure
        # For simplicity, we'll return 404 if delete_job_permanently_service returns false,
        # assuming it means the job wasn't there or a Redis error occurred during the check.
        # A more granular error could be returned from the service if needed.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found or could not be deleted.")
    
    return {"job_id": job_id, "message": "Job permanently deleted successfully."}