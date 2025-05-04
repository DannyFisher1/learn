// lib/api.ts

// Base URL for the backend API - Ensure this matches your backend port
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9000';

// --- Interfaces ---

export interface AgentAction {
    tool?: string;
    tool_input?: any;
    log?: string;
}

export interface IntermediateStep {
    action: AgentAction | string;
    observation: any;
}

// --- ADD RedditPost Interface --- //
// Matches the structure sent by the backend's 'reddit_results' event
// Also used by ObservationDisplay, ensure keys match there too.
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
// ----------------------------- //

// Interface for a single RAG Context Document (matches backend serialization)
export interface RagContextDocument {
    id: string; // e.g., "doc_0", "doc_1"
    page_content: string;
    metadata: {
        source_file?: string | null;
        page?: number | string | null; // Allow number or string for page
        tag?: string | null;
        file_type?: string | null;
        // Add other relevant metadata fields if needed
    };
}

// Main Message interface used in the frontend state
export interface Message {
  sender: 'user' | 'ai';
  text: string;
  sources?: { source: string; page: number | string }[]; // Final source attribution from RAG
  id?: string; // Unique ID for React keys and tracking
  intermediate_steps?: IntermediateStep[]; // Steps taken by the agent for this message
  // Optional: Store related RAG context directly on the message? Currently handled in page state.
  // rag_context?: RagContextDocument[] | null;
}

// Payload for file uploads
export interface UploadFilePayload {
    file: File;
    tag?: string; // Optional tag/category
}

// Payload for asking questions (supports filtering and history)
export interface AskPayload {
  question: string;
  filenames?: string[]; // Optional list of filenames to filter RAG
  tag_filter?: string | null; // Optional tag to filter RAG
  chat_history?: Array<{ sender: 'user' | 'ai'; text: string }>; // Simplified history format
}

// Response structure for the non-streaming /ask endpoint
export interface AskResponseData {
  answer: string;
  source_documents?: { source: string; page: number | string }[]; // Final sources used
  intermediate_steps?: IntermediateStep[]; // Complete steps for the request
}

// Basic information about an indexed document
export interface DocumentInfo {
    filename: string;
    tag?: string | null;
    file_type?: string | null;
}

// Response structure for listing documents
export interface DocumentList {
    documents: DocumentInfo[];
}

// Response structure for provider status
export interface ProviderStatus {
    current_provider: 'ollama' | 'openai' | string; // Allow string for potential future providers
    message: string;
}

// Payload for switching provider
export interface SetProviderPayload {
    provider: 'ollama' | 'openai';
}

// Interface describing the data structure within each SSE event's `data` field
export interface StreamEventData {
  token?: string; // For text chunks of the final answer
  step?: IntermediateStep; // For partial agent steps (tool call started)
  step_final?: IntermediateStep; // For completed agent steps (tool call finished with observation) - NOTE: Backend yields event 'step_final' but data key is 'step'
  error?: string | { message: string }; // For errors during stream
  context?: RagContextDocument[]; // For retrieved RAG context snippets
}

// Type definition for the callbacks object used with askQuestionStream
export type StreamCallbacks = {
  onOpen?: () => void; // Called when the stream connection is established
  onToken?: (token: string) => void; // Called for each piece of the final answer text
  onStep?: (step: IntermediateStep) => void; // Called when a tool call starts
  onStepFinal?: (step: IntermediateStep) => void; // Called when a tool call finishes
  onRagContext?: (contextDocs: RagContextDocument[]) => void; // Called when RAG context is retrieved
  onComplete?: () => void; // Called when the stream finishes normally (backend sends 'end' event or connection closes)
  onError?: (error: StreamEventData['error'] | string) => void; // Called on stream errors or 'error' events
};

// --- API Functions ---

/**
 * Uploads a file with an optional tag.
 */
export const uploadFile = async (payload: UploadFilePayload): Promise<{ filename: string; message: string }> => {
    console.log(`Uploading file: ${payload.file.name}, Tag: ${payload.tag || 'N/A'}`);
    const formData = new FormData();
    formData.append('file', payload.file);
    if (payload.tag) {
        formData.append('tag', payload.tag);
    }

    const response = await fetch(`${API_BASE_URL}/documents/upload`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        let errorDetail = `Upload failed: ${response.status} ${response.statusText}`;
        try {
            const errorData = await response.json();
            errorDetail = errorData.detail || errorDetail;
        } catch (e) { /* Ignore JSON parse error */ }
        console.error("Upload API Error:", errorDetail);
        throw new Error(errorDetail);
    }
    return response.json();
};

