from pydantic import BaseModel,Field
from typing import List, Optional, Literal, Dict, Any


class AskRequest(BaseModel):
    question: str
    chat_history: Optional[List[dict]] = None # To potentially handle conversation history [6]
    filenames: Optional[List[str]] = Field(None, description="Optional: List of filenames for specific documents to query.")
    tag_filter: Optional[str] = Field(None, description="Optional: Tag/category (e.g., 'homework', 'textbook') to filter the document query.") # <<< NEW



class AskResponse(BaseModel):
    answer: str
    source_documents: Optional[List[Dict[str, Any]]] = []
    intermediate_steps: Optional[List[Dict[str, Any]]] = None

class UploadResponse(BaseModel):
    filename: str
    message: str

class SetProviderRequest(BaseModel):
    provider: Literal['ollama', 'openai'] = Field(..., description="The AI provider to switch to ('ollama' or 'openai')")

# Schema for the response confirming the change (or current status)
class ProviderStatusResponse(BaseModel):
    current_provider: str
    message: str

class DocumentDetail(BaseModel):
    filename: str
    tag: Optional[str] = None
    file_type: Optional[str] = None
    # Could add more details later, like upload date, chunk count etc.

class DocumentListResponse(BaseModel):
    documents: List[DocumentDetail]


# class StreamChunkAction(BaseModel):
#     tool: str
#     tool_input: Any
#     log: str

# class StreamChunkData(BaseModel):
#     action: Optional[StreamChunkAction] = None
#     observation: Optional[Any] = None
#     final_answer_chunk: Optional[str] = None # Chunk of the final answer text
#     error: Optional[str] = None

# class StreamChunk(BaseModel):
#     # Types based on astream_log output structure (can be customized)
#     type: Literal["agent_start", "tool_start", "tool_end", "agent_finish", "llm_chunk", "error"]
#     data: Optional[Dict[str, Any]] = None # Raw data associated with the event type
#     log: Optional[str] = None # Optional raw log message or simplified info