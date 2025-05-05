# app/api/jobs.py

import logging
from fastapi import APIRouter, HTTPException, status, Depends
from typing import Any, Dict

# App imports
from app import schemas # Import schemas, including the new JobStatusResponse
# Import the function to get status (which accesses the in-memory store)
from app.services.chat_service import get_job_status
from app.utils import get_logger

logger = get_logger(__name__)
# Define the router for job-related endpoints
router = APIRouter(prefix="/jobs", tags=["Background Jobs"])


@router.get(
    "/{job_id}",
    response_model=schemas.JobStatusResponse, # Use the defined schema
    summary="Get Background Job Status",
    description="Retrieves the current status and result (if available) for a background job initiated by certain API calls (like project generation). Uses an in-memory store (development only)."
)
async def get_job_status_endpoint(job_id: str):
    """
    Retrieves the status and result (if available) for a background job
    identified by its unique Job ID.

    - **job_id**: The unique identifier for the job returned when the background task was initiated.
    """
    logger.info(f"Request received for status of Job ID: {job_id}")

    # --- Get status from the service layer's helper function ---
    # This function currently reads directly from the global _background_jobs dict
    job_data = get_job_status(job_id)
    # -----------------------------------------------------------

    if not job_data:
        logger.warning(f"Job ID not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found."
        )

    logger.info(f"Returning status for Job ID {job_id}: {job_data.get('status')}")

    # --- Prepare response using the schema ---
    # The get_job_status function returns the dictionary directly from _background_jobs.
    # We pass this dictionary to the Pydantic model for validation and serialization.
    try:
        # Add job_id to the response data explicitly as it might not be stored within the dict value
        response_data = {**job_data, "job_id": job_id}
        return schemas.JobStatusResponse(**response_data)
    except Exception as e:
        # Handle potential errors during Pydantic model creation (e.g., type mismatch)
        logger.error(f"Error creating JobStatusResponse for job {job_id}: Data={job_data}, Error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while formatting job status."
        )