# app/core/components/vector_store.py

import logging
# --- Added Dict for metadata return ---
from typing import List, Optional, Set, Dict, Any
# --------------------------------------
from pathlib import Path

# Database/Vector Store Imports
from chromadb import HttpClient
from langchain_community.vectorstores import Chroma
from chromadb.errors import InvalidDimensionException # To catch embedding dimension errors

# Langchain Core Imports
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever # For type hinting

# App imports
from app import config
from app.utils import get_logger, ensure_directory_exists # Added ensure_directory_exists
# Import the function to get embeddings from the dedicated module
from app.core.ai.embeddings import _get_embeddings

logger = get_logger(__name__)

# --- Global Variable for Vector Store Caching ---
_vectorstore: Optional[Chroma] = None

# --- Vector Store Initialization ---
def get_vectorstore(force_reload_embeddings: bool = False) -> Chroma:
    """
    Initializes or retrieves the persistent Chroma vector store instance.
    Handles HTTP client and local modes, calls _get_embeddings.
    """
    global _vectorstore
    if _vectorstore is None or force_reload_embeddings:
        if force_reload_embeddings:
             logger.info("Forcing vector store re-initialization due to embedding reload request.")
        else:
             logger.info("Initializing vector store instance.")
        try:
            embeddings_func = _get_embeddings(force_reload=force_reload_embeddings)

            # --- Chroma Setup ---
            collection_name = config.CHROMA_COLLECTION_NAME if hasattr(config, 'CHROMA_COLLECTION_NAME') else "rag_collection"
            logger.info(f"Using Chroma collection: '{collection_name}'")

            if hasattr(config, 'CHROMA_USE_HTTP') and config.CHROMA_USE_HTTP:
                host = config.CHROMA_HTTP_HOST if hasattr(config, 'CHROMA_HTTP_HOST') else "localhost"
                port = config.CHROMA_HTTP_PORT if hasattr(config, 'CHROMA_HTTP_PORT') else 8000
                logger.info(f"Attempting to connect to Chroma HTTP client at {host}:{port}")
                # Consider adding connection timeout/retries if needed
                chroma_client = HttpClient(host=host, port=port)
                _vectorstore = Chroma(
                    client=chroma_client,
                    collection_name=collection_name,
                    embedding_function=embeddings_func,
                )
                logger.info("Chroma vector store initialized via HTTP client successfully.")
            else:
                persist_directory = str(config.VECTOR_STORE_DIR)
                ensure_directory_exists(persist_directory) # Ensure directory exists
                logger.info(f"Attempting to initialize local Chroma vector store at: {persist_directory}")
                _vectorstore = Chroma(
                    persist_directory=persist_directory,
                    collection_name=collection_name,
                    embedding_function=embeddings_func,
                )
                logger.info("Chroma vector store initialized locally with persistence.")

        except InvalidDimensionException as ide:
            logger.error(f"Embedding dimension mismatch error initializing Chroma: {ide}. "
                         "This often happens if you switch embedding models after adding data. "
                         "You may need to delete the existing vector store data and re-index.")
            _vectorstore = None
            raise RuntimeError(f"Chroma initialization failed due to embedding dimension mismatch: {ide}")
        except Exception as e:
            logger.error(f"Failed to initialize Chroma vector store: {e}", exc_info=True)
            _vectorstore = None
            raise RuntimeError(f"Vector store initialization failed: {e}")

    if _vectorstore is None:
         raise RuntimeError("Vector store is not available after initialization attempt.")
    return _vectorstore

# --- Vector Store Operations (CRUD) ---

def add_documents_to_vectorstore(documents: List[Document]):
    """
    Adds a list of LangChain Document objects to the vector store.
    Handles persistence for local mode.
    """
    if not documents:
        logger.warning("No documents provided to add to vector store.")
        return

    try:
        vs = get_vectorstore()
        logger.info(f"Adding {len(documents)} document chunks to the vector store...")
        # Handle potential embedding dimension errors during addition
        ids = vs.add_documents(documents)
        logger.info(f"Added documents resulting in {len(ids)} new vector IDs.")

        # Persist if needed (Check if Chroma client mode handles this)
        # if not (hasattr(config, 'CHROMA_USE_HTTP') and config.CHROMA_USE_HTTP):
        #    logger.info("Persisting vector store changes (local mode)...")
        #    vs.persist()
        #    logger.info("Vector store changes persisted.")
        # else:
        #     logger.info("Chroma running in HTTP mode; persistence handled by server.")

    except InvalidDimensionException as ide:
         logger.error(f"Embedding dimension mismatch adding documents: {ide}. "
                      "Ensure documents are embedded with the model matching the existing collection.")
         # Decide how to handle: raise error, skip docs? Raising is safer.
         raise RuntimeError(f"Failed to add documents due to embedding dimension mismatch: {ide}")
    except RuntimeError as rte:
        logger.error(f"Cannot add documents: {rte}")
        raise
    except Exception as e:
        logger.error(f"Error adding documents to vector store: {e}", exc_info=True)
        raise RuntimeError(f"Failed to add documents to vector store: {e}")


