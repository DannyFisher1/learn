# backend/app/core/ai/agents/tools/web_search_searx_tool.py

import logging
import asyncio
import requests # For direct SearXNG API calls
from typing import List, Dict, Any

from langchain_core.tools import ToolException
from langchain_core.documents import Document # For type hinting
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import AsyncChromiumLoader
from langchain_community.document_transformers import BeautifulSoupTransformer
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

import fake_headers

from app import config
from app.utils import get_logger

logger = get_logger(__name__)

# --- Configuration Constants ---
# Number of search results to fetch from SearXNG
SEARXNG_RESULT_LIMIT = config.SEARXNG_SEARCH_LIMIT if hasattr(config, 'SEARXNG_SEARCH_LIMIT') else 5
# Number of fetched pages to summarize
CONTENT_SUMMARIZATION_LIMIT = config.CONTENT_SUMMARIZATION_LIMIT if hasattr(config, 'CONTENT_SUMMARIZATION_LIMIT') else 3
# LLM model for summarization
SUMMARIZATION_MODEL_NAME = config.OPENAI_MODEL_NAME if hasattr(config, 'OPENAI_MODEL_NAME') else "gpt-4o-mini"
# Tags to extract for BeautifulSoupTransformer
BS_TAGS_TO_EXTRACT = ["p", "article", "main", "h1", "h2", "h3", "li"]


# --- Fake Headers ---
try:
    _headers = fake_headers.Headers(headers=True).generate()
    logger.info("Fake headers generated successfully for SearXNG requests.")
except Exception as e:
    logger.error(f"Failed to generate fake headers: {e}. Proceeding with a default User-Agent.")
    _headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

# --- Tool Enabled Check ---
_tool_enabled = False
if config.SEARXNG_URL and config.OPENAI_API_KEY:
    logger.info(f"SearXNG URL ({config.SEARXNG_URL}) and OpenAI API Key are configured.")
    logger.info(f"Web Search & Summarization Tool will use model: {SUMMARIZATION_MODEL_NAME}")
    _tool_enabled = True
    # Optional: Test SearXNG connectivity here if desired
    try:
        # A light ping-like request or a simple search
        ping_params = {"q": "test", "format": "json", "engines": "google", "language": "en", "pageno": 1}
        response = requests.get(
            f"{config.SEARXNG_URL}/search",
            params=ping_params,
            headers=_headers,
            timeout=5 # Short timeout for a ping
        )
        response.raise_for_status()
        logger.info("SearXNG connectivity test successful.")
    except requests.exceptions.RequestException as e:
        logger.error(f"SearXNG connectivity test failed for {config.SEARXNG_URL}: {e}")
        logger.warning("Web Search & Summarization Tool may not function correctly due to SearXNG connectivity issues.")
        # Depending on strictness, you might set _tool_enabled = False here
        # _tool_enabled = False
else:
    if not config.SEARXNG_URL:
        logger.warning("SearXNG URL (SEARXNG_URL) not configured.")
    if not config.OPENAI_API_KEY:
        logger.warning("OpenAI API Key (OPENAI_API_KEY) not configured.")
    logger.warning("Web Search & Summarization Tool is disabled.")


# --- Helper Functions ---

async def _search_searxng_api(query: str, searxng_url: str, headers: Dict[str, str], limit: int) -> List[str]:
    """
    Performs a search using the SearXNG API and returns a list of URLs.
    This is a blocking function, intended to be run in a thread.
    """
    params = {
        "q": query,
        "format": "json",
        "language": "en", # Consider making this configurable
        "safesearch": 1,  # Consider making this configurable
        "pageno": 1
    }
    try:
        logger.debug(f"Querying SearXNG: {searxng_url}/search with params: {params}")
        response = await asyncio.to_thread(
            requests.get,
            f"{searxng_url}/search",
            params=params,
            headers=headers,
            timeout=10 # seconds
        )
        response.raise_for_status()
        results_json = response.json()
        urls = [r["url"] for r in results_json.get("results", []) if "url" in r and r["url"].startswith(("http://", "https://"))]
        logger.info(f"SearXNG returned {len(urls)} URLs for query '{query[:30]}...'. Taking top {limit}.")
        return urls[:limit]
    except requests.exceptions.Timeout:
        logger.error(f"SearXNG search timed out for query: {query}")
        return []
    except requests.exceptions.HTTPError as e:
        logger.error(f"SearXNG search HTTP error: {e.response.status_code} for query: {query}. Response: {e.response.text[:200]}")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Error searching with SearXNG API: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Unexpected error during SearXNG search: {e}", exc_info=True)
        return []

