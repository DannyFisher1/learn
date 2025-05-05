# app/services/document_service.py

import logging
import asyncio # <<< Added import
from pathlib import Path
from typing import List, Dict, Union, Any, Optional

# App imports
from app.core.processing import document_processor # Handles loading/splitting
from app.core.components import vector_store      # Handles ChromaDB interactions
from app.utils import get_logger

logger = get_logger(__name__)

# --- Updated handle_upload to call processor and add docs asynchronously ---
async def handle_upload(temp_file_path: Union[str, Path], original_filename: str, tag: Optional[str] = None) -> Dict[str, Any]:
    """
    Orchestrates the processing and storage of an uploaded document, including its tag.
    Runs blocking operations (processing, vector store add) in separate threads.

    1. Processes the document using document_processor asynchronously.
    2. If chunks are successfully created, adds them to the vector store asynchronously.

    Args:
        temp_file_path: Path to the temporarily saved uploaded file.
        original_filename: The original name of the uploaded file.
        tag: Optional tag/category assigned to the document.

    Returns:
        A dictionary containing: 'success', 'message', 'filename'.
    """
    logger.info(f"Service handling upload for: {original_filename} (Tag: {tag}) from temp path: {temp_file_path}")
    processed_successfully = False
    message = "Upload handling started."

    try:
        logger.info(f"Calling document processor asynchronously for {original_filename} with tag '{tag}'...")
        # --- Call processor asynchronously ---
        chunks = await asyncio.to_thread(
            document_processor.process_document_to_chunks,
            temp_file_path, original_filename, tag=tag
        )
        # -----------------------------------

        if not chunks:
            message = f"Processing failed or yielded no text content for '{original_filename}'. Document not added."
            logger.warning(message)
            return {"success": False, "message": message, "filename": original_filename}

        logger.info(f"Successfully processed '{original_filename}' into {len(chunks)} chunks with tag '{tag}'.")

        # --- Add Chunks to Vector Store asynchronously ---
        logger.info(f"Adding {len(chunks)} chunks for '{original_filename}' to vector store asynchronously...")
        # Assuming add_documents_to_vectorstore might block
        await asyncio.to_thread(vector_store.add_documents_to_vectorstore, chunks)
        logger.info(f"Chunks for '{original_filename}' added to vector store.")

        processed_successfully = True
        message = f"Document '{original_filename}' (Tag: {tag}) processed and stored successfully."

    except FileNotFoundError:
        message = f"Temporary file not found at {temp_file_path}. Upload failed."
        logger.error(message)
        processed_successfully = False
    # Note: asyncio.to_thread might raise the original exception if the thread function fails
    except RuntimeError as rte:
         message = f"A runtime error occurred during processing or storage of '{original_filename}': {rte}"
         logger.error(message, exc_info=False)
         processed_successfully = False
    except Exception as e:
        message = f"An unexpected error occurred while handling upload for '{original_filename}': {e}"
        logger.error(message, exc_info=True)
        processed_successfully = False

    return {"success": processed_successfully, "message": message, "filename": original_filename}

# --- Changed list_documents_service to async and wrap vector store call ---
async def list_documents_service() -> List[Dict[str, Optional[str]]]:
    """
    Retrieves the list of unique indexed documents asynchronously, including their filenames, tags, and file types.

    Returns:
        A list of dictionaries, containing 'filename', 'tag', and 'file_type'.
        Example: [{'filename': 'a.pdf', 'tag': 'hw', 'file_type': 'pdf'}, ...]
    """
    logger.info("Service retrieving list of indexed documents with tags and file types asynchronously.")
    document_details: List[Dict[str, Optional[str]]] = []
    try:
        # Assuming list_indexed_sources_with_metadata might block
        all_metadata = await asyncio.to_thread(vector_store.list_indexed_sources_with_metadata)

        # Process metadata (this part is usually fast and okay to keep sync)
        unique_docs: Dict[str, Dict[str, Optional[str]]] = {}
        for meta in all_metadata:
             filename = meta.get("source_file")
             if filename and filename not in unique_docs: # Process each filename only once
                  tag = meta.get("tag")
                  file_type = meta.get("file_type") # Get file_type
                  unique_docs[filename] = {
                      "tag": tag if isinstance(tag, str) else None,
                      "file_type": file_type if isinstance(file_type, str) else None
                  }

        # Convert the dictionary into the desired list format
        document_details = [
            {
                "filename": fname,
                "tag": data.get("tag"),
                "file_type": data.get("file_type")
            }
            for fname, data in unique_docs.items()
        ]
        document_details.sort(key=lambda x: x.get("filename", "").lower())

        logger.info(f"Service processed metadata, found {len(document_details)} unique documents with tags/types.")
        return document_details

    except NotImplementedError:
         logger.error("The vector store function 'list_indexed_sources_with_metadata' is not yet implemented.")
         return []
    except Exception as e:
        logger.error(f"Error retrieving or processing document list from vector store: {e}", exc_info=True)
        return []


# --- Changed delete_document_service to async and wrap vector store call ---
async def delete_document_service(filename: str) -> bool:
    """
    Requests the deletion of all document chunks associated with a given source filename asynchronously.
    """
    logger.info(f"Service requesting deletion of document: '{filename}' asynchronously.")
    if not filename:
        logger.warning("Delete request received with empty filename.")
        return False
    try:
        # Assuming delete_documents_by_source might block
        success = await asyncio.to_thread(vector_store.delete_documents_by_source, filename)
        if success:
             logger.info(f"Deletion request for '{filename}' processed by vector store (Success={success}).")
        else:
             logger.warning(f"Deletion request failed in vector store for '{filename}'.")
        return success
    except Exception as e:
        logger.error(f"Error requesting document deletion from vector store for '{filename}': {e}", exc_info=True)
        return False