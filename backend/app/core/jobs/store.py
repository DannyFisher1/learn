# app/core/jobs/store.py

import logging
import json
import asyncio
from typing import Optional, Dict, Any

# Import Redis library (ensure it's added to requirements.txt)
try:
    import redis.asyncio as redis
except ImportError:
    raise ImportError("Redis library not found. Please install it: pip install redis")

# App imports
from app import config # To get Redis connection details
from app.utils import get_logger

logger = get_logger(__name__)

# --- Module-level Cache for the Singleton Instance ---
_job_store_instance: Optional['RedisJobStore'] = None

class RedisJobStore:
    """
    Provides an async interface for interacting with Redis
    to manage background job data using Redis Hashes.
    """
    _pool: Optional[redis.ConnectionPool] = None
    _redis_url: Optional[str] = None # Store configured URL for comparison

    def __init__(self):
        """
        Initializes the connection pool based on configuration.
        Does not establish connection immediately, pool handles connections lazily.
        """
        # Prevent direct instantiation, use get_job_store_instance()
        if RedisJobStore._pool is not None:
             logger.warning("RedisJobStore already initialized. Use get_job_store_instance().")
             return

        try:
            # Construct Redis URL from config (add default values)
            # Example assumes REDIS_URL is set like "redis://localhost:6379/0"
            redis_url = getattr(config, 'REDIS_URL', 'redis://localhost:6379/0')
            RedisJobStore._redis_url = redis_url # Store for checking later

            logger.info(f"Initializing Redis connection pool for URL: {redis_url}")
            RedisJobStore._pool = redis.ConnectionPool.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True # Decode responses from bytes to strings automatically
            )
            logger.info("Redis connection pool configured.")
        except Exception as e:
            logger.critical(f"Failed to configure Redis connection pool: {e}", exc_info=True)
            RedisJobStore._pool = None # Ensure pool is None on failure
            # Optional: Raise error to prevent app startup if Redis is critical
            # raise RuntimeError(f"Failed to configure Redis: {e}") from e

    async def _get_redis_client(self) -> redis.Redis:
        """Gets a Redis client instance from the connection pool."""
        if RedisJobStore._pool is None:
             logger.error("Redis connection pool is not available.")
             raise ConnectionError("Redis connection pool not initialized.")
        # The client is created from the pool for each operation context usually
        return redis.Redis(connection_pool=RedisJobStore._pool)

    async def initialize_job(self, job_id: str, request_data: Dict[str, Any]) -> None:
        """
        Creates the initial job entry in Redis with 'pending' status.
        Overwrites if job_id already exists.

        Args:
            job_id: The unique identifier for the job.
            request_data: Dictionary containing initial job data (e.g., submitted_at, request).
        """
        if not job_id:
             logger.error("Initialize job called with empty job_id.")
             return
        try:
            async with await self._get_redis_client() as r:
                # Use HSET to store job data in a Redis Hash named job:<job_id>
                job_key = f"job:{job_id}"
                initial_data = {
                    "status": "pending",
                    **request_data # Include submitted_at, request, etc.
                }
                # Serialize complex types (like request dict) if necessary, though HSET handles strings
                # For simplicity, store basic fields directly, complex ones as JSON strings?
                # Let's store the whole thing as JSON for simplicity within the hash for now.
                # Alternative: Store each field separately using HMSET or HSET multiple times.
                await r.hset(job_key, mapping={
                     "data": json.dumps(initial_data)
                 })
                # Optional: Set an expiry time for the job key
                # await r.expire(job_key, timedelta(days=7)) # Example: expire after 7 days
                logger.info(f"Initialized job '{job_key}' in Redis with status 'pending'.")
        except Exception as e:
            logger.error(f"Failed to initialize job '{job_id}' in Redis: {e}", exc_info=True)
            # Optional: Raise exception if initialization is critical
            # raise ConnectionError(f"Failed to initialize job {job_id} in Redis") from e

    async def update_job(self, job_id: str, update_data: Dict[str, Any]) -> None:
        """
        Updates specific fields for a job entry in Redis.

        Args:
            job_id: The unique identifier for the job.
            update_data: Dictionary containing fields and values to update.
                         Values should be suitable for storage (str, int, float, or JSON string).
        """
        if not job_id:
             logger.error("Update job called with empty job_id.")
             return
        if not update_data:
             logger.warning(f"Update job called for '{job_id}' with empty data. No update performed.")
             return

        try:
            async with await self._get_redis_client() as r:
                job_key = f"job:{job_id}"

                # --- Fetch existing data, update, then save ---
                # This avoids overwriting the whole structure if only partial update needed
                existing_data_json = await r.hget(job_key, "data")
                if not existing_data_json:
                     logger.error(f"Cannot update job '{job_key}': Job key not found in Redis.")
                     # Or should we create it here? Depends on desired behavior. Let's error for now.
                     return # Or raise an exception

                try:
                    job_data = json.loads(existing_data_json)
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode existing JSON data for job '{job_key}'. Overwriting with update.")
                    job_data = {} # Start fresh if existing data is corrupt

                job_data.update(update_data) # Merge updates

                # Save updated data back
                await r.hset(job_key, mapping={
                    "data": json.dumps(job_data)
                })
                # --------------------------------------------

                # --- Alternative: Update individual fields using HSET ---
                # Need to serialize non-primitive types if using this approach
                # serialized_updates = {k: json.dumps(v) if isinstance(v, (dict, list)) else v
                #                      for k, v in update_data.items()}
                # await r.hset(job_key, mapping=serialized_updates)
                # --------------------------------------------------------
                logger.info(f"Updated job '{job_key}' in Redis. Fields updated: {list(update_data.keys())}")
        except Exception as e:
            logger.error(f"Failed to update job '{job_id}' in Redis: {e}", exc_info=True)
            # raise ConnectionError(f"Failed to update job {job_id} in Redis") from e

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the full job data dictionary from Redis.

        Args:
            job_id: The unique identifier for the job.

        Returns:
            A dictionary containing the job data, or None if the job is not found or an error occurs.
        """
        if not job_id:
             logger.error("Get job called with empty job_id.")
             return None
        try:
            async with await self._get_redis_client() as r:
                job_key = f"job:{job_id}"
                # Retrieve the single 'data' field containing the JSON string
                job_data_json = await r.hget(job_key, "data")

                if job_data_json:
                    try:
                        # Deserialize the JSON string back into a Python dict
                        job_data = json.loads(job_data_json)
                        logger.debug(f"Retrieved job '{job_key}' from Redis.")
                        return job_data
                    except json.JSONDecodeError as json_err:
                         logger.error(f"Failed to decode JSON data for job '{job_key}': {json_err}. Data: '{job_data_json[:100]}...'")
                         return None # Return None if data is corrupted
                else:
                    logger.warning(f"Job '{job_key}' not found in Redis.")
                    return None
        except Exception as e:
            logger.error(f"Failed to retrieve job '{job_id}' from Redis: {e}", exc_info=True)
            return None

    async def close(self) -> None:
        """Closes the Redis connection pool gracefully."""
        if RedisJobStore._pool:
            logger.info("Closing Redis connection pool...")
            try:
                await RedisJobStore._pool.disconnect()
                logger.info("Redis connection pool closed.")
                RedisJobStore._pool = None
                RedisJobStore._redis_url = None
            except Exception as e:
                logger.error(f"Error closing Redis connection pool: {e}", exc_info=True)

# --- Singleton Instance Getter ---
def get_job_store_instance() -> RedisJobStore:
    """
    Provides a singleton instance of the RedisJobStore, initializing if needed.
    Checks if Redis URL config changed since last init.
    """
    global _job_store_instance
    # Check if config changed since last init
    configured_url = getattr(config, 'REDIS_URL', 'redis://localhost:6379/0')
    if _job_store_instance is not None and RedisJobStore._redis_url != configured_url:
         logger.warning("Redis URL configuration changed. Re-initializing Job Store instance.")
         # Attempt graceful close of old pool if possible? (Might be complex)
         # For simplicity, just nullify the instance to force re-creation.
         _job_store_instance = None
         RedisJobStore._pool = None # Ensure pool is also cleared
         RedisJobStore._redis_url = None

    if _job_store_instance is None:
        logger.info("Creating RedisJobStore singleton instance.")
        _job_store_instance = RedisJobStore()
        # Check if pool failed to initialize during __init__
        if RedisJobStore._pool is None:
             logger.error("RedisJobStore instance created, but pool initialization failed earlier.")
             _job_store_instance = None # Don't return broken instance
             raise RuntimeError("Failed to initialize Redis job store connection pool.")
    return _job_store_instance