async def _fetch_and_clean_documents(urls: List[str]) -> List[Document]:
    """
    Asynchronously fetches content from URLs and cleans it using BeautifulSoup.
    """
    if not urls:
        return []
    logger.info(f"Fetching content from {len(urls)} URLs: {urls}")
    try:
        # AsyncChromiumLoader needs Playwright installed (playwright install --with-deps chromium)
        # It can be slow if many pages or heavy pages are loaded.
        loader = AsyncChromiumLoader(urls)
        raw_docs = await loader.aload() # Use aload for async
        
        # Filter out docs that might have failed to load (None or empty content)
        loaded_docs = [doc for doc in raw_docs if doc and doc.page_content.strip()]
        if not loaded_docs:
            logger.warning("No content successfully loaded from provided URLs.")
            return []

        logger.info(f"Successfully loaded content from {len(loaded_docs)}/{len(urls)} URLs.")
        
        transformer = BeautifulSoupTransformer()
        # Extract specific tags to get cleaner text content
        cleaned_docs = transformer.transform_documents(
            loaded_docs,
            tags_to_extract=BS_TAGS_TO_EXTRACT,
            unwanted_tags=["script", "style", "nav", "footer", "aside"],
            remove_lines=True,
            remove_blank_lines=True
        )
        logger.info(f"Cleaned content from {len(cleaned_docs)} documents.")
        return cleaned_docs
    except ImportError:
        logger.error("Playwright or related dependencies for AsyncChromiumLoader not found. "
                     "Please install with 'pip install playwright && playwright install --with-deps chromium'")
        raise ToolException("Web content fetching component is not properly configured (Playwright missing).")
    except Exception as e:
        logger.error(f"Error loading/cleaning documents: {e}", exc_info=True)
        # Return empty list or re-raise specific errors as ToolException
        return []


async def _summarize_content_with_llm(docs: List[Document], query: str) -> str:
    """
    Summarizes the content of the provided documents in relation to the original query.
    """
    if not docs:
        return "No content was available to summarize."

    combined_content = "\n\n".join([f"Source URL: {doc.metadata.get('source', 'N/A')}\nContent:\n{doc.page_content}" for doc in docs])
    
    # Limit content size to avoid exceeding token limits (approximate)
    # A more robust solution would use a tokenizer.
    # Max chars roughly: 1 token ~ 4 chars. 128k model = 512k chars. Let's be safer.
    # GPT-4o-mini has 128k context.
    # Max input for gpt-4o-mini is typically less than full context window to leave room for output.
    # E.g., if model has 128k context, aim for input < 100k tokens.
    # Let's set a character limit, e.g., 200,000 characters for combined_content sent to LLM.
    max_chars_for_llm = config.LLM_SUMMARIZATION_MAX_CHARS if hasattr(config, 'LLM_SUMMARIZATION_MAX_CHARS') else 200000
    if len(combined_content) > max_chars_for_llm:
        logger.warning(f"Combined content length ({len(combined_content)} chars) exceeds limit ({max_chars_for_llm} chars). Truncating.")
        combined_content = combined_content[:max_chars_for_llm] + "\n\n[Content Truncated]"

    prompt_template = ChatPromptTemplate.from_template(
        """You are an expert research assistant.
        Analyze the following web content, which was retrieved based on the user's query.
        Provide a concise, factual, and neutral summary of the key information relevant to the query.
        Synthesize insights from multiple sources if applicable.
        Focus on directly answering or addressing the user's query.
        If the content seems irrelevant or insufficient to answer the query, state that.
        Do NOT make up information. If the context doesn't provide an answer, say so.
        Cite the source URLs if they are distinct and relevant for specific pieces of information, like [Source: URL].

        User Query: {query}

        Web Content:
        ---
        {content}
        ---

        Concise Summary:"""
    )

    try:
        llm = ChatOpenAI(
            model=SUMMARIZATION_MODEL_NAME,
            temperature=0.2, # Lower temperature for more factual summaries
            openai_api_key=config.OPENAI_API_KEY,
            max_tokens=config.LLM_SUMMARIZATION_MAX_TOKENS if hasattr(config, 'LLM_SUMMARIZATION_MAX_TOKENS') else 1000 # Max output tokens for summary
        )
        chain = prompt_template | llm | StrOutputParser()
        
        logger.info(f"Requesting summarization from LLM for query '{query[:30]}...' using model {SUMMARIZATION_MODEL_NAME}.")
        summary = await chain.ainvoke({"query": query, "content": combined_content})
        logger.info(f"LLM summarization successful for query '{query[:30]}...'. Length: {len(summary)}")
        return summary
    except Exception as e:
        logger.error(f"Error during LLM summarization: {e}", exc_info=True)
        return "An error occurred while trying to summarize the web content."


