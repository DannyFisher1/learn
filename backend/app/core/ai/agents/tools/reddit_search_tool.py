from __future__ import annotations

import os
from typing import Any, Dict

from langchain.tools import tool
from langchain_community.tools.reddit_search.tool import (
    RedditSearchRun,
    RedditSearchSchema,
)
from langchain_community.utilities.reddit_search import RedditSearchAPIWrapper

from app.utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helper: build a single reusable API wrapper (avoids re‑auth each call)
# ---------------------------------------------------------------------------

def _build_reddit_wrapper(
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    user_agent: str | None = None,
) -> RedditSearchAPIWrapper:
    """Return a configured RedditSearchAPIWrapper.

    Falls back to environment variables if explicit args are not provided.
    Raises ValueError if any credential is missing.
    """

    client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
    client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = user_agent or os.getenv("REDDIT_USER_AGENT")

    if not (client_id and client_secret and user_agent):
        raise ValueError(
            "Reddit credentials missing. Set REDDIT_CLIENT_ID, "
            "REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT env vars."
        )

    return RedditSearchAPIWrapper(
        reddit_client_id=client_id,
        reddit_client_secret=client_secret,
        reddit_user_agent=user_agent,
    )


# Singleton wrapper instance -------------------------------------------------

_REDDIT_SEARCH_RUNNER = RedditSearchRun(api_wrapper=_build_reddit_wrapper())


# ---------------------------------------------------------------------------
# Public LangChain tool  -----------------------------------------------------


@tool
def search_reddit(
    query: str = "*",
    subreddit: str = "all",
    sort: str = "relevance",
    time_filter: str = "week",
    limit: int = 5,
) -> str:
    """
        **Accepted JSON fields** (all optional unless noted):
    - `query` *(str)*          – search keywords (defaults to "*")
    - `subreddit` *(str)*      – subreddit name, eg. "python"
    - `sort` *(str)*           – one of "relevance", "hot", "top", "new", "comments"
    - `time_filter` *(str)*    – "all", "day", "hour", "month", "week", "year"
    - `limit` *(int)*          – max posts to return (≤1000)

    **Example**::
        }
            {
            "params": {
                "subreddit": "LangChain",
                "sort": "new",
                "limit": 5
            }
            }

    Returns a formatted string summarising the matched posts, ready for the
    agent to consume.
    """
    params = {
        "query": query,
        "subreddit": subreddit,
        "sort": sort,
        "time_filter": time_filter,
        "limit": str(limit),
    }

    try:
        logger.debug("Searching Reddit with params=%s", params)
        result = _REDDIT_SEARCH_RUNNER.run(tool_input=params)
        logger.debug("Reddit search completed")
        return result
    except Exception as exc:
        logger.exception("Reddit search failed: %s", exc)
        return f"Reddit search failed: {exc}"