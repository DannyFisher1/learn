// learn/lib/api.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9000';

// --- Core Interfaces ---

export interface AgentAction { tool?: string; tool_input?: any; log?: string; }
export interface IntermediateStep { action: AgentAction | string; observation: any; }

// --- Source & Context Types ---
export interface Source { title: string; url: string; snippet?: string; } // For Web Sources
export interface RagSource { source: string; page: number | string } // For Legacy/Simple RAG display

// Define the structure for detailed RAG context chunks
export interface RagContextDocument {
  filename: string;
  page: string | number; // Page number can be string or number
  snippet: string;       // The actual retrieved text chunk
}
// --- End Source & Context Types ---


// --- Updated Message Interface ---
export interface Message {
  sender: 'user' | 'ai';
  text: string;
  id?: string;
  // UI State
  statusSteps?: string[];
  webSources?: Source[]; // Web search results
  ragSources?: RagSource[]; // Optional: Keep if you still use simple RAG source display elsewhere
  retrievedContext?: RagContextDocument[]; // <-- ADDED: For detailed RAG context display
  error?: string | null;
  // Debugger / Legacy State
  intermediate_steps?: IntermediateStep[];
  type?: 'human' | 'ai' | 'tool' | string;
  content?: string; // Raw content if needed
  tool_calls?: any[];
  tool_call_id?: string;
}
// --- End Updated Message Interface ---

// --- API Payloads & Responses (unchanged from previous) ---
export interface AskPayload { question: string; filenames?: string[]; tag_filter?: string | null; chat_history?: Array<{ sender: 'user' | 'ai'; text: string }>; }
export interface AskResponseData { answer: string; source_documents?: any[]; intermediate_steps?: IntermediateStep[]; }
export interface DocumentInfo { filename: string; tag?: string | null; file_type?: string | null; }
export interface DocumentList { documents: DocumentInfo[]; }
export interface ProviderStatus { current_provider: string; message: string; }
export interface SetProviderPayload { provider: string; }
export interface UploadFilePayload { file: File; tag?: string; }


// --- UI Stream Event Interfaces ---
export interface ThinkingStartedData { message: string; }
export interface ToolCallInitiatedData { tool_name: string; tool_input: any; message: string; }
export interface SourcesFoundData { sources: Source[]; } // Web sources payload
export interface RagContextFoundData { context: RagContextDocument[]; } // <<< ADDED: RAG context payload
export interface StatusUpdateData { message: string; }
export interface AiMessageChunkData { content_chunk: string; }
export interface FinalAnswerTurnCompleteData { message_id?: string; }
export interface ErrorMessageData { error: string; details?: string; }


// --- NEW: Job Schemas ---
export const JOB_STATUS_PENDING = "PENDING";
export const JOB_STATUS_RUNNING = "RUNNING";
export const JOB_STATUS_COMPLETED = "COMPLETED";
export const JOB_STATUS_FAILED = "FAILED";
export const JOB_STATUS_CANCELED = "CANCELED";
export type JobStatus = typeof JOB_STATUS_PENDING | typeof JOB_STATUS_RUNNING | typeof JOB_STATUS_COMPLETED | typeof JOB_STATUS_FAILED | typeof JOB_STATUS_CANCELED;

export interface JobMetadata {
    job_id: string;
    task_type: string;
    status: JobStatus;
    created_at: number; // Timestamp
    updated_at: number; // Timestamp
    progress_message?: string | null;
    error_message?: string | null;
}

export interface JobStatusResponse extends JobMetadata {
    input_params?: Record<string, any> | null;
}

export interface JobListResponseItem extends JobMetadata {
     input_summary?: string | null;
}

export interface JobListResponse {
    jobs: JobListResponseItem[];
    total: number;
    limit?: number | null;
    offset?: number | null;
}

export interface JobResultResponse extends JobMetadata {
    input_params?: Record<string, any> | null;
    result_data?: any | null; // Could be Markdown string, JSON, etc.
}

export interface StartJobResponse {
    job_id: string;
    message?: string;
}

export interface CancelJobResponse {
    job_id: string;
    status: string; // e.g., "CANCEL_REQUESTED", "CANCEL_FAILED"
    message?: string | null;
}

// Payload for starting deep research
export interface StartDeepResearchPayload {
    topic: string;
    depth?: number;
    max_sources_per_query?: number;
    max_total_sources?: number;
    // Add other params matching backend schema if needed
}

// Unified event type for the frontend callback
export interface UiStreamEvent {
  type:
    | 'thinking_started' | 'tool_call_initiated' | 'sources_found'
    | 'rag_context_found' // <<< ADDED
    | 'status_update' | 'ai_message_chunk' | 'final_answer_turn_complete'
    | 'error_message' | 'stream_end'
    // Debugger event types
    | 'node_start' | 'node_end' | 'state_update' | 'token' | 'tool_call'
    | 'tool_result' | 'final_message' | 'node_output';
  data: any; // Parsed data payload for the event type
  rawBackendEvent?: string; // Original SSE event name
}

