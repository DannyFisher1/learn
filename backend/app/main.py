# backend/app/main.py

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from typing import Optional

# App imports
from app import config # Import config early for settings
from app.utils import get_logger # Setup logging first potentially
# Import core components/services needed for lifespan startup checks
from app.core.components import vector_store
from app.core.ai.agents.executor import get_langgraph_app
# --- Import Job Store for Lifespan ---
from app.core.jobs.store import get_job_store_instance, RedisJobStore # Import class and getter
# --------------------------------------

# Setup logger (assuming get_logger configures it)
logger = get_logger(__name__)

# --- Import API Routers ---
# Use consistent naming convention if possible
from app.api import chat as chat_api_router
from app.api import documents as documents_api_router
from app.api import providers as providers_api_router
from app.api import jobs as jobs_api_router # Import the new jobs router
from app.api import graph as graph_api_router # Import the graph router

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

class SuppressLogsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/jobs/active":
            logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        else:
            logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        return await call_next(request)
    

# --- Lifespan for Startup/Shutdown ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup logic e.g., warm-up, checks, resource init."""
    # --- Store initialized resources for potential cleanup ---
    job_store_instance: Optional[RedisJobStore] = None
    # -------------------------------------------------------
    logger.info("--- Starting FastAPI Application ---")
    try:
        # --- Initialize Job Store (Redis Pool) ---
        logger.info("Initializing Redis Job Store connection pool...")
        # Calling the getter initializes the singleton pool if not already done
        job_store_instance = get_job_store_instance() # Throws RuntimeError if pool fails
        logger.info("Redis Job Store connection pool configured.")
        # -------------------------------------------

        # --- Initialize Vector Store ---
        # Wrap in try-except if vector store might not be available but app should still start
        try:
            logger.info("Verifying vector store connection...")
            vector_store.get_vectorstore(force_reload_embeddings=False) # Use False on startup
            logger.info("Vector store connection verified.")
        except Exception as vs_err:
            logger.error(f"Vector store initialization failed: {vs_err}", exc_info=True)
            # Decide if this is critical for startup
        # -----------------------------

        # --- Initialize Agent Executor ---
        # Wrap in try-except if agent might not be available but app should still start
        try:
             logger.info("Initializing Agent Executor...")
             get_langgraph_app() # Throws RuntimeError if agent fails
             logger.info("Agent Executor initialized.")
        except Exception as agent_err:
             logger.error(f"Agent Executor initialization failed: {agent_err}", exc_info=True)
             # Decide if this is critical for startup
        # -------------------------------

        logger.info("--- Application Startup Complete ---")
    except Exception as startup_err:
        # Catch errors specifically from get_job_store_instance or get_langgraph_app
        logger.critical(f"Application startup failed during critical initialization: {startup_err}", exc_info=True)
        # Attempt cleanup even on startup failure
        if job_store_instance:
             try:
                 logger.info("Closing Redis pool due to startup error...")
                 await job_store_instance.close()
             except Exception as close_err:
                 logger.error(f"Error closing Redis pool during startup error handling: {close_err}")
        # Re-raise the exception to potentially halt FastAPI startup process
        raise startup_err from startup_err
    # --- Application runs after yield ---
    yield
    # --- Cleanup logic on shutdown ---
    logger.info("--- FastAPI Application Shutting Down ---")
    if job_store_instance: # Use the instance captured during startup
        try:
            logger.info("Closing Redis Job Store connection pool...")
            await job_store_instance.close()
            logger.info("Redis Job Store connection pool closed.")
        except Exception as e:
            logger.error(f"Error closing Redis Job Store connection pool during shutdown: {e}", exc_info=True)
    # Add other cleanup here if needed (e.g., closing other connections)


# --- FastAPI App Initialization ---
app = FastAPI(
    title="LearnMate AI Platform API", # Updated title
    description="API for managing documents, triggering AI workflows (chat, research, generation), and tracking background jobs.",
    version="1.1.0", # Incremented version for Job System feature
    lifespan=lifespan # Use the lifespan manager
)

# --- CORS Configuration ---
# Read allowed origins from environment variable, fallback to default dev ports
origins_str = getattr(config, "CORS_ALLOWED_ORIGINS", "http://localhost:3000")
origins = [origin.strip() for origin in origins_str.split(',') if origin.strip()]

if not origins:
    logger.warning("No CORS origins specified via CORS_ALLOWED_ORIGINS. Defaulting to 'http://localhost:3000'.")
    origins = ["http://localhost:3000"]

# Allow all origins if specifically configured (Use '*' carefully, mainly for dev)
if getattr(config, "ALLOW_ALL_ORIGINS", False):
    logger.warning("ALLOW_ALL_ORIGINS is True. Allowing all origins for CORS (Development Setting).")
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info(f"CORS enabled for origins: {origins}")

app.add_middleware(SuppressLogsMiddleware)

# --- Include API Routers ---
# Ensure prefixes are defined within the router files themselves
app.include_router(chat_api_router.router, tags=["Chat"])
app.include_router(documents_api_router.router, tags=["Documents"])
app.include_router(providers_api_router.router, tags=["Configuration"])
app.include_router(jobs_api_router.router, tags=["Background Jobs"]) # Include the new jobs router
app.include_router(graph_api_router.router, tags=["Agent Graph"]) # Include graph router
logger.info("API routers included: Chat, Documents, Providers, Jobs, Graph.")

# --- Root Endpoint ---
@app.get("/", tags=["Status"])
async def read_root():
    """Root endpoint providing basic API status."""
    # Consider adding more status checks here (e.g., Redis ping, VectorDB status)
    return {
        "status": "ok",
        "message": "LearnMate AI Platform API is running.",
        "active_ai_provider": getattr(config, "ACTIVE_AI_PROVIDER", "UNKNOWN").upper()
     }

# --- Optional: Run directly with uvicorn (for local dev without docker-compose/run.py) ---
# if __name__ == "__main__":
#     import uvicorn
#     host = getattr(config, "HOST", "0.0.0.0")
#     port = getattr(config, "PORT", 9000)
#     reload = getattr(config, "RELOAD", True)
#     log_level = getattr(config, "LOG_LEVEL", "info").lower()
#     logger.info(f"Starting Uvicorn server: Host={host}, Port={port}, Reload={reload}, LogLevel={log_level}")
#     uvicorn.run("app.main:app", host=host, port=port, reload=reload, log_level=log_level)