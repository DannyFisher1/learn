# backend/app/core/ai/agents/tools/web_search_searx_tool.py

import logging
import asyncio
import requests
import json
from typing import List, Dict, Any, Tuple, Optional
from bs4 import BeautifulSoup # Using BeautifulSoup directly for cleaning and snippets

from langchain_core.tools import ToolException
from langchain_core.documents import Document # Keep for potential loader return type
from langchain.tools import tool
# Removed LLM/Chain related imports (ChatOpenAI, ChatPromptTemplate, StrOutputParser, load_summarize_chain)
from langchain_community.document_loaders import AsyncChromiumLoader # Keep for fetching

import fake_headers

from app import config
from app.utils import get_logger

logger = get_logger(__name__)

# --- Configuration Constants ---
SEARXNG_RESULT_LIMIT = config.SEARXNG_SEARCH_LIMIT if hasattr(config, 'SEARXNG_SEARCH_LIMIT') else 5
CONTENT_FETCH_LIMIT = config.CONTENT_SUMMARIZATION_LIMIT if hasattr(config, 'CONTENT_SUMMARIZATION_LIMIT') else 3 # How many URLs to fetch content from
# --- NEW: Snippet & Content Config ---
SNIPPET_TARGET_LENGTH = 250 # Characters for UI preview snippet
MAX_CLEANED_CONTENT_LENGTH = config.WEB_CONTEXT_MAX_CHARS if hasattr(config, 'WEB_CONTEXT_MAX_CHARS') else 4000 # Max chars per page for agent context
# ---------------------------

# --- Fake Headers ---
try:
    _headers = fake_headers.Headers(headers=True).generate()
except Exception as e:
    logger.warning(f"Failed to generate fake headers: {e}. Using default.")
    _headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

# --- Tool Enabled Check ---
_tool_enabled = False
if config.SEARXNG_URL:
    logger.info(f"SearXNG URL ({config.SEARXNG_URL}) is configured.")
    _tool_enabled = True
    # Removed OpenAI API Key check as LLM is no longer used in this tool
    try:
        ping_params = {"q": "test", "format": "json", "engines": "google", "language": "en", "pageno": 1}
        response = requests.get(f"{config.SEARXNG_URL}/search", params=ping_params, headers=_headers, timeout=5)
        response.raise_for_status()
        logger.info("SearXNG connectivity test successful.")
    except requests.exceptions.RequestException as e:
        logger.error(f"SearXNG connectivity test failed for {config.SEARXNG_URL}: {e}")
        logger.warning("Web Search Tool may not function correctly due to SearXNG connectivity issues.")
else:
    logger.warning("SearXNG URL (SEARXNG_URL) not configured. Web Search Tool is disabled.")


# --- Helper Functions ---

# _search_searxng_api (Unchanged - returns List[Dict[str, str]] with url/title)
async def _search_searxng_api(query: str, searxng_url: str, headers: Dict[str, str], limit: int) -> List[Dict[str, str]]:
    """Searches SearXNG and returns list of {'url': url, 'title': title}."""
    params = {"q": query, "format": "json", "language": "en", "safesearch": 1, "pageno": 1}
    sources: List[Dict[str, str]] = []
    try:
        logger.debug(f"Querying SearXNG: {searxng_url}/search with params: {params}")
        response = await asyncio.to_thread(requests.get, f"{searxng_url}/search", params=params, headers=headers, timeout=10)
        response.raise_for_status()
        results_json = response.json()
        raw_results = results_json.get("results", [])
        seen_urls = set()
        for r in raw_results:
            url = r.get("url")
            if url and url.startswith(("http://", "https://")) and url not in seen_urls:
                sources.append({"url": url, "title": r.get("title", "Untitled Source")})
                seen_urls.add(url)
            if len(sources) >= limit: break
        logger.info(f"SearXNG returned {len(sources)} unique sources for query '{query[:30]}...'.")
        return sources
    except Exception as e:
        logger.error(f"Error searching SearXNG: {e}", exc_info=True)
        return []


def _extract_clean_text_and_snippet(html_content: str, target_snippet_length: int, max_content_length: int) -> Tuple[str, str]:
    """
    Uses BeautifulSoup to extract cleaned text and a representative snippet from HTML.
    This is a synchronous function suitable for running in a thread.
    """
    cleaned_text = "Content could not be extracted."
    snippet = "Snippet not available."
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        # Remove common noise tags
        for element in soup(["script", "style", "nav", "footer", "aside", "header", "head", "noscript", "form"]):
            element.extract()

        # Extract main text content (simple approach, can be refined)
        # Join text from common content tags, prioritizing 'article', 'main' if they exist
        main_content_element = soup.find('article') or soup.find('main')
        if main_content_element:
            text_elements = main_content_element.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li'])
            if not text_elements: # Fallback if no specific tags inside main/article
                 text_elements = [main_content_element]
        else: # Fallback if no main/article
             text_elements = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li'])

        # Build text content and snippet simultaneously
        text_builder = []
        snippet_builder = []
        current_snippet_len = 0
        for element in text_elements:
            # Get text, replace multiple whitespace chars with single space
            elem_text = ' '.join(element.get_text(strip=True).split())
            if elem_text:
                text_builder.append(elem_text)
                # Add to snippet if not yet full
                if current_snippet_len < target_snippet_length:
                    needed = target_snippet_length - current_snippet_len
                    # Add separator if snippet already has content
                    sep = " " if current_snippet_len > 0 else ""
                    add_part = sep + elem_text
                    snippet_builder.append(add_part[:needed + len(sep)]) # Add up to needed length
                    current_snippet_len += len(add_part)

        full_cleaned_text = "\n".join(text_builder) # Join paragraphs/elements with newline
        cleaned_text = full_cleaned_text[:max_content_length].strip()
        if len(full_cleaned_text) > max_content_length:
            cleaned_text += "..." # Indicate truncation

        raw_snippet = "".join(snippet_builder).strip()
        snippet = raw_snippet[:target_snippet_length]
        if len(raw_snippet) > target_snippet_length:
             snippet += "..." # Indicate truncation

        if not cleaned_text: cleaned_text = "Content could not be extracted."
        if not snippet: snippet = "Snippet not available."

    except Exception as extract_err:
        logger.warning(f"BeautifulSoup extraction failed: {extract_err}")
        # Return default error messages

    return cleaned_text, snippet

