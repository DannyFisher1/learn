// lib/api.ts

// Base URL for the backend API - Ensure this matches your backend port
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9000';

// --- Core Interfaces ---

export interface AgentAction {
    tool?: string;
    tool_input?: any;
    log?: string;
}

export interface IntermediateStep {
    action: AgentAction | string;
    observation: any;
}

export interface RedditPost {
    post_title: string;
    post_score: number;
    post_id: string;
    post_subreddit: string;
    post_url: string;
    post_created_utc?: number;
    post_text?: string;
    post_num_comments?: number;
    post_author?: string;
}

export interface RagContextDocument {
    id: string;
    page_content: string;
    metadata: {
        source_file?: string | null;
        page?: number | string | null;
        tag?: string | null;
        file_type?: string | null;
    };
}

export interface Message {
  sender: 'user' | 'ai';
  text: string;
  sources?: { source: string; page: number | string }[];
  id?: string;
  intermediate_steps?: IntermediateStep[]; // Keep for non-streaming response
  // Properties likely found within LangGraph messages state:
  type?: 'human' | 'ai' | 'tool' | string; // From BaseMessage type
  content?: string;
  tool_calls?: any[]; // From AIMessage
  tool_call_id?: string; // From ToolMessage
}

// --- API Payloads and Responses ---

export interface UploadFilePayload {
    file: File;
    tag?: string;
}

export interface AskPayload {
  question: string;
  filenames?: string[];
  tag_filter?: string | null;
  chat_history?: Array<{ sender: 'user' | 'ai'; text: string }>;
}

export interface AskResponseData {
  answer: string;
  source_documents?: { source: string; page: number | string }[];
  intermediate_steps?: IntermediateStep[];
}

export interface DocumentInfo {
    filename: string;
    tag?: string | null;
    file_type?: string | null;
}

export interface DocumentList {
    documents: DocumentInfo[];
}

export interface ProviderStatus {
    current_provider: 'ollama' | 'openai' | string;
    message: string;
}

export interface SetProviderPayload {
    provider: 'ollama' | 'openai';
}


// --- Interfaces for Debugger Streaming ---

// Describes the structured data emitted by the enhanced parser
export interface StreamLogData {
    type: 'node_start' | 'node_end' | 'state_update' | 'token' | 'tool_call' | 'tool_result' | 'error' | 'final_message' | 'stream_end' | 'node_output';
    nodeId?: string;        // ID of the node starting/ending (e.g., "agent", "action")
    state?: { messages: Message[] }; // The updated messages list from AgentState (using Message type for frontend)
    token?: string;         // Final answer token
    toolCall?: { id: string; name?: string; args?: any }; // Details of a tool call initiated
    toolResult?: { id: string; result: any };            // Result corresponding to a tool call ID
    output?: any;           // For 'node_output' event, carrying the node's final output
    message?: string;       // For final_message or general info messages from backend
    error?: any;            // Error details
}

// Callbacks for the debugger stream
export type StreamLogCallbacks = {
  onOpen?: () => void;
  onLogData?: (logData: StreamLogData) => void; // Single callback for all structured events
  onComplete?: () => void;
  onError?: (error: any | string) => void; // General error callback
};

// --- Helper for Duck Typing Messages (adjust properties as needed) ---
function getMessageType(msg: any): string {
    if (!msg || typeof msg !== 'object') return 'unknown';
    if ('tool_call_id' in msg) return 'tool';
    if ('tool_calls' in msg && Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0) return 'ai_tool_call'; // Specific state
    if (typeof msg.content === 'string' && msg.type === 'ai') return 'ai'; // Check type property if backend sends it
    if (typeof msg.content === 'string' && msg.type === 'human') return 'human'; // Check type property
    // Fallbacks
    if ('tool_calls' in msg) return 'ai'; // Assume AI if tool_calls key exists
    return 'unknown_message';
}

// --- Duck Typing Helper for Chunk ---
function isAIMessageChunk(value: any): boolean {
    // Adjust checks based on actual streamed chunk properties from LangGraph/LangChain
    return value && typeof value === 'object' && 'content' in value && typeof value.content === 'string' && ('tool_call_chunks' in value || 'tool_calls' in value); // AIMessageChunk often has content and potentially tool_call_chunks
}
// --- Duck Typing Helper for Tool Call ---
function isToolCall(value: any): boolean {
     return value && typeof value === 'object' && 'id' in value && 'name' in value && 'args' in value;
}
// --- Duck Typing Helper for Tool Message ---
function isToolMessage(value: any): boolean {
     return value && typeof value === 'object' && 'tool_call_id' in value && 'content' in value;
}

