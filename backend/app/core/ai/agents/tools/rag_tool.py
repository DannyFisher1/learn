import logging
import asyncio
import json # <<< Added import
from typing import Optional, Dict, Any, List
from langchain.chains.summarize import load_summarize_chain
from langchain_core.documents import Document
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

# Tool to query the vector store based on user documents
@tool
async def query_uploaded_documents(
    query: str,
    filenames_filter: Optional[List[str]] = None,
    tag_filter: Optional[str] = None
) -> str: # <<< Output is now a JSON STRING
    """
    Use this tool ONLY when the user asks a question that could plausibly be answered by
    their uploaded documents. Input is the user's specific question.
    Optionally specify 'filenames_filter' or 'tag_filter'.
    Do NOT use this for general knowledge questions or summarizing entire files.
    Returns a JSON string containing the 'answer' and the 'rag_sources' (list of dicts
    with filename, page, and snippet) used to generate the answer.
    """
    logger.info(f"RAG Tool invoked (async). Query: '{query[:50]}...', Filenames Filter: {filenames_filter}, Tag Filter: {tag_filter}")

    # Default structure for no results or errors
    error_output = {"answer": f"Could not find relevant information for '{query}'.", "rag_sources": []}

    try:
        combine_chain = get_combine_docs_chain() # Sync setup okay

        # Construct Metadata Filter
        metadata_filter: Dict[str, Any] = {}
        filter_log_parts = []
        if filenames_filter:
            if len(filenames_filter) == 1: metadata_filter["source_file"] = filenames_filter[0]; filter_log_parts.append(f"Filename='{filenames_filter[0]}'")
            elif len(filenames_filter) > 1: metadata_filter["source_file"] = {"$in": filenames_filter}; filter_log_parts.append(f"Filenames IN {filenames_filter}")
        if tag_filter: metadata_filter["tag"] = tag_filter; filter_log_parts.append(f"Tag='{tag_filter}'")
        filter_log = " and ".join(filter_log_parts) if filter_log_parts else "None"
        logger.info(f"RAG Tool: Applying metadata filter: {filter_log}")

        retriever = get_retriever( # Sync setup okay
            search_type="similarity",
            k=config.RETRIEVER_K,
            filter_metadata=metadata_filter if metadata_filter else None
        )

        # Retrieve Documents asynchronously
        logger.debug(f"Invoking retriever asynchronously with query: '{query}' and filter: {metadata_filter}")
        retrieved_docs: List[Document] = await retriever.ainvoke(query) # Async retrieval
        logger.info(f"RAG Tool: Retrieved {len(retrieved_docs)} documents matching filter: {filter_log}.")

        if not retrieved_docs:
             # Construct no results message
             filter_desc = "within the uploaded documents"
             if filenames_filter and tag_filter: filter_desc = f"within documents matching filenames {filenames_filter} and tag '{tag_filter}'"
             elif filenames_filter: filter_desc = f"within documents matching filenames {filenames_filter}" if len(filenames_filter) > 1 else f"within the document '{filenames_filter[0]}'"
             elif tag_filter: filter_desc = f"within documents tagged as '{tag_filter}'"
             logger.warning(f"No relevant documents found {filter_desc} for query: '{query}'")
             error_output["answer"] = f"Based on my search {filter_desc}, I could not find information relevant to your question: '{query}'"
             return json.dumps(error_output) # Return JSON string

        # --- Extract Context for UI ---
        rag_sources_for_ui = []
        for doc in retrieved_docs:
            metadata = doc.metadata or {}
            source_info = {
                "filename": metadata.get("source_file", "Unknown Source"),
                "page": metadata.get("page", "N/A"), # Use page number if available
                "snippet": doc.page_content # The retrieved chunk
            }
            rag_sources_for_ui.append(source_info)
        # ------------------------------

        # Invoke the Combine Docs Chain asynchronously
        logger.debug("Invoking combine documents chain asynchronously...")
        # Pass only necessary context to the chain if it doesn't need the full metadata within the chain itself
        # Or pass retrieved_docs directly if the chain handles Document objects
        chain_input = {
             "input": query,
             "context": retrieved_docs # Pass full docs if chain expects them
             # Alternatively, pass formatted context:
             # "context": "\n\n".join([f"Source: {s['filename']}, Page: {s['page']}\n{s['snippet']}" for s in rag_sources_for_ui])
        }
        answer_text = await combine_chain.ainvoke(chain_input) # Get synthesized answer string

        logger.info(f"RAG Tool generated answer length: {len(answer_text)}")

        # --- Construct Final JSON Output ---
        final_output = {
            "answer": answer_text.strip(),
            "rag_sources": rag_sources_for_ui
        }
        return json.dumps(final_output, default=str) # Return JSON string
        # ---------------------------------

    except RuntimeError as rte:
        logger.error(f"Runtime error setting up RAG tool components for query '{query}': {rte}", exc_info=False)
        error_output["answer"] = f"Error: Could not prepare the RAG tool components: {rte}"
        return json.dumps(error_output) # Return JSON string on error
    except Exception as e:
        logger.error(f"Unexpected error executing RAG tool for query '{query}': {e}", exc_info=True)
        error_output["answer"] = f"Error: An internal error occurred while searching the documents."
        return json.dumps(error_output) # Return JSON string on error

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