# --- REFACTORED TOOL: search_web_raw ---
@tool
async def search_web_raw(query: str) -> str: # Output is JSON string: List[Dict[str, str]]
    """
    Use this tool to find real-time information or general knowledge from the internet.
    Searches the web and fetches content from relevant pages.
    Input should be a concise search query string.
    Returns a JSON string containing a list of source objects. Each object has:
    'title': Page title.
    'url': Page URL.
    'snippet': A short text preview from the page.
    'cleaned_content': The main extracted text content from the page (up to a limit).
    The CALLER (main agent) is responsible for synthesizing an answer from the 'cleaned_content'.
    """
    global _tool_enabled, _headers
    tool_name = "search_web_raw" # Use new name internally for logging
    logger.info(f"Refactored Web Search Tool ('{tool_name}') invoked. Query: '{query[:50]}...'")

    if not _tool_enabled: raise ToolException("Web search functionality is disabled.")

    final_results: List[Dict[str, str]] = []
    try:
        # --- STEP 1: Search SearXNG ---
        initial_sources = await _search_searxng_api(query, config.SEARXNG_URL, _headers, SEARXNG_RESULT_LIMIT)
        if not initial_sources:
            logger.warning(f"'{tool_name}': No URLs found by SearXNG for query: '{query}'")
            # Return empty list as JSON string, agent should handle this
            return json.dumps([])

        # --- STEP 2: Fetch Content Concurrently ---
        sources_to_fetch = initial_sources[:CONTENT_FETCH_LIMIT]
        urls_to_fetch = [src['url'] for src in sources_to_fetch]
        titles_map = {src['url']: src['title'] for src in sources_to_fetch} # Map URL back to title

        if not urls_to_fetch:
             logger.warning(f"'{tool_name}': No URLs selected to fetch for query: '{query}'")
             return json.dumps([])

        logger.info(f"'{tool_name}': Attempting to fetch content from {len(urls_to_fetch)} URLs.")
        try:
            import playwright # Ensure dependency
            loader = AsyncChromiumLoader(urls_to_fetch)
            # Set user agent if needed: loader.browser_args = [f"--user-agent={_headers['User-Agent']}"]
            raw_html_docs: List[Document] = await loader.aload() # Fetch in parallel
        except ImportError:
             logger.error("Playwright is not installed.")
             raise ToolException("A required component (Playwright) for web fetching is missing.")
        except Exception as fetch_err:
             logger.error(f"'{tool_name}': Error during AsyncChromiumLoader fetch: {fetch_err}", exc_info=True)
             # Proceed with any successfully fetched docs if possible, otherwise return empty
             raw_html_docs = [] # Assume total failure if loader raises exception

        # --- STEP 3: Clean Content and Extract Snippets in Parallel ---
        tasks = []
        source_url_map = {} # Keep track of which doc corresponds to which original URL
        for doc in raw_html_docs:
            if doc and doc.page_content and doc.metadata.get("source"):
                url = doc.metadata["source"]
                # Run sync cleaning function in thread pool executor
                task = asyncio.to_thread(_extract_clean_text_and_snippet, doc.page_content, SNIPPET_TARGET_LENGTH, MAX_CLEANED_CONTENT_LENGTH)
                tasks.append(task)
                source_url_map[task] = url # Map task back to URL

        processed_results = await asyncio.gather(*tasks, return_exceptions=True)

        # --- STEP 4: Assemble Final Results ---
        for i, result in enumerate(processed_results):
            task = tasks[i]
            url = source_url_map[task]
            if isinstance(result, Exception):
                logger.error(f"'{tool_name}': Failed to process content for {url}: {result}")
            elif isinstance(result, tuple) and len(result) == 2:
                cleaned_content, snippet = result
                # Only include if content extraction was successful
                if cleaned_content != "Content could not be extracted.":
                    final_results.append({
                        "title": titles_map.get(url, "Untitled Source"),
                        "url": url,
                        "snippet": snippet,
                        "cleaned_content": cleaned_content
                    })
            else:
                 logger.error(f"'{tool_name}': Unexpected result type from processing for {url}: {type(result)}")


        logger.info(f"'{tool_name}': Successfully processed content for {len(final_results)} out of {len(urls_to_fetch)} URLs.")
        return json.dumps(final_results, default=str) # Return list of processed sources as JSON

    except ToolException as e: # Re-raise ToolExceptions
        logger.error(f"'{tool_name}': ToolException during execution for '{query}': {e}", exc_info=True)
        raise
    except Exception as e: # Catch unexpected errors
        logger.error(f"'{tool_name}': Unexpected error during execution for query '{query}': {e}", exc_info=True)
        # Return empty list as JSON string to indicate failure
        return json.dumps([])

# Remove the old summarize_document_content tool if it's fully replaced by this logic
# Or keep it if it serves a distinct purpose (summarizing entire specific files)

# Ensure the old _load_document_chunks_by_filename is removed if no longer needed by other tools