// --- Updated SSE Parser Helper Function ---
const parseAndProcessLogChunk = (logDataJson: string, cbs: StreamLogCallbacks) => {
    // The backend now sends the structured data directly
    try {
        const logData: StreamLogData = JSON.parse(logDataJson);
        // Directly call the single callback with the parsed data
        if (cbs.onLogData) {
            cbs.onLogData(logData);
        } else {
             console.warn("onLogData callback not provided, skipping log processing:", logData);
        }
    } catch (e) {
        console.error("[SSE Parser] Failed to parse structured log data JSON:", logDataJson, e);
        if (cbs.onError) cbs.onError(`Failed to parse stream data: ${e instanceof Error ? e.message : String(e)}`);
    }
};
// --- End Updated SSE Parser Helper ---


// --- API Functions (uploadFile, askQuestion, getDocumentList, deleteDocument, getCurrentProvider, switchProvider remain the same) ---
/** Uploads a file with an optional tag. */
export const uploadFile = /* ... (implementation unchanged) ... */ async (payload: UploadFilePayload): Promise<{ filename: string; message: string }> => { console.log(`Uploading file: ${payload.file.name}, Tag: ${payload.tag || 'N/A'}`); const formData = new FormData(); formData.append('file', payload.file); if (payload.tag) { formData.append('tag', payload.tag); } const response = await fetch(`${API_BASE_URL}/documents/upload`, { method: 'POST', body: formData, }); if (!response.ok) { let errorDetail = `Upload failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error("Upload API Error:", errorDetail); throw new Error(errorDetail); } return response.json(); };
/** Sends a question for a non-streaming response. */
export const askQuestion = /* ... (implementation unchanged) ... */ async (payload: AskPayload): Promise<AskResponseData> => { console.log("Sending request to /ask endpoint with payload:", payload); const response = await fetch(`${API_BASE_URL}/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify({ question: payload.question, ...(payload.filenames && payload.filenames.length > 0 && { filenames: payload.filenames }), ...(payload.tag_filter && { tag_filter: payload.tag_filter }), ...(payload.chat_history && { chat_history: payload.chat_history }), }), }); if (!response.ok) { let errorDetail = `Ask request failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error("Ask question API error:", errorDetail); throw new Error(errorDetail); } return response.json(); };
/** Fetches the list of indexed documents. */
export const getDocumentList = /* ... (implementation unchanged) ... */ async (): Promise<DocumentList> => { console.log("Fetching document list..."); const response = await fetch(`${API_BASE_URL}/documents`, { method: 'GET', headers: { 'Accept': 'application/json' }, }); if (!response.ok) { let errorDetail = `Get documents failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error("Get document list error:", errorDetail); throw new Error(errorDetail); } return response.json(); };
/** Deletes a specified document. */
export const deleteDocument = /* ... (implementation unchanged) ... */ async (filename: string): Promise<void> => { const encodedFilename = encodeURIComponent(filename); console.log(`Requesting deletion of document: ${filename}`); const response = await fetch(`${API_BASE_URL}/documents/${encodedFilename}`, { method: 'DELETE', }); if (response.status === 204) { console.log(`Successfully deleted ${filename}`); return; } let errorDetail = `Delete failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error(`Delete document error for ${filename}:`, errorDetail); throw new Error(errorDetail); };
/** Fetches the current AI provider status. */
export const getCurrentProvider = /* ... (implementation unchanged) ... */ async (): Promise<ProviderStatus> => { console.log("Fetching current AI provider status..."); const response = await fetch(`${API_BASE_URL}/config/provider`, { method: 'GET', headers: { 'Accept': 'application/json' }, }); if (!response.ok) { let errorDetail = `Get provider status failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error("Get provider status error:", errorDetail); throw new Error(errorDetail); } return response.json(); };
/** Requests a switch of the active AI provider. */
export const switchProvider = /* ... (implementation unchanged) ... */ async (payload: SetProviderPayload): Promise<ProviderStatus> => { console.log(`Requesting switch to AI provider: ${payload.provider}`); const response = await fetch(`${API_BASE_URL}/config/provider`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify(payload), }); if (!response.ok) { let errorDetail = `Switch provider failed: ${response.status} ${response.statusText}`; try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ } console.error("Switch provider error:", errorDetail); throw new Error(errorDetail); } return response.json(); };

