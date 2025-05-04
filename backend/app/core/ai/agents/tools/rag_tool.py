# app/core/ai/agents/tools/rag_tool.py

import logging
# --- Added Dict, Any for filter typing ---
from typing import Optional, Dict, Any, List
# -----------------------------------------
from langchain.chains.summarize import load_summarize_chain
from langchain.docstore.document import Document # Use base Document type
from langchain_community.vectorstores import Chroma # To load specific docs
from langchain_core.tools import ToolException # Import ToolException
from app import config
from app.utils import get_logger
from app.core.ai.llm import _get_llm # Get the currently configured LLM
from app.core.components.vector_store import get_vectorstore # Access vector store

# Ap
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


def _load_document_chunks_by_filename(filename: str) -> Optional[List[Document]]:
    """Loads all document chunks associated with a specific filename."""
    logger.info(f"Attempting to load all chunks for document: '{filename}' for summarization.")
    try:
        vs = get_vectorstore()
        # Fetch all chunks matching the source_file metadata
        # Note: Depending on Chroma version/usage, 'get' might be more direct
        # than 'similarity_search' if we don't need relevance sorting here.
        # Using similarity search with a large k might be a pragmatic way
        # to get *all* chunks if 'get' with where filter is tricky.
        # Let's try 'get' first. Increase limit if needed. Assume max 1000 chunks per doc.
        results = vs.get(where={"source_file": filename}, include=['documents', 'metadatas'], limit=1000)

        if not results or not results.get("ids"):
            logger.warning(f"No document chunks found in vector store for filename: '{filename}'")
            return None

        # Reconstruct Document objects (vs.get returns contents/metadata separately)
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
        # Optional: Sort docs by page number or chunk ID if metadata allows,
        # which might help 'map_reduce' or 'refine' strategies.
        # E.g., docs.sort(key=lambda d: int(d.metadata.get('page', 0) or 0))
        return docs

    except Exception as e:
        logger.error(f"Error loading document chunks for '{filename}': {e}", exc_info=True)
        return None

@tool
async def summarize_document_content(filename: str, detail_level: str = "concise overview") -> str:
    """
    Use this tool ONLY to generate a summary of the entire content of a specific uploaded document identified by its filename.

    Purpose: To provide a condensed version (summary) of a specific document that the user has uploaded.

    Input:
      - `filename` (string, required): The exact filename of the document to be summarized (e.g., "chapter_3_notes.pdf", "research_paper.docx").
      - `detail_level` (string, optional): Describes the desired summary length/detail. Examples: "brief points", "concise overview", "detailed summary". Defaults to "concise overview".

    Output:
      - (string): The generated summary of the specified document, or an error message if the document cannot be found or summarization fails.

    ***IMPORTANT USAGE NOTES***:
    1.  **Specific Document:** This tool works on ONE entire document at a time, specified by its filename.
    2.  **Use Case:** Use ONLY when the user explicitly asks to "summarize [filename]" or "give me the main points of [filename]".
    3.  **Contrast with RAG:** Do NOT use this tool to answer specific questions *about* a document's content (e.g., "What did [filename] say about X?"). Use `query_uploaded_documents` for that, as it retrieves only relevant snippets. This tool processes the *entire* document content.
    4.  **Potential Delay:** Summarizing a whole document can take longer than answering a specific question, especially for long documents.
    5.  **Input Filename Accuracy:** The agent must provide the correct filename as listed in the system (e.g., from chat history or document lists).

    Example Scenarios:
      - User asks: "Can you summarize 'Introduction_to_AI.pdf' for me?" -> Use this tool with `filename="Introduction_to_AI.pdf"`. Optionally add `detail_level="concise overview"`.
      - User asks: "Give me the key takeaways from 'lecture_5_slides.pdf'." -> Use this tool with `filename="lecture_5_slides.pdf"` and `detail_level="brief points"`.
      - User asks: "What is the definition of mitigation in 'climate_report.docx'?" -> DO NOT use this tool. Use `query_uploaded_documents`.
    """
    # ... (Function implementation remains the same as before) ...
    logger.info(f"Summarize Document Tool invoked. Filename: '{filename}', Detail Level: '{detail_level}'")

    # 1. Load chunks
    document_chunks = _load_document_chunks_by_filename(filename) # This helper is sync

    if not document_chunks:
        # Raise ToolException for clearer agent feedback
        raise ToolException(f"Could not find or load the document '{filename}'. Please ensure the filename is correct.")

    if len(document_chunks) == 0:
         raise ToolException(f"Document '{filename}' was found but appears empty or lacks processable content.")

    # 2. Initialize Chain
    try:
        llm = _get_llm() # Sync fetch of LLM instance
        chain_type = "map_reduce" # Or choose dynamically
        logger.info(f"Initializing summarization chain (type: {chain_type}) for {len(document_chunks)} chunks.")
        summary_chain = load_summarize_chain(llm, chain_type=chain_type, verbose=False)

        # 3. Run Chain (use arun for async chain execution)
        logger.info(f"Running summarization chain async for '{filename}'...")
        summary_result = await summary_chain.arun({"input_documents": document_chunks})
        logger.info(f"Summarization chain completed for '{filename}'. Summary length: {len(summary_result)}")

        # Add clear prefix to the result
        return f"Summary of '{filename}':\n\n{summary_result}"

    except Exception as e:
        logger.error(f"Error during summarization process for '{filename}': {e}", exc_info=True)
        # Raise ToolException on errors
        raise ToolException(f"An unexpected error occurred while trying to summarize the document '{filename}'.")

