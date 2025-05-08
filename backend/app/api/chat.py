# app/api/chat.py

import logging
# --- Remove Depends for BackgroundTasks, keep BackgroundTasks ---
from fastapi import APIRouter, HTTPException, status, Depends, Request, BackgroundTasks
# ----------------------------------------------------------------
from sse_starlette.sse import EventSourceResponse
import json

# App imports
from app import schemas
from app.services import chat_service
from app.services.chat_service import AgentNotReadyError # Removed handle_chat_request_stream import, call via service module
from app.utils import get_logger # Added this import

logger = get_logger(__name__)
router = APIRouter(tags=["Chat Agent"])


@router.post("/ask", response_model=schemas.AskResponse)
async def ask_agent_endpoint(
    request: schemas.AskRequest,
    # --- FIX: Remove Depends() here ---
    background_tasks: BackgroundTasks
    # ----------------------------------
):
    """
    Endpoint to ask a question, optionally filtering by filename or tag.
    Delegates processing to the chat service, passing BackgroundTasks for
    potential long-running operations like project generation.
    Returns the agent's final answer or a job start message.
    """
    # --- Input Validation (No change) ---
    if not request.question or not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )

    # --- Call Service Layer ---
    try:
        logger.debug(f"Received ask request: {request.model_dump(exclude_none=True)}")
        # Pass background_tasks to the service function
        response_data = await chat_service.handle_chat_request(request, background_tasks)
        return response_data

    # --- Error Handling (No change) ---
    except AgentNotReadyError as anre:
        logger.error(f"Agent service unavailable: {anre}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Processing service is not ready: {anre}"
        )
    except ValueError as ve:
        logger.warning(f"Bad request processed by chat service: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except RuntimeError as rte:
        logger.error(f"Runtime error invoking agent via chat service: {rte}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while processing your request: {rte}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in /ask endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred."
        )

@router.post("/ask-stream")
async def ask_agent_streaming_endpoint(
    request_body: schemas.AskRequest,
    # --- FIX: Remove Depends() here ---
    background_tasks: BackgroundTasks
    # ----------------------------------
):
    """
    Endpoint to ask a question and stream the response using Server-Sent Events.
    Passes BackgroundTasks to the service for potential long-running operations.
    """
    # --- Input Validation (No change) ---
    if not request_body.question or not request_body.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )

    logger.debug(f"Received ask-stream request: {request_body.model_dump(exclude_none=True)}")

    # --- Call Streaming Service Layer ---
    try:
        # Fix: Remove 'await' keyword since handle_chat_request_stream returns an async generator
        event_generator = chat_service.handle_chat_request_stream(request_body, background_tasks)

        # Use EventSourceResponse to stream the generator's output
        return EventSourceResponse(event_generator)

    # --- Error Handling (No change) ---
    except AgentNotReadyError as anre:
        logger.error(f"Agent service unavailable for streaming: {anre}")
        return EventSourceResponse([{"event": "error", "data": json.dumps({"error": f"Agent service unavailable: {anre}"})}])
    except Exception as e:
        logger.error(f"Unexpected error setting up /ask-stream: {e}", exc_info=True)
        return EventSourceResponse([{"event": "error", "data": json.dumps({"error": f"An unexpected error occurred during stream setup: {e}"})}])