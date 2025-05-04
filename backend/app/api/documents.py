# app/api/documents.py

import logging
import os
import shutil
import urllib.parse
from pathlib import Path
# --- Added Form for tag ---
from fastapi import APIRouter, File, UploadFile, HTTPException, status, Response, Form
# --------------------------
from typing import Optional # For optional Form field

# App imports
from app import config, schemas
from app.services import document_service # Import the service layer
# Ensure utils provides the necessary functions if config doesn't
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
    Saves file temporarily, processes via service layer (passing the tag),
    and moves to final location on success.
    """
    # --- Updated File Validation ---
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

    # --- File Saving (Temporary) ---
    temp_dir = config.UPLOAD_DIR / "temp"
    ensure_directory_exists(temp_dir)
    safe_filename = Path(filename).name # Use original filename for safety
    temp_file_path = temp_dir / f"{safe_filename}.upload_tmp"
    final_file_path = config.UPLOAD_DIR / safe_filename

    # Check if file already exists in final destination (optional)
    if final_file_path.exists():
        logger.warning(f"File '{safe_filename}' already exists. Overwriting.")
        # Decide on behavior: reject, overwrite (current), version, etc.

    try:
        # Stream file content to temporary location
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"File '{safe_filename}' temporarily saved to: {temp_file_path}")
    except IOError as e:
        logger.error(f"Failed to save uploaded file '{safe_filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save uploaded file."
        )
    finally:
        await file.close() # Ensure file handle is closed

    # --- Processing via Service Layer (Pass the tag) ---
    try:
        logger.info(f"Starting processing via service for: {safe_filename} with tag '{tag}'")
        # Pass temp path, original filename, and tag to service
        result = await document_service.handle_upload(temp_file_path, safe_filename, tag)
        # ---------------------------------

        if result and result.get("success"):
            # Move file from temp to final location ONLY on full success
            # Ensure target directory exists before moving
            ensure_directory_exists(config.UPLOAD_DIR)
            shutil.move(str(temp_file_path), str(final_file_path))
            logger.info(f"Processing successful. File moved to: {final_file_path}")
            return schemas.UploadResponse(filename=safe_filename, message=result.get("message", "PDF processed successfully."))
        else:
            # Processing failed, service should log details. Clean up temp file.
            logger.error(f"Document processing failed for {safe_filename}. Reason: {result.get('message', 'Unknown')}")
            if os.path.exists(temp_file_path):
                 try:
                     os.remove(temp_file_path)
                     logger.info(f"Removed temporary file: {temp_file_path}")
                 except OSError as e:
                      logger.error(f"Error removing temporary file {temp_file_path}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to process PDF.")
            )
    except Exception as e:
        # Catch unexpected errors during service call or file move
        logger.error(f"Unexpected error during upload handling for {safe_filename}: {e}", exc_info=True)
        # Clean up temp file on any exception
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Removed temporary file due to error: {temp_file_path}")
            except OSError as remove_error:
                logger.error(f"Error removing temporary file {temp_file_path} after error: {remove_error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during processing: {e}"
        )


@router.get("", response_model=schemas.DocumentListResponse)
async def list_documents_endpoint():
    """
    Retrieves the list of indexed documents, including filenames, tags,
    and file types from the service layer.
    """
    logger.info("Request received for listing indexed documents with tags and file types.")
    try:
        # Service layer now returns list of dicts with filename, tag, file_type
        document_data = document_service.list_documents_service()

        # Adapt based on the richer data from the service
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
    Requests deletion of a document by filename via the service layer.
    (No change needed here for tagging, as deletion is by filename only).
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
        # Call the service layer function
        success = document_service.delete_document_service(decoded_filename)
        if success:
            logger.info(f"Deletion process completed via service for '{decoded_filename}'.")
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        else:
            logger.warning(f"Deletion failed or document not found for '{decoded_filename}'.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # Or 404 if service could differentiate
                detail=f"Failed to delete document '{decoded_filename}'."
            )
    except Exception as e:
        logger.error(f"Unexpected error during document deletion call for '{decoded_filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during deletion: {e}"
        )