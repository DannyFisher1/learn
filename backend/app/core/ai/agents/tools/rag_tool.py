# app/core/ai/agents/tools/rag_tool.py

import logging
import asyncio # <<< Added import
from typing import Optional, Dict, Any, List
from langchain.chains.summarize import load_summarize_chain
from langchain_core.documents import Document # Changed from docstore
from langchain_community.vectorstores import Chroma
from langchain_core.tools import ToolException
from langchain.tools import tool
from langchain_core.vectorstores import VectorStoreRetriever

# App imports
from app import config
from app.utils import get_logger
from app.core.ai.llm import get_llm
from app.core.components.vector_store import get_vectorstore, get_retriever
from app.core.ai.agents.chains import get_combine_docs_chain

logger = get_logger(__name__)

# --- Updated tool signature to async and using ainvoke ---
@tool
async def query_uploaded_documents( # <<< Changed to async def
    query: str,
    filenames_filter: Optional[List[str]] = None,
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
    logger.info(f"RAG Tool invoked (async). Query: '{query[:50]}...', Filenames Filter: {filenames_filter}, Tag Filter: {tag_filter}")

    try:
        # Getting chain and retriever instances are usually fast sync operations
        combine_chain = get_combine_docs_chain()

        # Construct Metadata Filter (No change needed here)
        metadata_filter: Dict[str, Any] = {}
        filter_log_parts = []
        if filenames_filter:
            if len(filenames_filter) == 1:
                metadata_filter["source_file"] = filenames_filter[0]
                filter_log_parts.append(f"Filename='{filenames_filter[0]}'")
            elif len(filenames_filter) > 1:
                metadata_filter["source_file"] = {"$in": filenames_filter}
                filter_log_parts.append(f"Filenames IN {filenames_filter}")
        if tag_filter:
            metadata_filter["tag"] = tag_filter
            filter_log_parts.append(f"Tag='{tag_filter}'")

        filter_log = " and ".join(filter_log_parts) if filter_log_parts else "None"
        logger.info(f"RAG Tool: Applying metadata filter: {filter_log}")

        # Get Retriever (sync setup)
        retriever = get_retriever(
            search_type="similarity",
            k=config.RETRIEVER_K,
            filter_metadata=metadata_filter if metadata_filter else None
        )

        # 2. Retrieve Documents asynchronously
        logger.debug(f"Invoking retriever asynchronously with query: '{query}' and filter: {metadata_filter}")
        retrieved_docs = await retriever.ainvoke(query) # <<< Changed to ainvoke
        logger.info(f"RAG Tool: Retrieved {len(retrieved_docs)} documents matching filter: {filter_log}.")

        if not retrieved_docs:
             # Handling no results (No change needed here)
             filter_desc = "within the uploaded documents"
             if filenames_filter and tag_filter:
                 filter_desc = f"within documents matching filenames {filenames_filter} and tag '{tag_filter}'"
             elif filenames_filter:
                  if len(filenames_filter) == 1: filter_desc = f"within the document '{filenames_filter[0]}'"
                  else: filter_desc = f"within documents matching filenames {filenames_filter}"
             elif tag_filter: filter_desc = f"within documents tagged as '{tag_filter}'"
             logger.warning(f"No relevant documents found {filter_desc} for query: '{query}'")
             return f"Based on my search {filter_desc}, I could not find information relevant to your question: '{query}'"

        # 3. Invoke the Combine Docs Chain asynchronously to Synthesize Answer
        logger.debug("Invoking combine documents chain asynchronously...")
        answer = await combine_chain.ainvoke({ # <<< Changed to ainvoke
            "input": query,
            "context": retrieved_docs
        })

        logger.info(f"RAG Tool generated answer length: {len(answer)}")
        return answer

    except RuntimeError as rte:
        # Catch errors from get_combine_docs_chain or get_retriever setup
        logger.error(f"Runtime error setting up RAG tool components for query '{query}': {rte}", exc_info=False)
        # Raise ToolException for agent awareness
        raise ToolException(f"Error: Could not prepare the RAG tool components: {rte}")
    except Exception as e:
        # Catch errors during ainvoke or other processing
        logger.error(f"Unexpected error executing RAG tool for query '{query}': {e}", exc_info=True)
        raise ToolException(f"Error: An internal error occurred while searching the documents.")


# --- Helper function remains synchronous ---
def _load_document_chunks_by_filename(filename: str) -> Optional[List[Document]]:
    """
    Loads all document chunks associated with a specific filename.
    NOTE: This function is synchronous as vs.get() is likely synchronous.
    It should be called using asyncio.to_thread from async contexts.
    """
    logger.info(f"Attempting to load all chunks for document: '{filename}' for summarization.")
    try:
        vs = get_vectorstore() # Sync setup
        # Fetch all chunks - assume vs.get() is synchronous blocking I/O
        results = vs.get(where={"source_file": filename}, include=['documents', 'metadatas'], limit=1000)

        if not results or not results.get("ids"):
            logger.warning(f"No document chunks found in vector store for filename: '{filename}'")
            return None

        # Reconstruct Document objects (sync processing)
        docs = []
        contents = results.get("documents", [])
        metadatas = results.get("metadatas", [])
        ids = results.get("ids", [])

        if not (len(contents) == len(metadatas) == len(ids)):
             logger.error(f"Mismatch in lengths retrieving chunks for {filename}. Cannot reconstruct documents.")
             return None

        for i in range(len(ids)):
             docs.append(Document(page_content=contents[i], metadata=metadatas[i]))

        logger.info(f"Loaded {len(docs)} chunks for filename: '{filename}'.")
        return docs

    except Exception as e:
        logger.error(f"Error loading document chunks for '{filename}': {e}", exc_info=True)
        return None # Return None on error

@tool
async def summarize_document_content(filename: str, detail_level: str = "concise overview") -> str:
    """
    Use this tool ONLY to generate a summary of the entire content of a specific uploaded document identified by its filename.
    (Docstring unchanged)
    """
    logger.info(f"Summarize Document Tool invoked (async). Filename: '{filename}', Detail Level: '{detail_level}'")

    # 1. Load chunks asynchronously by running the sync helper in a thread
    logger.debug(f"Loading chunks for '{filename}' asynchronously...")
    try:
        document_chunks = await asyncio.to_thread( # <<< Wrap the sync helper call
            _load_document_chunks_by_filename, filename
        )
    except Exception as load_err:
         logger.error(f"Error occurred in thread while loading chunks for {filename}: {load_err}", exc_info=True)
         raise ToolException(f"Failed to load document content for '{filename}' due to an internal error.")


    if document_chunks is None: # Check if helper returned None due to internal error
         raise ToolException(f"Could not find or load the document '{filename}' (it may not exist or an error occurred during loading). Please ensure the filename is correct.")

    if len(document_chunks) == 0: # Check if loading succeeded but found no chunks
         raise ToolException(f"Document '{filename}' was found but appears empty or lacks processable content.")

    # 2. Initialize Chain (sync setup is fine)
    try:
        llm = get_llm()
        chain_type = "map_reduce"
        logger.info(f"Initializing summarization chain (type: {chain_type}) for {len(document_chunks)} chunks.")
        summary_chain = load_summarize_chain(llm, chain_type=chain_type, verbose=False)

        # 3. Run Chain asynchronously (already using arun)
        logger.info(f"Running summarization chain async for '{filename}'...")
        # Ensure input_documents key matches what the chain expects
        summary_result = await summary_chain.ainvoke({"input_documents": document_chunks})

        # The result from load_summarize_chain (especially map_reduce) is often a dictionary like {'output_text': '...'}
        final_summary = ""
        if isinstance(summary_result, dict):
            final_summary = summary_result.get("output_text", "")
            if not final_summary:
                 logger.warning(f"Summarization chain for '{filename}' returned a dictionary but 'output_text' key was missing or empty: {summary_result}")
                 final_summary = str(summary_result) # Fallback to string representation
        elif isinstance(summary_result, str):
            final_summary = summary_result # If it returns a simple string
        else:
            logger.warning(f"Summarization chain for '{filename}' returned unexpected type: {type(summary_result)}. Using string representation.")
            final_summary = str(summary_result)


        if not final_summary.strip():
             logger.warning(f"Summarization chain for '{filename}' produced an empty result.")
             raise ToolException(f"Failed to generate a summary for '{filename}'. The process completed but yielded no content.")


        logger.info(f"Summarization chain completed for '{filename}'. Summary length: {len(final_summary)}")
        return f"Summary of '{filename}':\n\n{final_summary}"

    except Exception as e:
        logger.error(f"Error during summarization chain initialization or execution for '{filename}': {e}", exc_info=True)
        raise ToolException(f"An unexpected error occurred while trying to summarize the document '{filename}'.")