// Structure backend sends in the SSE `data:` field
export interface BackendUiEventPayload { type: UiStreamEvent['type']; data: string; }
export interface BackendDebuggerEventPayload { event: "log_data"; data: string; }


// Callbacks for the unified stream
export type StreamEventCallbacks = {
  onOpen?: () => void;
  onEvent?: (event: UiStreamEvent) => void;
  onComplete?: () => void;
  onError?: (error: any | string) => void;
};

// --- API Functions ---
// Upload, Ask (non-stream), Get/Delete Docs, Provider functions remain unchanged
export const uploadFile = async (payload: UploadFilePayload): Promise<{ filename: string; message: string }> => { console.log(`Uploading file: ${payload.file.name}, Tag: ${payload.tag || 'N/A'}`); const formData = new FormData(); formData.append('file', payload.file); if (payload.tag) { formData.append('tag', payload.tag); } const response = await fetch(`${API_BASE_URL}/documents/upload`, { method: 'POST', body: formData, }); if (!response.ok) { let errorDetail = `Upload failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error("Upload API Error:", errorDetail); throw new Error(errorDetail); } return response.json(); };
export const askQuestion = async (payload: AskPayload): Promise<AskResponseData> => { console.log("Sending request to /ask endpoint with payload:", payload); const response = await fetch(`${API_BASE_URL}/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify({ question: payload.question, ...(payload.filenames && payload.filenames.length > 0 && { filenames: payload.filenames }), ...(payload.tag_filter && { tag_filter: payload.tag_filter }), ...(payload.chat_history && { chat_history: payload.chat_history }), }), }); if (!response.ok) { let errorDetail = `Ask request failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error("Ask question API error:", errorDetail); throw new Error(errorDetail); } return response.json(); };
export const getDocumentList = async (): Promise<DocumentList> => { console.log("Fetching document list..."); const response = await fetch(`${API_BASE_URL}/documents`, { method: 'GET', headers: { 'Accept': 'application/json' }, }); if (!response.ok) { let errorDetail = `Get documents failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error("Get document list error:", errorDetail); throw new Error(errorDetail); } return response.json(); };
export const deleteDocument = async (filename: string): Promise<void> => { const encodedFilename = encodeURIComponent(filename); console.log(`Requesting deletion of document: ${filename}`); const response = await fetch(`${API_BASE_URL}/documents/${encodedFilename}`, { method: 'DELETE', }); if (response.status === 204) { console.log(`Successfully deleted ${filename}`); return; } let errorDetail = `Delete failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error(`Delete document error for ${filename}:`, errorDetail); throw new Error(errorDetail); };
export const getCurrentProvider = async (): Promise<ProviderStatus> => { console.log("Fetching current AI provider status..."); const response = await fetch(`${API_BASE_URL}/config/provider`, { method: 'GET', headers: { 'Accept': 'application/json' }, }); if (!response.ok) { let errorDetail = `Get provider status failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error("Get provider status error:", errorDetail); throw new Error(errorDetail); } return response.json(); };
export const switchProvider = async (payload: SetProviderPayload): Promise<ProviderStatus> => { console.log(`Requesting switch to AI provider: ${payload.provider}`); const response = await fetch(`${API_BASE_URL}/config/provider`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify(payload), }); if (!response.ok) { let errorDetail = `Switch provider failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error("Switch provider error:", errorDetail); throw new Error(errorDetail); } return response.json(); };

// --- askQuestionStream (SSE Parsing Logic - Unchanged from previous) ---
export const askQuestionStream = (
    payload: AskPayload,
    callbacks: StreamEventCallbacks
): AbortController => {
    console.log("Connecting to /ask-stream with payload:", payload);
    const abortController = new AbortController();
    const { onOpen, onEvent, onComplete, onError } = callbacks;

    const fetchStream = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/ask-stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
                body: JSON.stringify({ ...payload, chat_history: payload.chat_history?.map(m => ({ sender: m.sender, text: m.text })) }),
                signal: abortController.signal,
            });

            if (!response.ok) { throw new Error(`HTTP error! status: ${response.status}`); }
            if (!response.body) { throw new Error('Response body is null'); }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            if (onOpen) onOpen();

            while (true) {
                const { done, value } = await reader.read();
                if (value) { buffer += decoder.decode(value, { stream: true }); }

                let lineEndIndex;
                while ((lineEndIndex = buffer.indexOf('\n')) >= 0) {
                    const line = buffer.substring(0, lineEndIndex).trim();
                    buffer = buffer.substring(lineEndIndex + 1);

                    if (line.startsWith('event:')) {
                        const sseEventName = line.substring(6).trim();
                        let dataLineIndex = buffer.indexOf('\n');
                        if (dataLineIndex >= 0) {
                             const nextLine = buffer.substring(0, dataLineIndex).trim();
                             if (nextLine.startsWith('data:')) {
                                 const sseDataFieldJsonStr = nextLine.substring(5).trim();
                                 buffer = buffer.substring(dataLineIndex + 1);
                                 if (onEvent) {
                                    try {
                                        const parsedSseDataField = JSON.parse(sseDataFieldJsonStr);
                                        if (sseEventName === "log_data") { // Debugger event
                                            onEvent({ type: parsedSseDataField.type, data: parsedSseDataField, rawBackendEvent: sseEventName });
                                        } else { // Our UI event
                                            const uiEventPayload = parsedSseDataField as BackendUiEventPayload;
                                            onEvent({ type: uiEventPayload.type as UiStreamEvent['type'], data: JSON.parse(uiEventPayload.data), rawBackendEvent: sseEventName });
                                        }
                                    } catch (e) { if (onError) onError(`Failed to process stream event data: ${e instanceof Error ? e.message : String(e)}`); }
                                 }
                             } else { console.warn(`[SSE Parser] Event line '${line}' not followed by data line.`); }
                        } else if (done) { break; }
                        else { buffer = line + '\n' + buffer; break; }
                    }
                }
                if (done) { console.log("[SSE Parser] Stream reading finished."); break; }
            }
        } catch (error: any) {
            if (error.name === 'AbortError') { console.log('Stream fetch aborted by client.'); }
            else { console.error('Error reading or fetching stream:', error); if (onError) onError(`Stream connection error: ${error.message || String(error)}`); }
        } finally {
             console.log("[SSE Parser] Stream processing loop ended.");
             if (onComplete) onComplete();
        }
    };

    fetchStream();
    return abortController;
};


// --- NEW: Job API Functions ---

async function handleApiResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        let errorDetail = `API request failed: ${response.status} ${response.statusText}`;
        try { const errorData = await response.json(); errorDetail = errorData.detail || errorData.error || errorDetail; } catch (e) {}
        console.error("API Error:", errorDetail, response);
        throw new Error(errorDetail);
    }
    return response.json();
}

export const startJob = async (taskType: string, inputParams: Record<string, any>): Promise<StartJobResponse> => {
    console.log(`Starting job: ${taskType}`, inputParams);
    const response = await fetch(`${API_BASE_URL}/jobs/${taskType}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(inputParams),
    });
    return handleApiResponse<StartJobResponse>(response);
};

