# Refactoring Explanation: `chat_service.py`

The original `chat_service.py` file was refactored to improve code organization, maintainability, and separation of concerns. Its responsibilities were split into several new files and a new sub-package.

## New File Structure:

```
backend/app/
├── services/
│   ├── __init__.py
│   ├── chat/                 # NEW: Chat-specific services
│   │   ├── __init__.py
│   │   ├── events.py         # NEW: SSE Event formatting
│   │   ├── streaming.py      # NEW: Streaming chat logic
│   │   └── non_streaming.py  # NEW: Non-streaming chat logic
│   ├── jobs_service.py     # NEW: Background job handling
│   ├── document_service.py # Existing
│   └── provider_service.py # Existing
├── errors.py               # NEW: Custom Error classes
└── ... (other components)
```

## File Descriptions:

1.  **`backend/app/errors.py`**:
    *   **Purpose:** Defines custom application-specific exception classes.
    *   **Contents:** Includes `AgentNotReadyError` (previously in `chat_service.py`) and can host other errors like `ConfigurationError`. This centralizes error definitions.

2.  **`backend/app/services/jobs_service.py`**:
    *   **Purpose:** Handles logic related to background jobs, specifically the project generation workflow in this case.
    *   **Contents:** Contains `run_project_gen_in_background`, `get_job_status`, and `initialize_project_generation_job`. It also encapsulates the import and dummy definition for `execute_project_generation_workflow`. This separates potentially long-running background task logic from the main chat request/response flow.

3.  **`backend/app/services/chat/` (Sub-package)**:
    *   **Purpose:** Groups all services directly related to chat interactions.
    *   **`__init__.py`**: Makes the `chat` directory a Python package.
    *   **`events.py`**:
        *   **Purpose:** Contains helper functions specifically for formatting Server-Sent Events (SSE) for both the custom UI events and the debugger events.
        *   **Contents:** `yield_ui_event` and `prepare_debugger_event`. Centralizing formatting logic makes it easier to manage the SSE structure.
    *   **`streaming.py`**:
        *   **Purpose:** Contains the core logic for handling streaming chat requests (`/ask-stream`).
        *   **Contents:** `handle_chat_request_stream`. This function now imports helpers from `events.py` and potentially calls `jobs_service.py` if project generation is triggered. It focuses solely on managing the LangGraph stream, processing state changes, handling tool results for streaming UI events, and yielding data.
    *   **`non_streaming.py`**:
        *   **Purpose:** Contains the logic for handling traditional, non-streaming chat requests (`/ask`).
        *   **Contents:** `handle_chat_request`. It manages the non-streaming LangGraph invocation, processes the final state, parses tool results if necessary for the final answer, and handles background job triggers by calling `jobs_service.py`.

4.  **`backend/app/api/chat.py` (Updated)**:
    *   **Purpose:** Defines the FastAPI routes (`/ask`, `/ask-stream`).
    *   **Changes:** Imports for the handler functions (`handle_chat_request`, `handle_chat_request_stream`) were updated to point to their new locations in `app.services.chat.non_streaming` and `app.services.chat.streaming`.

## Benefits:

*   **Improved Readability:** Smaller files are easier to read and understand.
*   **Clearer Responsibilities:** Each file now has a more focused purpose.
*   **Easier Maintenance:** Changes related to streaming, non-streaming, events, or jobs can be made in their respective isolated files.
*   **Better Testability:** Individual components (like event formatting or job handling) can potentially be tested more easily in isolation.

This refactoring sets a cleaner foundation for future development.