@tool
async def search_and_summarize_web(query: str) -> str:
    """
    Use this tool to find real-time information or general knowledge from the internet and provide a summary.
    It searches the web, fetches relevant pages, and then summarizes their content in relation to your query.
    Input should be a concise search query.
    """
    global _tool_enabled, _headers
    logger.info(f"Web Search & Summarization Tool invoked. Query: '{query[:50]}...'")

    if not _tool_enabled:
        logger.warning("Attempted to use web search & summarization tool, but it is disabled.")
        # It's better to raise a ToolException so the agent knows the tool failed.
        raise ToolException(
            "Web search and summarization functionality is currently disabled "
            "due to missing SEARXNG_URL or OPENAI_API_KEY configuration."
        )
    if not config.SEARXNG_URL: # Should be caught by _tool_enabled, but as a safeguard
        raise ToolException("SearXNG URL is not configured for the web search tool.")
    if not config.OPENAI_API_KEY: # Safeguard
        raise ToolException("OpenAI API Key is not configured for the summarization part of the web tool.")

    try:
        # --- STEP 1: Search SearXNG for URLs ---
        logger.debug(f"Step 1: Searching SearXNG for query: {query}")
        urls = await _search_searxng_api(query, config.SEARXNG_URL, _headers, SEARXNG_RESULT_LIMIT)

        if not urls:
            logger.warning(f"No URLs found by SearXNG for query: '{query}'")
            return f"I searched the web for '{query}' but could not find any relevant web pages."

        logger.info(f"Found {len(urls)} URLs: {urls[:CONTENT_SUMMARIZATION_LIMIT]}")

        # --- STEP 2: Fetch and Clean Document Content ---
        # Limit the number of documents to fetch/process to avoid excessive load/time
        urls_to_fetch = urls[:CONTENT_SUMMARIZATION_LIMIT]
        logger.debug(f"Step 2: Fetching and cleaning content from up to {len(urls_to_fetch)} URLs.")
        
        # Ensure Playwright is available
        try:
            import playwright
        except ImportError:
            logger.error("Playwright is not installed. Cannot fetch web content. "
                         "Run 'pip install playwright && playwright install --with-deps chromium'")
            return "I can't access web pages because a required component (Playwright) is missing. Please ask the administrator to install it."

        documents = await _fetch_and_clean_documents(urls_to_fetch)

        if not documents:
            logger.warning(f"No content could be extracted from the top URLs for query: '{query}'")
            return f"I found web pages for '{query}' but was unable to extract their content for summarization."

        # --- STEP 3: Summarize Content with LLM ---
        logger.debug(f"Step 3: Summarizing content from {len(documents)} documents for query: {query}")
        summary = await _summarize_content_with_llm(documents, query)

        if not summary or summary.strip().lower() == "no content was available to summarize." or \
           "error occurred while trying to summarize" in summary.lower():
            logger.warning(f"Summarization failed or yielded no useful content for query: '{query}'")
            # Provide a more graceful fallback if summarization itself fails
            # You might return raw snippets if summary fails, or just a targeted message.
            # For now, let's stick to a message.
            return f"I found content for '{query}' but encountered an issue summarizing it. The raw information might be too complex or an error occurred."

        logger.info(f"Successfully generated summary for query: '{query}'. Length: {len(summary)} chars.")
        return summary

    except ToolException as e: # Re-raise ToolExceptions directly
        logger.error(f"ToolException during web search & summarization for '{query}': {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during web search & summarization for query '{query}': {e}", exc_info=True)
        raise ToolException(f"An unexpected error occurred while searching and summarizing the web for '{query}': {str(e)}")

# Example of how you might add configuration to app/config.py:
"""
# In app/config.py (add these or similar)
import os
from dotenv import load_dotenv

load_dotenv()

# ... other configs ...

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080") # Your SearXNG instance
SEARXNG_UNSECURE = os.getenv("SEARXNG_UNSECURE", "False").lower() in ("true", "1", "t") # if using http

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini") # Or "gpt-3.5-turbo", "gpt-4-turbo" etc.

# Optional: Fine-tune tool behavior
SEARXNG_SEARCH_LIMIT = int(os.getenv("SEARXNG_SEARCH_LIMIT", "5")) # How many URLs SearXNG should return
CONTENT_SUMMARIZATION_LIMIT = int(os.getenv("CONTENT_SUMMARIZATION_LIMIT", "3")) # How many of those URLs to fetch content from
LLM_SUMMARIZATION_MAX_CHARS = int(os.getenv("LLM_SUMMARIZATION_MAX_CHARS", "200000")) # Max input characters to LLM for summarization
LLM_SUMMARIZATION_MAX_TOKENS = int(os.getenv("LLM_SUMMARIZATION_MAX_TOKENS", "1000")) # Max output tokens for summary from LLM
"""