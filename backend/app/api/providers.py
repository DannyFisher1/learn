# app/api/providers.py

import logging
from fastapi import APIRouter, HTTPException, status

# App imports
from app import config, schemas
from app.services import provider_service # Import the specific service
from app.utils import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/config/provider", tags=["Configuration"])


@router.get("", response_model=schemas.ProviderStatusResponse)
async def get_provider_status_endpoint():
    """
    Returns the currently active AI provider.
    """
    # Reads directly from config as status check is simple
    active_provider = config.ACTIVE_AI_PROVIDER
    logger.info(f"Reporting current provider status: {active_provider.upper()}")
    return schemas.ProviderStatusResponse(
        current_provider=active_provider,
        message=f"Currently using {active_provider.upper()} provider."
    )


@router.post("", response_model=schemas.ProviderStatusResponse)
async def set_active_provider_endpoint(request: schemas.SetProviderRequest):
    """
    Sets the active AI provider by calling the provider service.
    Triggers re-initialization of AI components.
    """
    new_provider = request.provider
    current_provider = config.ACTIVE_AI_PROVIDER # Check current state

    if new_provider == current_provider:
        logger.info(f"Provider already set to {current_provider}. No action taken.")
        return schemas.ProviderStatusResponse(
            current_provider=current_provider,
            message=f"Provider is already set to {current_provider.upper()}."
        )

    logger.info(f"Request received to switch provider to: {new_provider.upper()}")

    # --- Call Service Layer ---
    try:
        # Delegate the switching logic and re-initialization to the service
        success = provider_service.switch_active_provider(new_provider)

        if success:
            # Service layer logs details
            updated_provider = config.ACTIVE_AI_PROVIDER # Re-read config after successful switch
            logger.info(f"Provider successfully switched to {updated_provider.upper()}.")
            return schemas.ProviderStatusResponse(
                current_provider=updated_provider,
                message=f"Successfully switched provider to {updated_provider.upper()}."
            )
        else:
            # This path might be less likely if service raises exceptions on failure
            logger.error(f"Provider service indicated failure switching to {new_provider.upper()}, but no exception was raised.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Provider service reported failure without specific error."
            )

    # --- Error Handling ---
    except ValueError as ve:
        # Catch configuration errors (e.g., missing API key) from service/config
        logger.error(f"Configuration error switching provider: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve) # Pass validation error message to client
        )
    except RuntimeError as rte:
        # Catch errors during re-initialization from the service layer
        logger.error(f"Runtime error switching provider: {rte}", exc_info=False) # Maybe don't need full trace here
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to switch provider due to an internal error: {rte}"
        )
    except Exception as e:
        # Catch any other unexpected exceptions
        logger.error(f"Unexpected error switching provider: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the provider switch."
        )