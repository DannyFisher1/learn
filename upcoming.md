Okay, let's map out a detailed requirements document for the next major evolution of LearnMate, focusing on transforming it into a workflow-driven platform with deep research capabilities and a revamped UI.

---

**Requirements Document: LearnMate Platform Evolution - Phase 1**

**1. Vision & Goal:**

*   **Vision:** Evolve LearnMate from a conversational chat interface into an interactive, workflow-driven analytical workspace. Users should be able to initiate complex, asynchronous tasks (like deep research), monitor their progress, and interact with structured results within a dedicated environment.
*   **Phase 1 Goal:** Implement the foundational UI structure for the new platform, introduce a robust asynchronous task management system, and deliver the first complex workflow: "Deep Research".

**2. High-Level Objectives:**

*   **Redesign UI:** Implement a multi-pane layout (Sidebar, Conversation/Input, Workspace/Output) moving away from a simple chat-bubble interface.
*   **Asynchronous Task Management:** Create a system for initiating, tracking, managing (canceling), and viewing results of background tasks/workflows.
*   **Implement "Deep Research" Workflow:** Develop a multi-step backend process for comprehensive web research that runs asynchronously.
*   **Structured Output Display:** Design the Workspace pane to display complex results beyond simple text (e.g., formatted reports, potentially data).
*   **Shift Interaction Model:** Introduce explicit ways to trigger defined workflows beyond just conversational prompts.

**3. Detailed Requirements:**

**3.1. Overall UI/UX Redesign (IDE/Workspace Concept)**

*   **REQ-UI-001:** Implement a primary three-pane layout using Flexbox/Grid:
    *   **Left Pane (Sidebar):** Collapsible, dedicated to task/job management and potentially other navigation/context elements later. Initial width ~250-300px.
    *   **Center Pane (Conversation/Input):** Primary area for user input and the chronological view of interactions/workflow initiations. Occupies the main central area.
    *   **Right Pane (Workspace/Output):** Dedicated area for displaying detailed results, visualizations, code output, or expanded context related to a selected task or conversation turn. Initial width ~40-50% of remaining space after sidebar.
*   **REQ-UI-002:** Implement a resizable vertical divider between the Center and Right panes.
*   **REQ-UI-003:** Style the Conversation Pane:
    *   Move away from chat bubbles.
    *   Display user inputs and AI responses (including steps, sources, context, suggestions) as distinct "blocks" or "cards" within the scrollable feed.
    *   Use clear visual separators (borders, background shades, spacing) between turns.
*   **REQ-UI-004:** Apply a professional, clean, and modern visual theme (typography, colors, spacing) consistent with an analytical tool or IDE aesthetic. Consider subtle background textures/gradients.
*   **REQ-UI-005:** Ensure layout is responsive, gracefully handling smaller screen sizes (e.g., collapsing sidebar, stacking panes if necessary).

**3.2. Asynchronous Task Management & Sidebar**

*   **REQ-BACKEND-JOB-001:** Implement a persistent Job Store (e.g., using existing Redis instance).
    *   Store job metadata: `job_id`, `user_id` (if multi-user), `task_type` (e.g., "deep_research", "summarize_doc"), `status` (pending, running, processing_step_X, completed, failed, canceled), `created_at`, `updated_at`, `input_params`, `progress_message`, `result_location` (or result data if small), `error_message`.
