# app/core/ai/agents/tools/reddit_search_tool.py

from __future__ import annotations

import os
import asyncio # <<< Added import
from typing import Any, Dict, List
import json # <-- Kept json import

from langchain.tools import tool
from langchain_community.utilities.reddit_search import RedditSearchAPIWrapper
from langchain_core.tools import ToolException

from app.utils import get_logger
from app import config

logger = get_logger(__name__)

# Helper function _build_reddit_wrapper remains unchanged
def _build_reddit_wrapper(
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    user_agent: str | None = None,
) -> RedditSearchAPIWrapper | None:
    """Return a configured RedditSearchAPIWrapper or None if disabled."""
    if not config.REDDIT_ENABLED:
        logger.warning("Reddit tool is disabled via config. Skipping wrapper build.")
        return None
    client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
    client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = user_agent or os.getenv("REDDIT_USER_AGENT")
    if not (client_id and client_secret and user_agent):
        logger.error(
            "Reddit credentials missing or incomplete. Set REDDIT_CLIENT_ID, "
            "REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT env vars."
        )
        return None
    try:
        wrapper = RedditSearchAPIWrapper(
            reddit_client_id=client_id,
            reddit_client_secret=client_secret,
            reddit_user_agent=user_agent,
        )
        logger.info("RedditSearchAPIWrapper initialized successfully.")
        return wrapper
    except Exception as e:
        logger.error(f"Failed to initialize RedditSearchAPIWrapper: {e}", exc_info=True)
        return None

# Singleton wrapper instance remains unchanged
_REDDIT_WRAPPER_INSTANCE: RedditSearchAPIWrapper | None = _build_reddit_wrapper()


@tool
async def search_reddit( # <<< Changed to async def
    query: str = "*",
    subreddit: str = "all",
    sort: str = "relevance",
    time_filter: str = "week",
    limit: int = 5,
) -> List[Dict[str, Any]]: # <<< Changed return type hint for clarity on success
    """Searches Reddit for posts matching the query and criteria. Use this to find community discussions, opinions, or experiences.

    Args:
        query (str): Keywords to search for. Defaults to '*' (everything).
        subreddit (str): Subreddit name (without 'r/'). Defaults to 'all'. E.g., "python", "MachineLearning".
        sort (str): Sorting method. Options: "relevance", "hot", "top", "new", "comments". Defaults to "relevance".
        time_filter (str): Time period. Options: "all", "day", "hour", "month", "week", "year". Defaults to "week".
        limit (int): Max number of posts to return (1-100). Defaults to 5. Be mindful of result size.

    Returns:
        A list of dictionaries, where each dictionary represents a Reddit post and contains keys like 'post_title', 'post_score', 'post_id', 'post_subreddit', 'post_url', 'post_text', 'post_author'. Raises ToolException if the search fails or the tool is disabled.
    """
    global _REDDIT_WRAPPER_INSTANCE
    logger.info(f"Reddit Search Tool invoked (async). Query='{query}', Subreddit='{subreddit}', Sort='{sort}', Time='{time_filter}', Limit={limit}")

    if _REDDIT_WRAPPER_INSTANCE is None:
        logger.error("Reddit search called, but the API wrapper is not available (disabled or failed init).")
        raise ToolException("Reddit search functionality is currently unavailable due to configuration issues.")

    try:
        # --- Wrap the synchronous API call in asyncio.to_thread ---
        logger.debug("Calling Reddit API wrapper asynchronously via thread...")
        results: List[Dict[str, Any]] = await asyncio.to_thread(
            _REDDIT_WRAPPER_INSTANCE.results, # Pass the method itself
            query=query,                       # Pass arguments
            limit=limit,
            time_filter=time_filter,
            subreddit=subreddit,
            sort=sort,
        )
        # ----------------------------------------------------------

        num_found = len(results)
        logger.info(f"Reddit search successful, found {num_found} posts.")

        # --- Return structured list ---
        # Convert author to string just in case
        return [
            {**post, "post_author": str(post.get("post_author"))}
            for post in results
        ]
        # -----------------------------

    except ToolException: # Re-raise ToolExceptions specifically
        raise
    except Exception as exc:
        logger.exception(f"Reddit search failed during API call or processing: {exc}")
        raise ToolException(f"Reddit search failed: {exc}")