# --- Updated get_retriever to accept generic metadata filter ---
def get_retriever(
    search_type: str = "similarity",
    k: Optional[int] = None,
    filter_metadata: Optional[Dict[str, Any]] = None
) -> VectorStoreRetriever:
    """
    Creates and returns a retriever instance from the vector store,
    optionally filtering by metadata.

    Args:
        search_type: Type of search (e.g., "similarity", "mmr"). Defaults to "similarity".
        k: Number of documents to retrieve. Defaults to RETRIEVER_K from config.
        filter_metadata: A dictionary defining metadata filters (e.g.,
                         `{"source_file": "doc.pdf", "tag": "homework"}`). See ChromaDB
                         docs for filter syntax (e.g., $in, $eq operators).

    Returns:
        A VectorStoreRetriever instance configured for searching.

    Raises:
        RuntimeError: If the retriever cannot be created.
    """
    effective_k = k if k is not None else config.RETRIEVER_K
    search_kwargs = {"k": effective_k}

    # Add metadata filter if provided
    if filter_metadata:
        search_kwargs['filter'] = filter_metadata
        logger.info(f"Creating retriever with metadata filter: {filter_metadata}")
    else:
        logger.info("Creating retriever without metadata filter.")

    try:
        vs = get_vectorstore()
        retriever = vs.as_retriever(
            search_type=search_type,
            search_kwargs=search_kwargs
        )
        logger.info(f"Retriever created: search_type='{search_type}', k={effective_k}, filter={filter_metadata}")
        return retriever
    except RuntimeError as rte:
        logger.error(f"Cannot create retriever: {rte}")
        raise
    except Exception as e:
        logger.error(f"Error creating retriever: {e}", exc_info=True)
        raise RuntimeError(f"Failed to create retriever: {e}")


# --- NEW: Function to get all metadata for listing ---
def list_indexed_sources_with_metadata() -> List[Dict[str, Any]]:
    """
    Retrieves the metadata for all documents currently indexed in the vector store.

    Returns:
        A list of metadata dictionaries. Returns empty list on error or if empty.
        Example: [{'source_file': 'a.pdf', 'tag': 'hw', ...}, {'source_file': 'b.pdf', ...}]
    """
    try:
        vs = get_vectorstore()
        logger.info("Attempting to retrieve all document metadata for listing.")

        # Fetch only metadata for all documents in the collection
        # Adjust limit if needed, but fetching all metadata is required for the service layer
        results = vs.get(include=['metadatas']) # Fetch only metadata

        if not results or not results.get("metadatas"):
            logger.info("No documents or metadata found in the vector store.")
            return []

        all_metadata = results["metadatas"]
        logger.info(f"Retrieved metadata for {len(all_metadata)} chunks.")
        # Filter out any potential None entries just in case
        valid_metadata = [meta for meta in all_metadata if isinstance(meta, dict)]
        return valid_metadata

    except RuntimeError as rte:
        logger.error(f"Cannot list sources with metadata: {rte}")
        return []
    except Exception as e:
        logger.error(f"Error listing indexed sources with metadata: {e}", exc_info=True)
        return []


# --- OLD list_indexed_sources - Can be kept for simpler use cases or removed ---
def list_indexed_sources() -> List[str]:
    """
    DEPRECATED (prefer list_indexed_sources_with_metadata): Retrieves a list of unique source filenames.
    """
    logger.warning("Using deprecated list_indexed_sources. Prefer list_indexed_sources_with_metadata for richer info.")
    all_metadata = list_indexed_sources_with_metadata()
    sources: Set[str] = set()
    for meta in all_metadata:
        if "source_file" in meta and isinstance(meta["source_file"], str):
            sources.add(meta["source_file"])
    return sorted(list(sources))


def delete_documents_by_source(source_filename: str) -> bool:
    """
    Deletes documents associated with a specific source file. (No changes needed here)
    """
    logger.info(f"Attempting to delete documents with source_file: '{source_filename}'")
    if not isinstance(source_filename, str) or not source_filename:
         logger.error("Invalid source_filename provided for deletion.")
         return False
    try:
        vs = get_vectorstore()
        # Using Chroma's `delete` with a `where` filter is often more direct if supported well
        # vs.delete(where={"source_file": source_filename}) # Alternative approach
        # logger.info(f"Deletion request sent using where filter for source: {source_filename}")

        # Original approach: Find IDs first
        results = vs.get(where={"source_file": source_filename}, include=[]) # Fetch only IDs
        ids_to_delete = results.get("ids")

        if not ids_to_delete:
            logger.warning(f"No documents found matching source_file: '{source_filename}'. Nothing to delete.")
            return True

        logger.info(f"Found {len(ids_to_delete)} document chunks to delete for source: {source_filename}")
        if ids_to_delete:
            vs.delete(ids=ids_to_delete)
            logger.info(f"Successfully deleted {len(ids_to_delete)} chunks from vector store for source: {source_filename}.")

        # Persist if needed
        # if not (hasattr(config, 'CHROMA_USE_HTTP') and config.CHROMA_USE_HTTP): vs.persist()

        return True
    except RuntimeError as rte:
        logger.error(f"Cannot delete documents for source '{source_filename}': {rte}")
        return False
    except Exception as e:
        logger.error(f"Error deleting documents for source '{source_filename}': {e}", exc_info=True)
        return False