export const getJobStatus = async (jobId: string): Promise<JobStatusResponse> => {
    console.log(`Getting status for job: ${jobId}`);
    const response = await fetch(`${API_BASE_URL}/jobs/status/${jobId}`, {
         method: 'GET', headers: { 'Accept': 'application/json' },
    });
    return handleApiResponse<JobStatusResponse>(response);
};

export const getJobResult = async (jobId: string): Promise<JobResultResponse> => {
    console.log(`Getting result for job: ${jobId}`);
    const response = await fetch(`${API_BASE_URL}/jobs/result/${jobId}`, {
         method: 'GET', headers: { 'Accept': 'application/json' },
    });
    return handleApiResponse<JobResultResponse>(response);
};

export const cancelJob = async (jobId: string): Promise<CancelJobResponse> => {
    console.log(`Requesting cancellation for job: ${jobId}`);
    const response = await fetch(`${API_BASE_URL}/jobs/cancel/${jobId}`, {
         method: 'POST', headers: { 'Accept': 'application/json' },
    });
     // Cancel might return 200 OK on success or raise HTTPException for failure cases
    return handleApiResponse<CancelJobResponse>(response);
};

export const getActiveJobs = async (): Promise<JobListResponse> => {
    console.log("Fetching active jobs...");
    const response = await fetch(`${API_BASE_URL}/jobs/active`, {
         method: 'GET', headers: { 'Accept': 'application/json' },
    });
    return handleApiResponse<JobListResponse>(response);
};

export const getJobHistory = async (limit: number = 20, offset: number = 0): Promise<JobListResponse> => {
    console.log(`Fetching job history (limit=${limit}, offset=${offset})...`);
    const response = await fetch(`${API_BASE_URL}/jobs/history?limit=${limit}&offset=${offset}`, {
         method: 'GET', headers: { 'Accept': 'application/json' },
    });
    return handleApiResponse<JobListResponse>(response);
};

export const hardDeleteJobAPI = async (jobId: string): Promise<{ job_id: string; message: string }> => {
    console.log(`Requesting permanent deletion for job: ${jobId}`);
    const response = await fetch(`${API_BASE_URL}/jobs/delete/${jobId}`, {
         method: 'DELETE', headers: { 'Accept': 'application/json' },
    });
    return handleApiResponse<{ job_id: string; message: string }>(response); // Assuming handleApiResponse handles non-OK
};