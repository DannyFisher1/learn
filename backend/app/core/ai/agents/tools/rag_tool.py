# app/core/ai/agents/tools/rag_tool.py

import logging
# --- Added Dict, Any for filter typing ---
from typing import Optional, Dict, Any, List
# -----------------------------------------

# Langchain imports
from langchain.tools import tool
from langchain_core.vectorstores import VectorStoreRetriever

# App imports
from app import config
from app.utils import get_logger
# --- Updated import to use the modified get_retriever ---
from app.core.components.vector_store import get_vectorstore, get_retriever
# ----------------------------------------------------
from app.core.ai.agents.chains import get_combine_docs_chain

logger = get_logger(__name__)

# --- Updated tool signature and description ---
@tool
def query_uploaded_documents(
    query: str,
    filenames_filter: Optional[List[str]] = None, # Changed to list
    tag_filter: Optional[str] = None
) -> str:
    """
    Use this tool ONLY when the user asks a question specifically about the content
    within their uploaded documents (like textbooks, PDFs, notes, slides, homework).
    Input is the user's question.
    Optionally specify:
      - 'filenames_filter': A list of specific filenames to search within.
      - 'tag_filter': A specific document type/tag to search within (e.g., 'homework', 'textbook').
    If both filters are provided, documents must match BOTH conditions.
    Do NOT use this for general knowledge questions.
    """
    logger.info(f"RAG Tool invoked. Query: '{query[:50]}...', Filenames Filter: {filenames_filter}, Tag Filter: {tag_filter}")

    try:
        # --- Get the combine docs chain (no change here) ---
        combine_chain = get_combine_docs_chain()
        # -------------------------------------------------

        # --- Construct Metadata Filter (Handles List of Filenames) ---
        metadata_filter: Dict[str, Any] = {}
        filter_log_parts = []

        # Handle filename filter (single or multiple)
        if filenames_filter:
            if len(filenames_filter) == 1:
                # Single filename filter
                metadata_filter["source_file"] = filenames_filter[0]
                filter_log_parts.append(f"Filename='{filenames_filter[0]}'")
            elif len(filenames_filter) > 1:
                # Multiple filenames filter using $in operator
                metadata_filter["source_file"] = {"$in": filenames_filter}
                filter_log_parts.append(f"Filenames IN {filenames_filter}")
            # If list is empty, effectively no filter is applied

        # Handle tag filter
        if tag_filter:
            metadata_filter["tag"] = tag_filter
            filter_log_parts.append(f"Tag='{tag_filter}'")
        # -----------------------------------------------------------

        filter_log = " and ".join(filter_log_parts) if filter_log_parts else "None"
        logger.info(f"RAG Tool: Applying metadata filter: {filter_log}")
        # ---------------------------------

        # 1. Get Retriever using the constructed filter
        # Use the updated get_retriever function
        retriever = get_retriever(
            search_type="similarity", # Or make configurable
            k=config.RETRIEVER_K,
            filter_metadata=metadata_filter if metadata_filter else None # Pass the combined filter
        )
        # --------------------------------------------------

        # 2. Retrieve Documents
        logger.debug(f"Invoking retriever with query: '{query}' and filter: {metadata_filter}")
        retrieved_docs = retriever.invoke(query)
        logger.info(f"RAG Tool: Retrieved {len(retrieved_docs)} documents matching filter: {filter_log}.")

        if not retrieved_docs:
             # Provide more specific feedback based on filters used
             filter_desc = "within the uploaded documents"
             if filenames_filter and tag_filter:
                 filter_desc = f"within documents matching filenames {filenames_filter} and tag '{tag_filter}'"
             elif filenames_filter:
                  if len(filenames_filter) == 1:
                      filter_desc = f"within the document '{filenames_filter[0]}'"
                  else:
                       filter_desc = f"within documents matching filenames {filenames_filter}"
             elif tag_filter:
                  filter_desc = f"within documents tagged as '{tag_filter}'"

             logger.warning(f"No relevant documents found {filter_desc} for query: '{query}'")
             return f"Based on my search {filter_desc}, I could not find information relevant to your question: '{query}'"

        # Log retrieved sources for debugging (optional)
        # retrieved_sources = {doc.metadata.get('source_file', 'Unknown') for doc in retrieved_docs}
        # logger.debug(f"Retrieved content from sources: {retrieved_sources}")

        # 3. Invoke the Combine Docs Chain to Synthesize Answer
        logger.debug("Invoking combine documents chain...")
        answer = combine_chain.invoke({
            "input": query,
            "context": retrieved_docs
        })

        logger.info(f"RAG Tool generated answer length: {len(answer)}")
        return answer

    except RuntimeError as rte:
        logger.error(f"Runtime error executing RAG tool components for query '{query}': {rte}", exc_info=False)
        return f"Error: Could not prepare the RAG tool components: {rte}"
    except Exception as e:
        logger.error(f"Unexpected error executing RAG tool for query '{query}': {e}", exc_info=True)
        return f"Error: An internal error occurred while searching the documents for your query."

# Note: The 'tools' list definition remains in tools/__init__.py