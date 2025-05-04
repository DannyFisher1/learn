# app/core/processing/document_processor.py

import logging
from typing import List, Union, Optional
from pathlib import Path

# Langchain imports for document handling
from langchain_community.document_loaders import (
    PyPDFLoader, 
    UnstructuredWordDocumentLoader,
    TextLoader,
    UnstructuredFileLoader  # Keep as fallback
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# App imports
from app import config
from app.utils import get_logger

logger = get_logger(__name__)

def process_document_to_chunks(
    file_path: Union[str, Path],
    original_filename: str,
    tag: Optional[str] = None,
    chunk_size: int = config.CHUNK_SIZE,
    chunk_overlap: int = config.CHUNK_OVERLAP
) -> Optional[List[Document]]:
    """
    Loads text from PDF, TXT, or DOCX files, splits it into chunks, and adds metadata.

    Args:
        file_path: Path to the document file.
        original_filename: The original name of the file.
        tag: Optional tag provided by the user.
        chunk_size: The target size for text chunks.
        chunk_overlap: The overlap between consecutive chunks.

    Returns:
        A list of Document objects (chunks) with metadata, or None if loading/processing fails.
    """
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        logger.error(f"File not found: {file_path_obj}")
        return None

    # --- Determine file extension from ORIGINAL filename --- 
    original_path_obj = Path(original_filename)
    file_extension = original_path_obj.suffix.lower()
    file_type = file_extension.lstrip('.')
    # -----------------------------------------------------

    logger.info(f"Processing document: {original_filename} (Detected Type: {file_type}, Tag: {tag}) from temporary path: {file_path_obj}")

    # --- Direct File Read Check --- (Keep this for initial validation)
    try:
        with open(file_path_obj, 'rb') as f:
            first_bytes = f.read(100)
            logger.debug(f"Directly read first {len(first_bytes)} bytes from {file_path_obj}: {first_bytes[:80]}...") # Log snippet
    except Exception as read_err:
        logger.error(f"Direct file read failed for {file_path_obj}: {read_err}", exc_info=True)
        return None
    # ----------------------------

    loader = None
    docs = []
    try:
        # Select Loader based on file type
        if file_extension == ".pdf":
            loader = PyPDFLoader(str(file_path_obj))
            logger.debug(f"Using PyPDFLoader for {original_filename}.")
            docs = loader.load()

        elif file_extension == ".txt":
            logger.debug(f"Attempting to load TXT file: {original_filename}")
            loaded_with_textloader = False
            # Attempt 1: TextLoader with chardet
            try:
                import chardet
                raw_data = file_path_obj.read_bytes()
                result = chardet.detect(raw_data)
                detected_encoding = result['encoding']
                confidence = result['confidence']
                if detected_encoding and confidence > 0.7: # Use if confidence is reasonable
                    logger.debug(f"Detected encoding {detected_encoding} (confidence: {confidence:.2f}), trying TextLoader.")
                    loader_attempt = TextLoader(str(file_path_obj), encoding=detected_encoding)
                    docs = loader_attempt.load()
                    if docs:
                        logger.info(f"Successfully loaded with TextLoader (Encoding: {detected_encoding}).")
                        loader = loader_attempt # Mark success
                        loaded_with_textloader = True
                else:
                    logger.warning(f"Chardet encoding detection uncertain (Encoding: {detected_encoding}, Confidence: {confidence:.2f}). Skipping TextLoader.")
            except ImportError:
                logger.warning("`chardet` not installed. Skipping TextLoader with encoding detection.")
            except Exception as e:
                logger.warning(f"TextLoader with detected encoding failed: {e}")

            # Attempt 2: UnstructuredFileLoader (if TextLoader failed or wasn't tried)
            if not loaded_with_textloader:
                try:
                    logger.debug("Using UnstructuredFileLoader (mode=elements) as fallback.")
                    loader_attempt = UnstructuredFileLoader(str(file_path_obj), mode="elements")
                    docs = loader_attempt.load()
                    if docs:
                        logger.info("Successfully loaded with UnstructuredFileLoader (mode=elements).")
                        loader = loader_attempt # Mark success
                except Exception as e:
                    logger.error(f"UnstructuredFileLoader fallback failed: {e}", exc_info=True)
                    # Both attempts failed
                    return None # Give up if both fail

        elif file_extension == ".docx":
            loader = UnstructuredWordDocumentLoader(str(file_path_obj))
            logger.debug(f"Using UnstructuredWordDocumentLoader for {original_filename}.")
            docs = loader.load()

        else:
            logger.error(f"Unsupported file type '{file_extension}' for {original_filename}")
            return None

        # --- Validation after loading ---
        if not docs:
            loader_name = type(loader).__name__ if loader else "UnknownLoader"
            logger.warning(f"No content loaded from {original_filename} (loader: {loader_name}). File might be empty or loader failed silently.")
            return None
        logger.info(f"Loaded {len(docs)} initial document parts from {original_filename}.")
        # ------------------------------

        # Split Text (Common logic for all successful loads)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        chunks = text_splitter.split_documents(docs)

        if not chunks:
            logger.warning(f"No chunks generated after splitting {original_filename}. Initial docs might have been empty.")
            return None

        # Add Metadata (User Tag + File Type)
        for chunk in chunks:
            chunk.metadata["source_file"] = original_filename
            chunk.metadata["file_type"] = file_type
            if tag:
                chunk.metadata["tag"] = tag
            if "page" not in chunk.metadata:
                chunk.metadata["page"] = chunk.metadata.get("page_number", "N/A")

        logger.info(f"Split '{original_filename}' into {len(chunks)} chunks. Metadata includes file_type='{file_type}' and tag='{tag}'.")
        return chunks

    except ImportError as ie:
        logger.error(f"Missing dependency for processing '{file_extension}' files: {ie}. Please install required libraries.")
        return None
    except Exception as e:
        # General catch-all for other unexpected errors during loading/splitting
        logger.error(f"Failed to process document {original_filename}: {e}", exc_info=True)
        return None