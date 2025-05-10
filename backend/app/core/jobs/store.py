# app/core/jobs/store.py

import logging
import json
import asyncio
import time
from typing import Optional, Dict, Any, List, Set, Tuple

try:
    import redis.asyncio as redis
except ImportError:
    raise ImportError("Redis library not found. Please install it: pip install redis")

from app import config
from app.utils import get_logger
from app.schemas import JOB_STATUS_PENDING, JOB_STATUS_RUNNING, JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELED # Import statuses

logger = get_logger(__name__)

_job_store_instance: Optional['RedisJobStore'] = None

# --- Redis Key Prefixes ---
JOB_HASH_PREFIX = "job:"
ACTIVE_JOB_SET_KEY = "jobs:active" # Set of IDs for PENDING/RUNNING jobs
COMPLETED_JOB_SET_KEY = "jobs:completed"
FAILED_JOB_SET_KEY = "jobs:failed"
CANCELED_JOB_SET_KEY = "jobs:canceled"
JOB_HISTORY_SET_KEY = "jobs:history" # Sorted set by timestamp for history? Or union of completed/failed/canceled

# TTL for job data (e.g., 7 days)
JOB_TTL_SECONDS = 60 * 60 * 24 * 7

class RedisJobStore:
    _pool: Optional[redis.ConnectionPool] = None
    _redis_url: Optional[str] = None

    def __init__(self):
        if RedisJobStore._pool is not None: return # Already initialized

        try:
            redis_url = getattr(config, 'REDIS_URL', 'redis://localhost:6379/0')
            RedisJobStore._redis_url = redis_url
            logger.info(f"Initializing Redis connection pool: {redis_url}")
            RedisJobStore._pool = redis.ConnectionPool.from_url(redis_url, encoding="utf-8", decode_responses=True)
            logger.info("Redis connection pool configured.")
        except Exception as e:
            logger.critical(f"Failed to configure Redis connection pool: {e}", exc_info=True)
            RedisJobStore._pool = None

    async def _get_redis_client(self) -> redis.Redis:
        if RedisJobStore._pool is None: raise ConnectionError("Redis connection pool not initialized.")
        return redis.Redis(connection_pool=RedisJobStore._pool)

    def _get_job_key(self, job_id: str) -> str:
        return f"{JOB_HASH_PREFIX}{job_id}"

    async def _update_status_sets(self, r: redis.Redis, job_id: str, old_status: Optional[str], new_status: str):
        """Helper to manage job IDs in status-based sets."""
        job_key = self._get_job_key(job_id)
        # Remove from old status set if applicable
        if old_status:
            if old_status in [JOB_STATUS_PENDING, JOB_STATUS_RUNNING]: await r.srem(ACTIVE_JOB_SET_KEY, job_key)
            elif old_status == JOB_STATUS_COMPLETED: await r.srem(COMPLETED_JOB_SET_KEY, job_key)
            elif old_status == JOB_STATUS_FAILED: await r.srem(FAILED_JOB_SET_KEY, job_key)
            elif old_status == JOB_STATUS_CANCELED: await r.srem(CANCELED_JOB_SET_KEY, job_key)

        # Add to new status set
        if new_status in [JOB_STATUS_PENDING, JOB_STATUS_RUNNING]: await r.sadd(ACTIVE_JOB_SET_KEY, job_key)
        elif new_status == JOB_STATUS_COMPLETED: await r.sadd(COMPLETED_JOB_SET_KEY, job_key)
        elif new_status == JOB_STATUS_FAILED: await r.sadd(FAILED_JOB_SET_KEY, job_key)
        elif new_status == JOB_STATUS_CANCELED: await r.sadd(CANCELED_JOB_SET_KEY, job_key)

    async def initialize_job(self, job_id: str, task_type: str, input_params: Dict[str, Any]) -> None:
        """Creates the initial job entry in Redis with PENDING status."""
        if not job_id: raise ValueError("Job ID cannot be empty")
        try:
            async with await self._get_redis_client() as r:
                job_key = self._get_job_key(job_id)
                now = time.time()
                job_data = {
                    "job_id": job_id, # Store ID also within hash for easier retrieval
                    "task_type": task_type,
                    "status": JOB_STATUS_PENDING,
                    "created_at": now,
                    "updated_at": now,
                    "input_params": json.dumps(input_params), # Store complex input as JSON string
                    "progress_message": "Job queued.",
                    "result_data": None,
                    "error_message": None
                }
                # Use HMSET (via hset mapping) for better efficiency
                await r.hset(job_key, mapping={k: v for k, v in job_data.items() if v is not None})
                await r.expire(job_key, JOB_TTL_SECONDS)
                # Add to active set
                await self._update_status_sets(r, job_id, None, JOB_STATUS_PENDING)
                logger.info(f"Initialized job '{job_key}' in Redis.")
        except Exception as e:
            logger.error(f"Failed to initialize job '{job_id}' in Redis: {e}", exc_info=True)
            raise ConnectionError(f"Failed to initialize job {job_id}") from e

    async def update_job(self, job_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates specific fields for a job entry in Redis."""
        if not job_id: raise ValueError("Job ID cannot be empty")
        if not update_data: return True # Nothing to update

        try:
            async with await self._get_redis_client() as r:
                job_key = self._get_job_key(job_id)

                # Get current status before update to manage sets correctly
                old_status = await r.hget(job_key, "status")

                # Prepare updates, ensuring complex types are stringified
                updates_to_save = {}
                for k, v in update_data.items():
                    if isinstance(v, (dict, list)): updates_to_save[k] = json.dumps(v)
                    elif v is not None: updates_to_save[k] = v

                updates_to_save["updated_at"] = time.time() # Always update timestamp

                if not updates_to_save: return True # No valid fields to update

                await r.hset(job_key, mapping=updates_to_save)
                # Ensure TTL is refreshed on update
                await r.expire(job_key, JOB_TTL_SECONDS)

                # Update status sets if status changed
                new_status = update_data.get("status")
                if new_status and old_status != new_status:
                     await self._update_status_sets(r, job_id, old_status, new_status)

                logger.info(f"Updated job '{job_key}' in Redis. Fields: {list(updates_to_save.keys())}")
                return True
        except Exception as e:
            logger.error(f"Failed to update job '{job_id}' in Redis: {e}", exc_info=True)
            return False # Indicate failure

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the full job data dictionary from Redis."""
        if not job_id: return None
        try:
            async with await self._get_redis_client() as r:
                job_key = self._get_job_key(job_id)
                job_data_redis = await r.hgetall(job_key)

                if not job_data_redis:
                    logger.warning(f"Job '{job_key}' not found in Redis.")
                    return None

                # Deserialize specific fields known to be JSON
                job_data = {}
                for k, v in job_data_redis.items():
                    if k in ["input_params", "result_data"] and v:
                         try: job_data[k] = json.loads(v)
                         except json.JSONDecodeError: logger.error(f"Corrupt JSON in field '{k}' for job {job_id}"); job_data[k] = None
                    elif k in ["created_at", "updated_at"] and v:
                         try: job_data[k] = float(v)
                         except ValueError: logger.error(f"Corrupt timestamp in field '{k}' for job {job_id}"); job_data[k] = 0.0
                    else: job_data[k] = v # Keep others as strings (status, messages etc.)

                logger.debug(f"Retrieved job '{job_key}' from Redis.")
                return job_data
        except Exception as e:
            logger.error(f"Failed to retrieve job '{job_id}' from Redis: {e}", exc_info=True)
            return None

    async def get_jobs_by_status(self, statuses: List[str], limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        """Retrieves jobs matching given statuses using status sets."""
        job_keys: Set[str] = set()
        total_count = 0
        try:
            async with await self._get_redis_client() as r:
                # Union the relevant status sets
                set_keys_to_scan = []
                if JOB_STATUS_PENDING in statuses or JOB_STATUS_RUNNING in statuses: set_keys_to_scan.append(ACTIVE_JOB_SET_KEY)
                if JOB_STATUS_COMPLETED in statuses: set_keys_to_scan.append(COMPLETED_JOB_SET_KEY)
                if JOB_STATUS_FAILED in statuses: set_keys_to_scan.append(FAILED_JOB_SET_KEY)
                if JOB_STATUS_CANCELED in statuses: set_keys_to_scan.append(CANCELED_JOB_SET_KEY)

                if not set_keys_to_scan: return [], 0

                # Use SUNION to get all job keys matching statuses
                # Note: SUNION can be heavy if sets are massive. Consider alternatives for extreme scale.
                all_matching_keys = await r.sunion(set_keys_to_scan)
                total_count = len(all_matching_keys)
                # Apply pagination (on the client side after getting all keys, less efficient but simpler than Redis SORT)
                paginated_keys = sorted(list(all_matching_keys))[offset : offset + limit] # Sort for consistent pagination

                jobs = []
                if paginated_keys:
                     # Fetch data for paginated keys
                     # Use pipeline for efficiency if fetching many jobs
                     pipe = r.pipeline()
                     for key in paginated_keys:
                          pipe.hgetall(key)
                     results = await pipe.execute()

                     for i, job_data_redis in enumerate(results):
                          if job_data_redis:
                               job_data = {}
                               job_id = paginated_keys[i].replace(JOB_HASH_PREFIX, "")
                               for k, v in job_data_redis.items():
                                   # Deserialize relevant fields (input_params only for list view?)
                                   if k == "input_params" and v:
                                        try: job_data[k] = json.loads(v)
                                        except: job_data[k] = {} # Or just summary
                                   elif k in ["created_at", "updated_at"] and v:
                                        try: job_data[k] = float(v)
                                        except: job_data[k] = 0.0
                                   else: job_data[k] = v
                               # Create input summary for list view
                               job_data["input_summary"] = str(job_data.get("input_params", {}))[:100] + "..."
                               jobs.append(job_data)

                return jobs, total_count
        except Exception as e:
            logger.error(f"Failed to retrieve jobs by status {statuses}: {e}", exc_info=True)
            return [], 0

    async def cancel_job(self, job_id: str) -> Tuple[bool, str]:
        """Attempts to mark a job as canceled. Actual task termination depends on queue implementation."""
        if not job_id: return False, "No Job ID provided."
        try:
            async with await self._get_redis_client() as r:
                job_key = self._get_job_key(job_id)
                current_status = await r.hget(job_key, "status")

                if not current_status: return False, "Job not found."
                if current_status not in [JOB_STATUS_PENDING, JOB_STATUS_RUNNING]:
                     return False, f"Job cannot be canceled (status: {current_status})."

                # Update status in Redis
                success = await self.update_job(job_id, {"status": JOB_STATUS_CANCELED, "progress_message": "Cancellation requested."})
                if success:
                     # *** Placeholder: Add logic here to signal the actual task queue worker to stop ***
                     # This depends heavily on Celery/Arq/RQ API
                     logger.info(f"Job {job_id} marked as CANCELED in Redis. Actual task termination depends on queue.")
                     # ***********************************************************************************
                     return True, "Cancellation requested."
                else:
                     return False, "Failed to update job status in store."
        except Exception as e:
            logger.error(f"Failed to request cancellation for job '{job_id}': {e}", exc_info=True)
            return False, "Internal error during cancellation request."
    
    async def delete_job(self, job_id: str) -> bool:
        """Deletes a job entirely from Redis, including its hash and from status sets."""
        if not job_id:
            logger.warning("Attempted to delete job with no ID provided.")
            return False
        
        job_key_to_delete = self._get_job_key(job_id) # e.g., job:your-id
        job_id_for_set = job_id # For old sets that might have stored job_id directly (if any, legacy)
                                # Modern sets store job_key_to_delete
        
        try:
            async with await self._get_redis_client() as r:
                # Get current job data to find its status for set removal
                job_data = await r.hgetall(job_key_to_delete)
                
                if not job_data:
                    logger.warning(f"Job '{job_key_to_delete}' not found for deletion.")
                    # Try to remove from sets anyway, in case of orphaned IDs
                    # This part depends on what was actually added to your sets.
                    # Assuming sets store the full `job:id` key:
                    await r.srem(ACTIVE_JOB_SET_KEY, job_key_to_delete)
                    await r.srem(COMPLETED_JOB_SET_KEY, job_key_to_delete)
                    await r.srem(FAILED_JOB_SET_KEY, job_key_to_delete)
                    await r.srem(CANCELED_JOB_SET_KEY, job_key_to_delete)
                    return False # Job hash didn't exist

                status = job_data.get("status")

                # Use a pipeline for atomic deletion from hash and sets
                pipe = r.pipeline()
                pipe.delete(job_key_to_delete) # Delete the job's HASH

                # Remove from status-specific sets (assuming sets store the full `job:id` key)
                if status:
                    if status in [JOB_STATUS_PENDING, JOB_STATUS_RUNNING]:
                        pipe.srem(ACTIVE_JOB_SET_KEY, job_key_to_delete)
                    elif status == JOB_STATUS_COMPLETED:
                        pipe.srem(COMPLETED_JOB_SET_KEY, job_key_to_delete)
                    elif status == JOB_STATUS_FAILED:
                        pipe.srem(FAILED_JOB_SET_KEY, job_key_to_delete)
                    elif status == JOB_STATUS_CANCELED:
                        pipe.srem(CANCELED_JOB_SET_KEY, job_key_to_delete)
                else:
                    # If status is unknown, try removing from all known sets just in case
                    logger.warning(f"Job '{job_key_to_delete}' had no status field; attempting to remove from all status sets.")
                    pipe.srem(ACTIVE_JOB_SET_KEY, job_key_to_delete)
                    pipe.srem(COMPLETED_JOB_SET_KEY, job_key_to_delete)
                    pipe.srem(FAILED_JOB_SET_KEY, job_key_to_delete)
                    pipe.srem(CANCELED_JOB_SET_KEY, job_key_to_delete)

                await pipe.execute()
                logger.info(f"Successfully deleted job '{job_key_to_delete}' from Redis.")
                return True
        except Exception as e:
            logger.error(f"Failed to delete job '{job_key_to_delete}' from Redis: {e}", exc_info=True)
            return False
    async def close(self) -> None:
        if RedisJobStore._pool:
            logger.info("Closing Redis connection pool...")
            try: await RedisJobStore._pool.disconnect()
            except Exception as e: logger.error(f"Error closing Redis pool: {e}", exc_info=True)
            finally: RedisJobStore._pool = None; RedisJobStore._redis_url = None

# --- Singleton Instance Getter ---
def get_job_store_instance() -> RedisJobStore:
    global _job_store_instance
    configured_url = getattr(config, 'REDIS_URL', 'redis://localhost:6379/0')
    if _job_store_instance is not None and RedisJobStore._redis_url != configured_url:
         logger.warning("Redis URL configuration changed. Re-initializing Job Store instance.")
         # Close old pool if possible (best effort)
         if _job_store_instance._pool:
             try: asyncio.ensure_future(_job_store_instance.close()) # Close async in background
             except: pass
         _job_store_instance = None; RedisJobStore._pool = None; RedisJobStore._redis_url = None

    if _job_store_instance is None:
        logger.info("Creating RedisJobStore singleton instance.")
        _job_store_instance = RedisJobStore()
        if RedisJobStore._pool is None:
             _job_store_instance = None # Prevent returning broken instance
             raise RuntimeError("Failed to initialize Redis job store connection pool.")
    return _job_store_instance