# backend/app/core/ai/agents/tools/web_search_searx_tool.py

import logging
from langchain_community.utilities import SearxSearchWrapper
from langchain_core.tools import ToolException
from langchain.tools import tool
import fake_headers

from app import config # Import config to get the URL
from app.utils import get_logger

logger = get_logger(__name__)


from fake_headers import Headers
headers = Headers().generate()

# Initialize the wrapper *once* if configured
_searx_wrapper = None
_tool_enabled = False

if config.SEARXNG_URL:
    try:
        logger.info(f"Initializing SearxSearchWrapper for host: {config.SEARXNG_URL}")
        _searx_wrapper = SearxSearchWrapper(
            searx_host=config.SEARXNG_URL,
            headers=headers,
            unsecure=config.SEARXNG_UNSECURE,
            k=5
        )
        _tool_enabled = True
        logger.info("SearxSearchWrapper initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize SearxSearchWrapper: {e}", exc_info=True)
        _searx_wrapper = None # Ensure it's None on failure
        _tool_enabled = False
    except ValueError as e:
        if  "403" in str(e): 
            raise ToolException("SearXNG blocked the request; try another host.")

else:
    logger.warning("SearXNG URL not configured. Web search tool is disabled.")
    _tool_enabled = False


@tool
def search_the_web(query: str) -> str:
    """
    Use this tool ONLY to find real-time information or general knowledge on the internet.

    Purpose: To answer questions about current events, definitions, facts, or topics that are NOT expected to be found within the user's uploaded documents.

    Input:
      - `query` (string, required): A concise search query string suitable for a web search engine. Formulate this based on the user's question.

    Output:
      - (string): A summary of the web search results found, or a message indicating if the search failed or returned no relevant results.

    ***IMPORTANT USAGE NOTES***:
    1.  **PRIORITIZE DOCUMENTS:** Before using this tool, ALWAYS consider if the `query_uploaded_documents` tool could answer the question based on the user's materials. Use this web search tool ONLY if the question is clearly outside the scope of the uploaded documents OR if the document search explicitly failed to find relevant information for a general query.
    2.  **Use for General/Current Info:** Ideal for topics like "What's the weather today?", "Who won the recent election?", "Explain the concept of X [if not in documents]", "Latest news about Y".
    3.  **Query Formulation:** Create a good search engine query from the user's question.
    4.  **DO NOT Use For:** Questions about the *content* of uploaded documents, simple calculations, complex math word problems, or package information (use the dedicated tools for those).

    Example Scenarios:
      - User asks: "What is the capital of France?" (and it's unlikely to be in their specific documents) -> Use this tool with `query="capital of France"`.
      - User asks: "Summarize the key points about photosynthesis from my biology textbook PDF." -> DO NOT use this tool. Use `query_uploaded_documents`.
      - After `query_uploaded_documents` fails for "Explain quantum entanglement", User asks "Ok, can you explain it generally?" -> Use this tool with `query="explain quantum entanglement"`.
    """
    global _searx_wrapper, _tool_enabled
    logger.info(f"Web Search (SearXNG) Tool invoked. Query: '{query[:50]}...'")

    if not _tool_enabled or _searx_wrapper is None:
        logger.warning("Attempted to use web search tool, but it is disabled or not initialized.")
        # Raise ToolException to signal the agent the tool failed clearly
        raise ToolException("Web search functionality is currently disabled or unavailable.")

    try:
        results = _searx_wrapper.run(query)
        logger.info(f"SearXNG search returned {len(results)} characters.")
        if not results or results.strip() == "No good results found.": # Check for Searx specific "no results"
             return f"I searched the web for '{query}' but couldn't find relevant results."
        # Return the results fetched by the wrapper
        return results
    except Exception as e:
        logger.error(f"Error running SearXNG search for query '{query}': {e}", exc_info=True)
        # Raise ToolException on runtime errors
        raise ToolException(f"An error occurred while searching the web: {e}")

