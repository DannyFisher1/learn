# app/core/components/vector_store.py

import logging
from typing import List, Optional, Set, Dict, Any
from pathlib import Path

# Database/Vector Store Imports
from chromadb import HttpClient, Settings # Added Settings
from langchain_community.vectorstores import Chroma
from chromadb.errors import InvalidDimensionException

# Langchain Core Imports
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.embeddings import Embeddings # For type hinting

# App imports
from app import config
from app.utils import get_logger, ensure_directory_exists
# --- Updated Embeddings Import ---
from app.core.ai.embeddings import get_embeddings, clear_embeddings_cache # <<< Use new getter/clearer
# ----------------------------------

logger = get_logger(__name__)

# --- Module-level Cache ---
_cached_vectorstore: Optional[Chroma] = None
_cached_embeddings_used: Optional[Embeddings] = None # Track embeddings used by the cache

# --- Vector Store Initialization ---
def get_vectorstore(force_reload_embeddings: bool = False) -> Chroma:
    """
    Initializes or retrieves the persistent Chroma vector store instance.
    Handles HTTP client and local modes. Uses the get_embeddings dependency.
    Reloads if embeddings are forced or if the underlying embedding instance changes.
    """
    global _cached_vectorstore, _cached_embeddings_used

    # --- Determine if reload is necessary ---
    reload_required = False
    current_embedding_instance: Optional[Embeddings] = None

    if force_reload_embeddings:
        logger.info("Vector store: Force reload embeddings requested.")
        clear_embeddings_cache() # Clear embeddings cache first
        # Getting new embeddings might raise errors if config is bad
        current_embedding_instance = get_embeddings()
        # If embeddings were forced, we must reload the vector store
        reload_required = True
        logger.info("Vector store reload forced due to forced embeddings reload.")
    else:
        # Get current embeddings instance (might be cached from embeddings.py)
        current_embedding_instance = get_embeddings()
        # Check if VS cache exists and if embeddings instance has changed
        if _cached_vectorstore is not None and _cached_embeddings_used is not current_embedding_instance:
            logger.warning("Embeddings instance has changed since vector store was cached. Forcing vector store reload.")
            reload_required = True
        elif _cached_vectorstore is None:
            logger.debug("No cached vector store found.")
            reload_required = True # Need to initialize if not cached

    # --- Re-initialize if needed ---
    if reload_required:
        logger.info(f"Initializing Vector Store Instance (Embeddings Forced: {force_reload_embeddings}, Reload Required: {reload_required})")
        # Ensure we have the definitive embedding instance
        if current_embedding_instance is None:
             current_embedding_instance = get_embeddings()

        try:
            # --- Chroma Setup ---
            collection_name = getattr(config, 'CHROMA_COLLECTION_NAME', "rag_collection")
            logger.info(f"Using Chroma collection: '{collection_name}'")

            vs_instance: Optional[Chroma] = None # Temporary variable for new instance

            if getattr(config, 'CHROMA_USE_HTTP', False):
                host = getattr(config, 'CHROMA_HTTP_HOST', "chroma")
                logger.info(f"CHROMA_HTTP_HOST: {host}")
                port = getattr(config, 'CHROMA_HTTP_PORT', 6000)
                logger.info(f"CHROMA_HTTP_PORT: {port}")
                logger.info(f"Attempting to connect to Chroma HTTP client at {host}:{port}")
                chroma_client = HttpClient(host=host, port=port, settings=Settings(anonymized_telemetry=False))
                # Test connection explicitly? client.heartbeat() might be useful
                vs_instance = Chroma(
                    client=chroma_client,
                    collection_name=collection_name,
                    embedding_function=current_embedding_instance, # Use current instance
                )
                logger.info("Chroma vector store initialized via HTTP client successfully.")
            else:
                persist_directory = str(config.VECTOR_STORE_DIR)
                ensure_directory_exists(persist_directory)
                logger.info(f"Attempting to initialize local Chroma vector store at: {persist_directory}")
                vs_instance = Chroma(
                    persist_directory=persist_directory,
                    collection_name=collection_name,
                    embedding_function=current_embedding_instance, # Use current instance
                )
                logger.info("Chroma vector store initialized locally with persistence.")

            # --- Update Cache ---
            _cached_vectorstore = vs_instance
            _cached_embeddings_used = current_embedding_instance
            # ------------------

        except InvalidDimensionException as ide:
            logger.error(f"Embedding dimension mismatch error initializing Chroma: {ide}. Check model consistency.")
            _cached_vectorstore = None # Reset cache
            _cached_embeddings_used = None
            raise RuntimeError(f"Chroma initialization failed due to embedding dimension mismatch: {ide}") from ide
        except Exception as e:
            logger.error(f"Failed to initialize Chroma vector store: {e}", exc_info=True)
            _cached_vectorstore = None # Reset cache
            _cached_embeddings_used = None
            raise RuntimeError(f"Vector store initialization failed: {e}") from e
    else:
        logger.debug("Using cached vector store instance.")


    # Final check before returning
    if _cached_vectorstore is None:
         logger.critical("Vector store instance is None after initialization attempt!")
         raise RuntimeError("Vector store is not available after initialization attempt.")

    return _cached_vectorstore