*   **REQ-BACKEND-JOB-002:** Define standardized Job Statuses: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELED`. Consider adding granular `PROCESSING_<STEP_NAME>` statuses for detailed progress.
*   **REQ-BACKEND-JOB-003:** Implement robust background task execution using a dedicated Task Queue (e.g., Celery, Arq, RQ) integrated with FastAPI. Move long-running workflows (Deep Research, Project Gen) off simple `BackgroundTasks`.
*   **REQ-BACKEND-API-001:** Create new API endpoints:
    *   `POST /jobs/{task_type}/start`: Accepts task-specific input payload, initializes job in store, queues the background task, returns `{ job_id: string }`.
    *   `GET /jobs/status/{job_id}`: Returns current status, progress message, and metadata for a specific job.
    *   `GET /jobs/result/{job_id}`: Returns the final result payload (e.g., report content, data) for a completed job. Requires authentication/authorization.
    *   `POST /jobs/cancel/{job_id}`: Attempts to cancel a running job (requires task queue support for cancellation). Returns success/failure status.
    *   `GET /jobs/active`: Returns a list of jobs for the current user with status `PENDING` or `RUNNING`.
    *   `GET /jobs/history`: Returns a list of completed/failed/canceled jobs for the user (paginated).
*   **REQ-BACKEND-SSE-001 (Optional but recommended):** Implement an SSE endpoint `GET /jobs/status-stream` that pushes real-time status updates for active jobs belonging to the authenticated user.
*   **REQ-UI-SIDEBAR-001:** Implement the collapsible Sidebar UI component.
*   **REQ-UI-SIDEBAR-002:** Fetch and display active jobs (`/jobs/active`) in a dedicated section of the sidebar upon initial load and potentially refresh periodically or via SSE.
*   **REQ-UI-SIDEBAR-003:** Create a `JobItem.tsx` component to render individual jobs in the sidebar list. Display:
    *   Job title/summary.
    *   Current status text (`progress_message` from backend).
    *   Visual progress indicator (spinner for running, check for completed, X for failed). A determinate progress bar can be added later if backend provides %.
    *   "Cancel" button for running jobs (calls `/jobs/cancel/{job_id}`).
    *   "View Results" button for completed jobs (fetches `/jobs/result/{job_id}` and signals the Workspace pane to display).
    *   Indicator/button for failed jobs (potentially show error details on click/hover).
*   **REQ-UI-SIDEBAR-004:** Implement polling (`/jobs/status/{job_id}`) or SSE (`/jobs/status-stream`) logic in `page.tsx` to update the status of active jobs displayed in the sidebar.
*   **REQ-UI-SIDEBAR-005 (Optional):** Add a section for "Job History" fetched from `/jobs/history`.

**3.3. "Deep Research" Workflow**

*   **REQ-WORKFLOW-DR-001:** Define the trigger mechanism (e.g., `/research <topic>` command in input OR dedicated UI form launched from a button/menu).
*   **REQ-WORKFLOW-DR-002:** Define input parameters (e.g., `topic: string`, `depth: int (1-5?)`, `max_sources: int`, `exclude_domains: list[str]`).
*   **REQ-BACKEND-DR-001:** Implement the `/jobs/deep_research/start` API endpoint.
*   **REQ-BACKEND-DR-002:** Implement the asynchronous background task/workflow for deep research:
    *   **Step 1: Initial Broad Search:** Use `search_web_raw` with the initial topic. Update job status.
    *   **Step 2: Result Analysis & Refinement:** Use LLM to analyze initial source titles/snippets/content, identify key sub-topics, and generate 3-5 refined search queries. Update job status.
    *   **Step 3: Iterative Deeper Search:** Loop 1-N times (based on `depth` param?):
        *   Perform `search_web_raw` for each refined query in parallel. Update job status.
        *   Aggregate unique URLs/content.
    *   **Step 4: Content Aggregation & Cleaning:** Fetch content for unique relevant URLs (up to `max_sources`). Clean HTML, potentially filter duplicates/boilerplate. Update job status.
    *   **Step 5: Synthesis:** Use a capable LLM with a dedicated "report generation" prompt, feeding it the aggregated cleaned content and the original user topic. Instruct it to produce a structured Markdown report (e.g., with sections, summaries, key findings). Update job status.
    *   **Step 6: Finalize:** Store the generated Markdown report and associated source list (title, url, snippet) in the Job Store. Mark job as `COMPLETED`.
*   **REQ-AGENT-DR-001:** No direct agent/tool changes needed *if* the workflow runs entirely separately. However, the *main agent* might need to be aware of how to *trigger* this workflow (e.g., recognize the `/research` command and call the API).
*   **REQ-UI-WORKSPACE-001:** Implement rendering logic in the Workspace pane to display the fetched Markdown report from a completed "Deep Research" job, including rendering sources with popovers.

**3.4. Workspace Pane Enhancements**

*   **REQ-UI-WORKSPACE-002:** Implement state management in `page.tsx` to control the content displayed in the Workspace pane (e.g., `workspaceContent: { type: 'report' | 'viz' | 'code' | 'placeholder', data: any } | null`).
*   **REQ-UI-WORKSPACE-003:** Create a `WorkspacePane.tsx` component that dynamically renders different views based on the `workspaceContent` state (e.g., `ReportViewer`, `ChartViewer`, `CodeOutputViewer`). Initially, implement `ReportViewer` using `ReactMarkdown`.
*   **REQ-UI-WORKSPACE-004:** Clicking the "View Results" button on a completed job in the sidebar should trigger fetching the result and setting the `workspaceContent` state to display it.

**4. Non-Functional Requirements:**

*   **NFR-001 (Error Handling):** Workflows and API calls must handle errors gracefully, update job status to `FAILED`, store error messages, and report failures clearly in the UI sidebar.
*   **NFR-002 (Cancellation):** Implement cancellation support in the task queue and backend logic for long-running workflows.
*   **NFR-003 (Performance):** Optimize background workflows using asynchronous operations (`asyncio.gather` for parallel fetches/processing where appropriate).
*   **NFR-004 (Scalability):** Utilize a proper task queue for background jobs to handle potential load.
*   **NFR-005 (Logging):** Ensure detailed logging with Job IDs throughout the backend workflow execution for debugging.

**5. Future Considerations (Out of Scope for Phase 1):**

*   Interactive visualizations in the Workspace pane.
*   Code execution sandbox and output display.
*   More workflow types (data analysis, document comparison, etc.).
*   Saving/sharing/exporting workflow results.
*   Visual workflow builder (Node-based UI).
*   Real-time collaboration features.

**6. Implementation Phasing Suggestion:**

1.  **Foundation:** Implement basic Sidebar UI, Job Store (Redis), Task Queue setup, basic Job API endpoints (`/start`, `/status`, `/result`).
2.  **UI Layout:** Implement the 3-pane layout in `page.tsx`.
3.  **Sidebar Integration:** Connect Sidebar to fetch/display active/completed jobs and handle "View Results" click (initially just logging the result).
4.  **Deep Research Backend:** Implement the multi-step Deep Research workflow logic in the background task queue, ensuring it updates the Job Store status.
5.  **Workspace Display:** Implement the `WorkspacePane.tsx` and `ReportViewer` to display the fetched Markdown report.
6.  **Workflow Trigger:** Implement the `/research` command or UI form to trigger the workflow via the API.
7.  **Refinements:** Add cancellation, detailed progress updates via SSE/polling, error handling polish.

---

This detailed plan provides a clear roadmap for transforming LearnMate. It's a significant undertaking, but tackling it phase by phase, starting with the asynchronous job infrastructure and the UI layout, is achievable.