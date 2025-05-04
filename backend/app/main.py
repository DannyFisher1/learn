# app/main.py

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# App imports
from app import config # Direct config access needed for root endpoint/status
from app.utils import get_logger
# Import core components/services needed for lifespan startup checks
from app.core.components import vector_store
from app.core.ai.agents.executor import get_agent_executor

# --- Import API Routers ---
from app.api import chat as chat_router
from app.api import documents as documents_router
from app.api import providers as providers_router

logger = get_logger(__name__)

# --- Lifespan for Startup/Shutdown ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup logic e.g., warm-up, checks."""
    logger.info("--- Starting FastAPI Application ---")
    try:
        # Perform initial checks/warm-up using imported functions
        logger.info("Verifying vector store connection...")
        vector_store.get_vectorstore() # Initialize/check vector store connection
        logger.info("Vector store connection verified.")

        logger.info("Initializing Agent Executor...")
        get_agent_executor() # Pre-initialize agent executor
        logger.info("Agent Executor initialized.")

        logger.info("--- Application Startup Complete ---")
    except Exception as e:
        logger.critical(f"Application startup failed during initialization: {e}", exc_info=True)
        # Depending on severity, you might want the app to fail startup.
        # Re-raising the exception here would likely stop FastAPI startup.
        # raise
    yield
    # Cleanup logic can go here if needed on shutdown
    logger.info("--- FastAPI Application Shutting Down ---")


# --- FastAPI App Initialization ---
app = FastAPI(
    title="Modular AI Interaction API", # Updated title
    description="API for interacting with an AI agent, managing documents, and providers.",
    version="1.3.0", # Incremented version for refactor
    lifespan=lifespan # Use the lifespan manager
)

# --- CORS Configuration ---
# TODO: Make origins configurable via environment variables?
origins = ["http://localhost:3000"] # Allow frontend origin
# Allow other origins if needed, e.g., staging or production frontend URLs
# origins.append(os.getenv("FRONTEND_URL", "")) # Example

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in origins if origin], # Filter out empty origins
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods
    allow_headers=["*"], # Allows all headers
)
logger.info(f"CORS enabled for origins: {origins}")

# --- Include API Routers ---
# Include routers from the api module, setting prefixes if not done in the router file
app.include_router(chat_router.router) # Assuming prefix is not set in router file
app.include_router(documents_router.router) # Assuming prefix "/documents" is set in router file
app.include_router(providers_router.router) # Assuming prefix "/config/provider" is set in router file

logger.info("API routers included.")

# --- Root Endpoint ---
@app.get("/", tags=["Status"])
async def read_root():
    """Root endpoint providing basic API status and active provider."""
    # Use ACTIVE_AI_PROVIDER for current runtime status
    return {
        "status": "ok",
        "message": "Modular AI Interaction API is running.",
        "active_ai_provider": config.ACTIVE_AI_PROVIDER.upper()
     }