def clear_vectorstore_cache():
    """Clears the cached vector store instance and its associated embedding tracker."""
    global _cached_vectorstore, _cached_embeddings_used
    logger.info("Clearing cached VectorStore instance.")
    _cached_vectorstore = None
    _cached_embeddings_used = None


# --- Vector Store Operations (CRUD) ---
# These functions now implicitly use the cached/managed vectorstore via get_vectorstore()

def add_documents_to_vectorstore(documents: List[Document]):
    """Adds a list of LangChain Document objects to the vector store."""
    if not documents:
        logger.warning("No documents provided to add to vector store.")
        return
    try:
        vs = get_vectorstore() # Get potentially cached instance
        logger.info(f"Adding {len(documents)} document chunks to the vector store...")
        # The embedding function used here is the one associated with the current 'vs' instance
        ids = vs.add_documents(documents)
        logger.info(f"Added documents resulting in {len(ids)} new vector IDs.")
    except InvalidDimensionException as ide:
         logger.error(f"Embedding dimension mismatch adding documents: {ide}. Ensure embedding model matches collection.")
         raise RuntimeError(f"Failed to add documents due to embedding dimension mismatch: {ide}") from ide
    except RuntimeError as rte:
        logger.error(f"Cannot add documents: {rte}")
        raise
    except Exception as e:
        logger.error(f"Error adding documents to vector store: {e}", exc_info=True)
        raise RuntimeError(f"Failed to add documents to vector store: {e}") from e


def get_retriever(
    search_type: str = "similarity",
    k: Optional[int] = None,
    filter_metadata: Optional[Dict[str, Any]] = None
) -> VectorStoreRetriever:
    """Creates and returns a retriever instance from the vector store."""
    # (Logic remains the same, uses get_vectorstore implicitly)
    effective_k = k if k is not None else config.RETRIEVER_K
    search_kwargs = {"k": effective_k}
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
        raise RuntimeError(f"Failed to create retriever: {e}") from e


def list_indexed_sources_with_metadata() -> List[Dict[str, Any]]:
    """Retrieves the metadata for all documents currently indexed."""
    # (Logic remains the same, uses get_vectorstore implicitly)
    try:
        vs = get_vectorstore()
        logger.info("Attempting to retrieve all document metadata for listing.")
        results = vs.get(include=['metadatas'])
        if not results or not results.get("metadatas"):
            logger.info("No documents or metadata found in the vector store.")
            return []
        all_metadata = results["metadatas"]
        logger.info(f"Retrieved metadata for {len(all_metadata)} chunks.")
        valid_metadata = [meta for meta in all_metadata if isinstance(meta, dict)]
        return valid_metadata
    except RuntimeError as rte:
        logger.error(f"Cannot list sources with metadata: {rte}")
        return []
    except Exception as e:
        logger.error(f"Error listing indexed sources with metadata: {e}", exc_info=True)
        return []


def delete_documents_by_source(source_filename: str) -> bool:
    """Deletes documents associated with a specific source file."""
    # (Logic remains the same, uses get_vectorstore implicitly)
    logger.info(f"Attempting to delete documents with source_file: '{source_filename}'")
    if not isinstance(source_filename, str) or not source_filename:
         logger.error("Invalid source_filename provided for deletion.")
         return False
    try:
        vs = get_vectorstore()
        results = vs.get(where={"source_file": source_filename}, include=[])
        ids_to_delete = results.get("ids")
        if not ids_to_delete:
            logger.warning(f"No documents found matching source_file: '{source_filename}'. Nothing to delete.")
            return True
        logger.info(f"Found {len(ids_to_delete)} document chunks to delete for source: {source_filename}")
        vs.delete(ids=ids_to_delete)
        logger.info(f"Successfully deleted {len(ids_to_delete)} chunks from vector store for source: {source_filename}.")
        return True
    except RuntimeError as rte:
        logger.error(f"Cannot delete documents for source '{source_filename}': {rte}")
        return False
    except Exception as e:
        logger.error(f"Error deleting documents for source '{source_filename}': {e}", exc_info=True)
        return False