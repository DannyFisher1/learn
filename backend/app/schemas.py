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


# --- NEW: Job Schemas ---

# Standardized Job Status Enum (can also use Python Enum class)
JOB_STATUS_PENDING = "PENDING"
JOB_STATUS_RUNNING = "RUNNING"
JOB_STATUS_COMPLETED = "COMPLETED"
JOB_STATUS_FAILED = "FAILED"
JOB_STATUS_CANCELED = "CANCELED"

class JobMetadataBase(BaseModel):
    job_id: str
    task_type: str
    status: str = JOB_STATUS_PENDING
    created_at: float # Unix timestamp
    updated_at: float # Unix timestamp
    progress_message: Optional[str] = None
    error_message: Optional[str] = None

class JobStatusResponse(JobMetadataBase):
    input_params: Optional[Dict[str, Any]] = None # Include input for status check

class JobListResponseItem(JobMetadataBase):
     # Maybe only include essential info for list views
     input_summary: Optional[str] = None # e.g., first few chars of request

class JobListResponse(BaseModel):
    jobs: List[JobListResponseItem]
    total: int
    limit: Optional[int] = None
    offset: Optional[int] = None

class JobResultResponse(JobMetadataBase):
    input_params: Optional[Dict[str, Any]] = None
    result_data: Optional[Any] = None # The actual result (e.g., Markdown string, JSON data)

class StartJobResponse(BaseModel):
    job_id: str
    message: str = "Job started successfully."

class CancelJobResponse(BaseModel):
    job_id: str
    status: str # e.g., "CANCEL_REQUESTED", "ALREADY_COMPLETED", "NOT_FOUND"
    message: Optional[str] = None

# Example payload for starting a 'deep_research' job
class StartDeepResearchPayload(BaseModel):
    topic: str = Field(..., description="The main research topic.")
    depth: int = Field(default=2, ge=1, le=5, description="Research depth (e.g., number of refinement rounds).")
    max_sources_per_query: int = Field(default=5, ge=1, le=10, description="Max sources to fetch per individual search query.")
    max_total_sources: int = Field(default=15, ge=1, le=50, description="Max total sources to process for the final report.")
    # Add other relevant parameters like exclude_domains etc.