/**
 * Sends a question for a non-streaming response. (Less used now, but kept for potential use)
 */
export const askQuestion = async (payload: AskPayload): Promise<AskResponseData> => {
    console.log("Sending request to /ask endpoint with payload:", payload);
    const response = await fetch(`${API_BASE_URL}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({
          question: payload.question,
          ...(payload.filenames && payload.filenames.length > 0 && { filenames: payload.filenames }),
          ...(payload.tag_filter && { tag_filter: payload.tag_filter }),
          ...(payload.chat_history && { chat_history: payload.chat_history }), // Ensure backend handles this format
      }),
    });

    if (!response.ok) {
        let errorDetail = `Ask request failed: ${response.status} ${response.statusText}`;
        try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ }
        console.error("Ask question API error:", errorDetail);
        throw new Error(errorDetail);
    }
    return response.json();
};

/**
 * Fetches the list of indexed documents.
 */
export const getDocumentList = async (): Promise<DocumentList> => {
    console.log("Fetching document list...");
    const response = await fetch(`${API_BASE_URL}/documents`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
    });
    if (!response.ok) {
        let errorDetail = `Get documents failed: ${response.status} ${response.statusText}`;
        try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ }
        console.error("Get document list error:", errorDetail);
        throw new Error(errorDetail);
    }
    return response.json();
};

/**
 * Deletes a specified document.
 */
export const deleteDocument = async (filename: string): Promise<void> => {
    const encodedFilename = encodeURIComponent(filename);
    console.log(`Requesting deletion of document: ${filename}`);
    const response = await fetch(`${API_BASE_URL}/documents/${encodedFilename}`, {
        method: 'DELETE',
    });

    if (response.status === 204) {
        console.log(`Successfully deleted ${filename}`);
        return; // Success
    }

    let errorDetail = `Delete failed: ${response.status} ${response.statusText}`;
    try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ }
    console.error(`Delete document error for ${filename}:`, errorDetail);
    throw new Error(errorDetail);
};

/**
 * Fetches the current AI provider status.
 */
export const getCurrentProvider = async (): Promise<ProviderStatus> => {
    console.log("Fetching current AI provider status...");
    const response = await fetch(`${API_BASE_URL}/config/provider`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
    if (!response.ok) {
      let errorDetail = `Get provider status failed: ${response.status} ${response.statusText}`;
      try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ }
      console.error("Get provider status error:", errorDetail);
      throw new Error(errorDetail);
    }
    return response.json();
};

/**
 * Requests a switch of the active AI provider.
 */
export const switchProvider = async (payload: SetProviderPayload): Promise<ProviderStatus> => {
    console.log(`Requesting switch to AI provider: ${payload.provider}`);
    const response = await fetch(`${API_BASE_URL}/config/provider`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      let errorDetail = `Switch provider failed: ${response.status} ${response.statusText}`;
      try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* Ignore */ }
      console.error("Switch provider error:", errorDetail);
      throw new Error(errorDetail);
    }
    return response.json();
};

/**
 * Initiates a streaming chat request and handles Server-Sent Events (SSE).
 */
export const askQuestionStream = (
    payload: AskPayload,
    callbacks: StreamCallbacks
): AbortController => {
    console.log("Connecting to /ask-stream endpoint with payload:", payload);
    const abortController = new AbortController();
    const { onOpen, onToken, onStep, onStepFinal, onRagContext, onComplete, onError } = callbacks;

    // --- SSE Parser Helper Function ---
    const parseAndHandleSSEData = ( event: string | null, data: string, cbs: StreamCallbacks ) => {
        const eventType = event || 'message'; // SSE default event type
        try {
            const parsedData = JSON.parse(data); // Removed explicit type cast here

            // console.debug(`[SSE Parser] Event='${eventType}', Data:`, parsedData); // Verbose debug log

            if (eventType === 'token' && typeof parsedData.token === 'string' && cbs.onToken) {
                cbs.onToken(parsedData.token);
            } else if (eventType === 'step' && parsedData.step && cbs.onStep) {
                cbs.onStep(parsedData.step as IntermediateStep);
            } else if (eventType === 'step_final' && parsedData.step && cbs.onStepFinal) {
                // Pass the nested step object, which matches the IntermediateStep structure
                cbs.onStepFinal(parsedData.step as IntermediateStep); // Pass the nested object
            } else if (eventType === 'rag_context' && Array.isArray(parsedData.context) && cbs.onRagContext) {
                 console.log(`[SSE Parser] Identified 'rag_context' with ${parsedData.context.length} docs.`);
                 cbs.onRagContext(parsedData.context as RagContextDocument[]); // Pass validated context
            } else if (eventType === 'error' && parsedData.error && cbs.onError) {
                 cbs.onError(parsedData.error);
            } else if (eventType === 'end') {
                 console.log("[SSE Parser] Received 'end' event signal."); // Usually handled by stream completion
            } else if (eventType !== 'message') { // Log unhandled named events
                 console.warn(`[SSE Parser] Unhandled SSE event type '${eventType}' with data:`, parsedData);
            }

        } catch (e) {
            console.error('[SSE Parser] Failed to parse SSE JSON data:', data, e);
            if (cbs.onError) cbs.onError(`Failed to parse stream data: ${e instanceof Error ? e.message : String(e)}`);
        }
    };
    // --- End SSE Parser Helper ---


    // --- Main Fetch Logic ---
    const fetchStream = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/ask-stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream', // Important for SSE
                },
                // Ensure payload structure matches backend expectation
                body: JSON.stringify({
                    ...payload,
                    // Map history if needed, ensure correct format
                    chat_history: payload.chat_history?.map(m => ({ sender: m.sender, text: m.text }))
                }),
                signal: abortController.signal, // Allow aborting the fetch request
            });

            // Check for HTTP errors before attempting to read stream
            if (!response.ok) {
                let errorDetail = `Stream request failed: ${response.status} ${response.statusText}`;
                try {
                    const errorData = await response.json();
                    errorDetail = errorData.detail || errorData.error || errorDetail;
                } catch (e) { /* Ignore if response isn't JSON */ }
                console.error("Ask stream API error response:", { status: response.status, detail: errorDetail });
                if (onError) onError(errorDetail); // Report HTTP error
                if (onComplete) onComplete(); // Signal completion even on error
                return;
            }
            if (!response.body) {
                throw new Error('Response body is unexpectedly null');
            }

            // Setup for reading the stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = ''; // Accumulates partial lines
            let currentEvent: string | null = null; // Tracks 'event:' line
            let currentData = ''; // Accumulates 'data:' lines for a single event

            if (onOpen) onOpen(); // Signal stream opened successfully

            // Loop to continuously read chunks from the stream
            while (true) {
                const { done, value } = await reader.read();

                if (value) {
                    const rawChunk = decoder.decode(value, { stream: true }); // Decode chunk
                    buffer += rawChunk; // Append to buffer
                }

                // Process complete lines (ending in '\n') from the buffer
                let lineEndIndex;
                while ((lineEndIndex = buffer.indexOf('\n')) >= 0) {
                    const line = buffer.substring(0, lineEndIndex).trim(); // Extract line
                    buffer = buffer.substring(lineEndIndex + 1); // Remove processed line from buffer

                    if (line === '') { // Empty line signifies end of an event message
                        if (currentData) { // If we have accumulated data
                            parseAndHandleSSEData(currentEvent, currentData, callbacks);
                        }
                        // Reset for the next event message
                        currentEvent = null;
                        currentData = '';
                    } else if (line.startsWith('event:')) {
                        currentEvent = line.substring(6).trim();
                    } else if (line.startsWith('data:')) {
                        const dataContent = line.substring(5).trim();
                        // Append data (handling multi-line data fields)
                        currentData = currentData ? `${currentData}\n${dataContent}` : dataContent;
                    } // Ignore comment lines (starting with ':') or other non-standard lines
                } // End while loop for processing lines in buffer

                // If the stream is finished
                if (done) {
                    console.log("[SSE Parser] Stream reading finished (done signal).");
                    // Process any final data remaining in the buffer (if stream ended mid-message)
                    if (currentData) {
                        console.warn("[SSE Parser] Processing final data after stream 'done'.");
                        parseAndHandleSSEData(currentEvent, currentData, callbacks);
                    }
                    break; // Exit the main reading loop
                }
            } // End while(true) loop for reading stream

        } catch (error: any) {
            // Handle errors during fetch/read
            if (error.name === 'AbortError') {
                console.log('Stream fetch aborted by client.'); // Expected if user stops
            } else {
                console.error('Error reading or fetching stream:', error);
                if (onError) onError(`Stream connection error: ${error.message || String(error)}`);
            }
        } finally {
             console.log("[SSE Parser] Stream processing loop ended or encountered an error.");
             if (onComplete) onComplete(); // Ensure onComplete is always called
        }
    };
    // --- End Fetch Logic ---

    fetchStream(); // Start the process
    return abortController; // Return controller to allow cancellation
};