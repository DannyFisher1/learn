from __future__ import annotations

import os
from typing import Any, Dict, List # <-- Added List
import json # <-- Added json for potential error formatting

from langchain.tools import tool
# We might not need RedditSearchRun anymore if we call the wrapper directly
# from langchain_community.tools.reddit_search.tool import RedditSearchRun
from langchain_community.utilities.reddit_search import RedditSearchAPIWrapper
from langchain_core.tools import ToolException # <-- Import ToolException for errors

from app.utils import get_logger
from app import config # <-- Import config to check if enabled

logger = get_logger(__name__)

# Keep the helper function as is
def _build_reddit_wrapper(
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    user_agent: str | None = None,
) -> RedditSearchAPIWrapper | None: # <-- Return None if disabled
    """Return a configured RedditSearchAPIWrapper or None if disabled."""

    # Check config flag first
    if not config.REDDIT_ENABLED:
         logger.warning("Reddit tool is disabled via config. Skipping wrapper build.")
         return None

    client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
    client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = user_agent or os.getenv("REDDIT_USER_AGENT")

    if not (client_id and client_secret and user_agent):
        # Log the error but return None, the tool check will handle it
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


# Singleton wrapper instance (can be None if disabled/error)
_REDDIT_WRAPPER_INSTANCE: RedditSearchAPIWrapper | None = _build_reddit_wrapper()


@tool
def search_reddit(
    query: str = "*",
    subreddit: str = "all",
    sort: str = "relevance",
    time_filter: str = "week",
    limit: int = 5,
) -> List[Dict[str, Any]] | str: # <-- CHANGED return type annotation
    """Searches Reddit for posts matching the query and criteria. Use this to find community discussions, opinions, or experiences.

    Args:
        query (str): Keywords to search for. Defaults to '*' (everything).
        subreddit (str): Subreddit name (without 'r/'). Defaults to 'all'. E.g., "python", "MachineLearning".
        sort (str): Sorting method. Options: "relevance", "hot", "top", "new", "comments". Defaults to "relevance".
        time_filter (str): Time period. Options: "all", "day", "hour", "month", "week", "year". Defaults to "week".
        limit (int): Max number of posts to return (1-100). Defaults to 5. Be mindful of result size.

    Returns:
        A list of dictionaries, where each dictionary represents a Reddit post and contains keys like 'title', 'score', 'id', 'subreddit', 'url', 'created_utc', 'body'. Returns an error string if the search fails or the tool is disabled.
    """
    global _REDDIT_WRAPPER_INSTANCE
    logger.info(f"Reddit Search Tool invoked. Query='{query}', Subreddit='{subreddit}', Sort='{sort}', Time='{time_filter}', Limit={limit}")

    if _REDDIT_WRAPPER_INSTANCE is None:
        logger.error("Reddit search called, but the API wrapper is not available (disabled or failed init).")
        # Raise ToolException for the agent
        raise ToolException("Reddit search functionality is currently unavailable due to configuration issues.")

    try:
        # --- Directly call the results method which returns structured data ---
        results: List[Dict[str, Any]] = _REDDIT_WRAPPER_INSTANCE.results(
            query=query,
            limit=limit,
            time_filter=time_filter,
            subreddit=subreddit,
            sort=sort,
        )
        # ---------------------------------------------------------------------

        logger.info(f"Reddit search successful, found {len(results)} posts.")

        # Return the structured list
        return [
            {**post, "post_author": str(post.get("post_author"))}
            for post in results
        ]

    except Exception as exc:
        logger.exception("Reddit search failed during API call: %s", exc)
        # Raise ToolException for the agent
        raise ToolException(f"Reddit search failed: {exc}")