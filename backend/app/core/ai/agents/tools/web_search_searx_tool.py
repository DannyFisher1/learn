# backend/app/core/ai/agents/tools/web_search_searx_tool.py

import logging
import asyncio # <<< Added import
from langchain_community.utilities import SearxSearchWrapper
from langchain_core.tools import ToolException
from langchain.tools import tool
import fake_headers # Keep fake_headers import

from app import config
from app.utils import get_logger

logger = get_logger(__name__)

# Keep fake_headers generation logic
try:
    headers = fake_headers.Headers(headers=True).generate()
except Exception as e:
    logger.error(f"Failed to generate fake headers: {e}. Proceeding without specific headers.")
    headers = {} # Use empty dict as fallback

# Initialize the wrapper *once* if configured
_searx_wrapper = None
_tool_enabled = False

if config.SEARXNG_URL:
    try:
        logger.info(f"Initializing SearxSearchWrapper for host: {config.SEARXNG_URL}")
        _searx_wrapper = SearxSearchWrapper(
            searx_host=config.SEARXNG_URL,
            headers=headers, # Pass generated headers
            unsecure=config.SEARXNG_UNSECURE,
            k=5 # Default number of results to fetch internally if wrapper uses it
        )
        # Optional: Perform a quick test call to check connectivity
        # try:
        #     _searx_wrapper.run("test")
        #     logger.info("SearxSearchWrapper connectivity test successful.")
        # except Exception as test_e:
        #     logger.error(f"SearxSearchWrapper connectivity test failed: {test_e}", exc_info=True)
        #     raise ConnectionError(f"Failed to connect to SearXNG at {config.SEARXNG_URL}") from test_e

        _tool_enabled = True
        logger.info("SearxSearchWrapper initialized successfully.")
    except ToolException: # Catch ToolException from init if raised (e.g., 403)
         raise # Re-raise it to prevent app startup if needed
    except Exception as e:
        logger.error(f"Failed to initialize SearxSearchWrapper: {e}", exc_info=True)
        _searx_wrapper = None
        _tool_enabled = False
else:
    logger.warning("SearXNG URL not configured. Web search tool is disabled.")
    _tool_enabled = False


@tool
async def search_the_web(query: str) -> str: # <<< Changed to async def
    """
    Use this tool ONLY to find real-time information or general knowledge on the internet.
    (Docstring unchanged)
    """
    global _searx_wrapper, _tool_enabled
    logger.info(f"Web Search (SearXNG) Tool invoked (async). Query: '{query[:50]}...'")

    if not _tool_enabled or _searx_wrapper is None:
        logger.warning("Attempted to use web search tool, but it is disabled or not initialized.")
        raise ToolException("Web search functionality is currently disabled or unavailable.")

    try:
        # --- Wrap the synchronous API call in asyncio.to_thread ---
        logger.debug("Calling SearXNG wrapper asynchronously via thread...")
        results = await asyncio.to_thread(_searx_wrapper.run, query)
        # --------------------------------------------------------

        logger.info(f"SearXNG search returned {len(results)} characters.")

        # Check for standard "no results" string from the wrapper
        if results is None or results.strip() == "No good results found.":
             logger.warning(f"SearXNG search for '{query}' returned no relevant results.")
             return f"I searched the web for '{query}' but couldn't find relevant results."

        # Return the results fetched by the wrapper
        return results
    except ToolException: # Re-raise specific ToolExceptions
        raise
    except Exception as e:
        logger.error(f"Error running SearXNG search for query '{query}': {e}", exc_info=True)
        raise ToolException(f"An error occurred while searching the web: {e}")