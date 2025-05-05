# app/api/documents.py

import logging
import os
import shutil
import asyncio # <<< Added import
# import urllib.parse # <--- Not used, can be removed
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException, status, Response, Form
from typing import Optional

# App imports
from app import config, schemas
from app.services import document_service
from app.utils import get_logger, ensure_directory_exists

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post("/upload", response_model=schemas.UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document_endpoint(
    file: UploadFile = File(..., description="The document file to upload (.pdf, .txt, .docx)."),
    tag: Optional[str] = Form(None, description="Optional tag/category for the document (e.g., 'homework', 'textbook').")
):
    """
    Handles document file uploads (.pdf, .txt, .docx), including an optional tag.
    Saves file temporarily (asynchronously), processes via service layer (passing the tag),
    and moves to final location (asynchronously) on success.
    """
    # --- File Validation (No change needed) ---
    filename = file.filename
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename cannot be empty.")

    file_extension = Path(filename).suffix.lower()
    allowed_extensions = {".pdf", ".txt", ".docx"}

    if file_extension not in allowed_extensions:
        logger.warning(f"Upload rejected: Invalid file type '{file_extension}' for file '{filename}'")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
        )
    # ------------------------------

    logger.info(f"Received upload for '{filename}' with tag: '{tag if tag else 'None'}'")

    # --- File Saving (Temporary) - Made Async ---
    temp_dir = config.UPLOAD_DIR / "temp"
    # ensure_directory_exists is sync, but typically fast. If it becomes an issue, wrap it.
    ensure_directory_exists(temp_dir)
    safe_filename = Path(filename).name
    temp_file_path = temp_dir / f"{safe_filename}.upload_tmp"
    final_file_path = config.UPLOAD_DIR / safe_filename

    # Check if file already exists (sync check, usually fast)
    if final_file_path.exists():
        logger.warning(f"File '{safe_filename}' already exists. Overwriting.")

    try:
        # --- Wrap blocking file I/O in thread ---
        logger.debug(f"Saving temporary file asynchronously to {temp_file_path}")
        with open(temp_file_path, "wb") as buffer:
            # Use asyncio.to_thread for shutil.copyfileobj as it's blocking I/O
            await asyncio.to_thread(shutil.copyfileobj, file.file, buffer)
        logger.info(f"File '{safe_filename}' temporarily saved to: {temp_file_path}")
        # ----------------------------------------
    except Exception as e: # Catch broader exceptions during file save
        logger.error(f"Failed to save uploaded file '{safe_filename}': {e}", exc_info=True)
        # Attempt to clean up partially written temp file if it exists
        if os.path.exists(temp_file_path):
            try:
                await asyncio.to_thread(os.remove, temp_file_path)
            except Exception as remove_err:
                 logger.error(f"Error removing partial temp file {temp_file_path} after save error: {remove_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save uploaded file."
        )
    finally:
        # file.close() is already awaitable from UploadFile
        await file.close()

    # --- Processing via Service Layer (already async) ---
    try:
        logger.info(f"Starting processing via service for: {safe_filename} with tag '{tag}'")
        # Call the already async service function
        result = await document_service.handle_upload(temp_file_path, safe_filename, tag)

        if result and result.get("success"):
            # --- Move file asynchronously ---
            ensure_directory_exists(config.UPLOAD_DIR) # Keep sync check
            logger.debug(f"Moving file asynchronously from {temp_file_path} to {final_file_path}")
            await asyncio.to_thread(shutil.move, str(temp_file_path), str(final_file_path))
            # -------------------------------
            logger.info(f"Processing successful. File moved to: {final_file_path}")
            return schemas.UploadResponse(filename=safe_filename, message=result.get("message", "Document processed successfully.")) # Typo fix: PDF -> Document
        else:
            # Processing failed, service logged details. Clean up temp file asynchronously.
            logger.error(f"Document processing failed for {safe_filename}. Reason: {result.get('message', 'Unknown')}")
            if os.path.exists(temp_file_path):
                 try:
                     # --- Remove temp file asynchronously ---
                     logger.debug(f"Removing temporary file asynchronously: {temp_file_path}")
                     await asyncio.to_thread(os.remove, temp_file_path)
                     # -------------------------------------
                     logger.info(f"Removed temporary file: {temp_file_path}")
                 except Exception as e: # Catch broader exceptions
                      logger.error(f"Error removing temporary file {temp_file_path}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to process document.") # Typo fix: PDF -> document
            )
    except Exception as e:
        # Catch unexpected errors during service call or file move
        logger.error(f"Unexpected error during upload handling for {safe_filename}: {e}", exc_info=True)
        # Clean up temp file asynchronously on any exception
        if os.path.exists(temp_file_path):
            try:
                # --- Remove temp file asynchronously ---
                logger.debug(f"Removing temporary file asynchronously due to error: {temp_file_path}")
                await asyncio.to_thread(os.remove, temp_file_path)
                # -------------------------------------
                logger.info(f"Removed temporary file due to error: {temp_file_path}")
            except Exception as remove_error: # Catch broader exceptions
                logger.error(f"Error removing temporary file {temp_file_path} after error: {remove_error}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during processing: {e}"
        )


@router.get("", response_model=schemas.DocumentListResponse)
async def list_documents_endpoint():
    """
    Retrieves the list of indexed documents asynchronously.
    """
    logger.info("Request received for listing indexed documents with tags and file types.")
    try:
        # Call the async service function
        document_data = await document_service.list_documents_service()

        # Adapt based on the richer data from the service (no change needed here)
        doc_details = [
            schemas.DocumentDetail(
                filename=item.get("filename", "Unknown"),
                tag=item.get("tag"),
                file_type=item.get("file_type")
            )
            for item in document_data
            if isinstance(item, dict) and item.get("filename")
        ]

        logger.info(f"Returning {len(doc_details)} indexed documents with tags and file types.")
        return schemas.DocumentListResponse(documents=doc_details)
    except Exception as e:
        logger.error(f"Failed to list indexed documents via service: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document list."
        )


@router.delete("/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_endpoint(filename: str):
    """
    Requests deletion of a document by filename asynchronously via the service layer.
    """
    try:
        decoded_filename = filename # Already decoded by FastAPI
        logger.info(f"Request received to delete document: '{decoded_filename}'")
    except Exception as e:
        logger.error(f"Error processing filename parameter: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename format."
        )

    try:
        # Call the async service layer function
        success = await document_service.delete_document_service(decoded_filename)
        if success:
            logger.info(f"Deletion process completed via service for '{decoded_filename}'.")
            # Return Response directly for 204 No Content
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        else:
            logger.warning(f"Deletion failed or document not found for '{decoded_filename}'.")
            # Service layer indicated failure (e.g., vector store returned false)
            # Consider if 404 is more appropriate if the service *knows* it wasn't found
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, # Changed to 404 assuming service handles 'not found' case
                detail=f"Document '{decoded_filename}' not found or could not be deleted."
            )
    except Exception as e:
        logger.error(f"Unexpected error during document deletion call for '{decoded_filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during deletion: {e}"
        )