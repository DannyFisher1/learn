# app/main.py

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# App imports
from app import config
from app.utils import get_logger
# Import core components/services needed for lifespan startup checks
from app.core.components import vector_store
from app.core.ai.agents.executor import get_langgraph_app
# --- Import Job Store for Lifespan ---
from app.core.jobs.store import get_job_store_instance # <<< Import job store getter
# --------------------------------------

logger = get_logger(__name__)

# --- Import API Routers ---
from app.api import chat as chat_router
from app.api import documents as documents_router
from app.api import providers as providers_router
from app.api import jobs as jobs_router
from app.api import graph as graph_router

# --- Lifespan for Startup/Shutdown ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup logic e.g., warm-up, checks, resource init."""
    # --- Store initialized resources for potential cleanup ---
    job_store_instance = None
    # -------------------------------------------------------
    logger.info("--- Starting FastAPI Application ---")
    try:
        # --- Initialize Job Store (Redis Pool) ---
        logger.info("Initializing Redis Job Store connection pool...")
        # Calling the getter initializes the singleton pool if not already done
        job_store_instance = get_job_store_instance()
        logger.info("Redis Job Store connection pool configured.")
        # -------------------------------------------

        # --- Initialize Vector Store ---
        logger.info("Verifying vector store connection...")
        vector_store.get_vectorstore()
        logger.info("Vector store connection verified.")
        # -----------------------------

        # --- Initialize Agent Executor ---
        logger.info("Initializing Agent Executor...")
        get_langgraph_app()
        logger.info("Agent Executor initialized.")
        # -------------------------------

        logger.info("--- Application Startup Complete ---")
    except Exception as e:
        logger.critical(f"Application startup failed during initialization: {e}", exc_info=True)
        # Optionally close any resources that *did* initialize successfully before exiting
        if job_store_instance:
             try:
                 logger.info("Closing Redis pool due to startup error...")
                 await job_store_instance.close()
             except Exception as close_err:
                 logger.error(f"Error closing Redis pool during error handling: {close_err}")
        # Decide whether to re-raise to halt FastAPI startup
        # raise e
    # --- Application runs after yield ---
    yield
    # --- Cleanup logic on shutdown ---
    logger.info("--- FastAPI Application Shutting Down ---")
    if job_store_instance:
        try:
            logger.info("Closing Redis Job Store connection pool...")
            await job_store_instance.close()
            logger.info("Redis Job Store connection pool closed.")
        except Exception as e:
            logger.error(f"Error closing Redis Job Store connection pool during shutdown: {e}", exc_info=True)
    # Add other cleanup here if needed (e.g., closing other connections)


# --- FastAPI App Initialization ---
app = FastAPI(
    title="Modular AI Interaction API",
    description="API for interacting with an AI agent, managing documents, providers, and background jobs.",
    version="1.5.0", # Incremented version for Redis Job Store feature
    lifespan=lifespan # Use the updated lifespan manager
)

# --- CORS Configuration ---
origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, http://chroma:6000")
origins = [origin.strip() for origin in origins_str.split(',') if origin.strip()]

if not origins:
    logger.warning("No CORS origins specified. Defaulting to 'http://localhost:3000'. Frontend might not connect if running elsewhere.")
    origins = ["http://localhost:3000"] # Provide a default if env var is empty

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info(f"CORS enabled for origins: {origins}")

# --- Include API Routers ---
app.include_router(chat_router.router)
app.include_router(documents_router.router) # Assumes prefix="/documents" in router file
app.include_router(providers_router.router) # Assumes prefix="/config/provider" in router file
app.include_router(jobs_router.router)      # Assumes prefix="/jobs" in router file
app.include_router(graph_router.router)    # Assumes prefix="/graph" in router file
logger.info("API routers included: Chat, Documents, Providers, Jobs.")

# --- Root Endpoint ---
@app.get("/", tags=["Status"])
async def read_root():
    """Root endpoint providing basic API status and active provider."""
    return {
        "status": "ok",
        "message": "Modular AI Interaction API is running.",
        "active_ai_provider": config.ACTIVE_AI_PROVIDER.upper()
     }