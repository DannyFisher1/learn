# app/schemas.py

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
import time # <<< Add import for default factory

# --- Existing Schemas ---

class AskRequest(BaseModel):
    question: str
    chat_history: Optional[List[dict]] = None
    filenames: Optional[List[str]] = Field(None, description="Optional: List of filenames for specific documents to query.")
    tag_filter: Optional[str] = Field(None, description="Optional: Tag/category (e.g., 'homework', 'textbook') to filter the document query.")

class AskResponse(BaseModel):
    answer: str
    source_documents: Optional[List[Dict[str, Any]]] = Field(default_factory=list) # Use factory for default empty list
    intermediate_steps: Optional[List[Dict[str, Any]]] = None

class UploadResponse(BaseModel):
    filename: str
    message: str

class SetProviderRequest(BaseModel):
    provider: Literal['ollama', 'openai'] = Field(..., description="The AI provider to switch to ('ollama' or 'openai')")

class ProviderStatusResponse(BaseModel):
    current_provider: str
    message: str

class DocumentDetail(BaseModel):
    filename: str
    tag: Optional[str] = None
    file_type: Optional[str] = None

class DocumentListResponse(BaseModel):
    documents: List[DocumentDetail]


# --- NEW Job Status Schema ---

class JobStatusResponse(BaseModel):
    """Response model for background job status."""
    job_id: str
    status: Literal["pending", "running", "completed", "failed", "unknown"] = Field(default="unknown", description="Current status of the background job.")
    submitted_at: float = Field(default_factory=time.time, description="Timestamp when the job was submitted.")
    started_at: Optional[float] = Field(None, description="Timestamp when the job processing started.")
    ended_at: Optional[float] = Field(None, description="Timestamp when the job processing ended.")
    duration_seconds: Optional[float] = Field(None, description="Total duration of the job execution in seconds.")
    request: Optional[str] = Field(None, description="Original request that triggered the job (e.g., project description).")
    result_message: Optional[str] = Field(None, description="Success message (e.g., path to output). Populated when status is 'completed'.")
    error_message: Optional[str] = Field(None, description="Error details if the job failed. Populated when status is 'failed'.")
    output_path: Optional[str] = Field(None, description="Path to generated project output, if successful and applicable.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                    "status": "completed",
                    "submitted_at": 1678886400.0,
                    "started_at": 1678886401.5,
                    "ended_at": 1678886521.8,
                    "duration_seconds": 120.3,
                    "request": "Create a simple flask app",
                    "result_message": "Success: Project generation finished in 120.30 seconds!\nOutput Location: /app/data/generated_projects/simple_flask_app_20230315_132201",
                    "error_message": None,
                    "output_path": "/app/data/generated_projects/simple_flask_app_20230315_132201"
                },
                {
                    "job_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                    "status": "failed",
                    "submitted_at": 1678887000.0,
                    "started_at": 1678887001.0,
                    "ended_at": 1678887015.3,
                    "duration_seconds": 14.3,
                    "request": "Generate a complex AI model",
                    "result_message": None,
                    "error_message": "An unexpected error occurred during project generation: ValueError('Missing required parameter')",
                    "output_path": None
                },
                 {
                    "job_id": "b2c3d4e5-f6a7-8901-2345-67890abcdef0",
                    "status": "running",
                    "submitted_at": 1678887100.0,
                    "started_at": 1678887100.5,
                    "ended_at": None,
                    "duration_seconds": None,
                    "request": "Build a full-stack application",
                    "result_message": None,
                    "error_message": None,
                    "output_path": None
                }
            ]
        }
    }

# --- Removed old commented-out stream schemas ---
# (Keep them if you plan to add more structured stream events later)