# app/api/chat.py

import logging
from fastapi import APIRouter, HTTPException, status, Depends, Request
from sse_starlette.sse import EventSourceResponse # Import for SSE
import json

# App imports
from app import schemas
from app.services import chat_service # Import the specific service
from app.services.chat_service import AgentNotReadyError, handle_chat_request_stream
from app.utils import get_logger

logger = get_logger(__name__)
# Consider adding a prefix like "/chat" if you have many top-level routers
# router = APIRouter(prefix="/chat", tags=["Chat Agent"])
router = APIRouter(tags=["Chat Agent"])


@router.post("/ask", response_model=schemas.AskResponse)
async def ask_agent_endpoint(request: schemas.AskRequest):
    """
    Endpoint to ask a question, optionally filtering by filename or tag.
    Delegates processing to the chat service.
    Returns the agent's final answer and intermediate steps.
    """
    # --- Input Validation ---
    if not request.question or not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )

    # --- Call Service Layer ---
    # The 'request' object now includes 'tag_filter' (as Optional[str])
    # based on the updated AskRequest schema.
    try:
        # Log the full request, including the new filter if present
        logger.debug(f"Received ask request: {request.model_dump(exclude_none=True)}")
        # Delegate the core logic to the chat service, passing the whole request
        response_data = await chat_service.handle_chat_request(request)
        return response_data

    # --- Error Handling (No changes needed here) ---
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
async def ask_agent_streaming_endpoint(request_body: schemas.AskRequest, request: Request):
    """
    Endpoint to ask a question and stream the response using Server-Sent Events.
    """
    # --- Input Validation (same as /ask) ---
    if not request_body.question or not request_body.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )

    logger.debug(f"Received ask-stream request: {request_body.model_dump(exclude_none=True)}")

    # --- Call Streaming Service Layer ---
    try:
        # Get the async generator from the service
        event_generator = handle_chat_request_stream(request_body)
        
        # Use EventSourceResponse to stream the generator's output
        return EventSourceResponse(event_generator)

    except AgentNotReadyError as anre:
        # For SSE, we can't easily raise HTTPException after starting the stream.
        # The service function now yields error events, but handle bootstrap error here.
        logger.error(f"Agent service unavailable for streaming: {anre}")
        # Return an immediate error response before streaming starts
        # Note: This error handling might need refinement depending on how
        # you want to signal errors *during* an established stream.
        # The service currently yields error events for that.
        return EventSourceResponse([{"event": "error", "data": json.dumps({"error": f"Agent service unavailable: {anre}"})}])

    except Exception as e:
        logger.error(f"Unexpected error setting up /ask-stream: {e}", exc_info=True)
        # Return an immediate error response
        return EventSourceResponse([{"event": "error", "data": json.dumps({"error": f"An unexpected error occurred during stream setup: {e}"})}])