// --- askQuestionStream (Updated for Debugger) ---
export const askQuestionStream = (
    payload: AskPayload,
    callbacks: StreamLogCallbacks // Uses the new callback type
): AbortController => {
    console.log("Connecting to /ask-stream for log streaming with payload:", payload);
    const abortController = new AbortController();
    const { onOpen, onLogData, onComplete, onError } = callbacks; // Get the single data callback

    // --- Main Fetch Logic (Reads raw chunks) ---
    const fetchStream = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/ask-stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
                body: JSON.stringify({ ...payload, chat_history: payload.chat_history?.map(m => ({ sender: m.sender, text: m.text })) }),
                signal: abortController.signal,
            });

            if (!response.ok) { /* ... (standard error handling) ... */
                let errorDetail = `Stream request failed: ${response.status} ${response.statusText}`;
                try { const errorData = await response.json(); errorDetail = errorData.detail || errorData.error || errorDetail; } catch (e) { /* Ignore */ }
                console.error("Ask stream API error response:", { status: response.status, detail: errorDetail });
                if (onError) onError(errorDetail); if (onComplete) onComplete(); return;
            }
            if (!response.body) { throw new Error('Response body is unexpectedly null'); }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            // Removed temporary JSON buffer, process line by line

            if (onOpen) onOpen();

            while (true) {
                const { done, value } = await reader.read();
                if (value) { buffer += decoder.decode(value, { stream: true }); }

                let lineEndIndex;
                while ((lineEndIndex = buffer.indexOf('\n')) >= 0) {
                    const line = buffer.substring(0, lineEndIndex).trim();
                    buffer = buffer.substring(lineEndIndex + 1);

                    // --- Updated SSE Message Parsing ---
                    if (line.startsWith('event:')) {
                        const eventName = line.substring(6).trim();
                        // We expect 'log_data' or maybe 'error', 'end' from backend now
                        // Read the next line which should be the 'data:' line
                        let dataLineIndex = buffer.indexOf('\n');
                        if (dataLineIndex >= 0) {
                             const nextLine = buffer.substring(0, dataLineIndex).trim();
                             if (nextLine.startsWith('data:')) {
                                 const jsonData = nextLine.substring(5).trim();
                                 if (eventName === 'log_data') {
                                      parseAndProcessLogChunk(jsonData, callbacks);
                                 } else if (eventName === 'error') {
                                     // Handle explicit error events if backend sends them
                                     try {
                                         const errorData = JSON.parse(jsonData);
                                         if (onError) onError(errorData.error || jsonData);
                                     } catch (e) { if (onError) onError("Failed to parse error event data"); }
                                 } else if (eventName === 'end') {
                                      // Explicit end signal from backend (though onComplete in finally is more robust)
                                      console.log("[SSE Parser] Received explicit 'end' event name.");
                                 } else {
                                     console.warn(`[SSE Parser] Received unexpected event name: '${eventName}'`)
                                 }
                                 buffer = buffer.substring(dataLineIndex + 1); // Consume data line
                             } else {
                                 // Event line wasn't followed by data line, potential issue
                                 console.warn(`[SSE Parser] Event line '${line}' not followed by data line.`);
                             }
                        } else if (done) {
                            // Stream ended right after event line
                            break;
                        } else {
                             // Need more data for the data line
                             buffer = line + '\n' + buffer; // Put event line back
                             break; // Exit inner loop, wait for more data
                        }
                    } else if (line.startsWith('data:')) {
                         // Message without an 'event:' line (defaults to 'message' event)
                         // We don't expect backend to send messages this way anymore, maybe log warning
                         console.warn("[SSE Parser] Received data without explicit event:", line);
                    }
                    // Ignore empty lines and comment lines (starting with ':')
                    // ----------------------------------
                } // End while loop processing lines

                if (done) {
                    console.log("[SSE Parser] Stream reading finished (done signal).");
                    // No trailing data processing needed here as we process line-by-line
                    break;
                }
            } // End while(true)
        } catch (error: any) { /* ... (standard error handling) ... */
            if (error.name === 'AbortError') { console.log('Stream fetch aborted by client.'); }
            else { console.error('Error reading or fetching stream:', error); if (onError) onError(`Stream connection error: ${error.message || String(error)}`); }
        } finally {
             console.log("[SSE Parser] Stream processing loop ended.");
             if (onComplete) onComplete(); // Ensure onComplete is called
        }
    }; // End fetchStream

    fetchStream();
    return abortController;
};