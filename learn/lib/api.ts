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

export interface Message {
  sender: 'user' | 'ai';
  text: string;
  sources?: { source: string; page: number | string }[];
  id?: string;
  intermediate_steps?: IntermediateStep[];
}

/**
 * Payload structure for uploading a file.
 * Changed 'category' to 'tag'.
 */
export interface UploadFilePayload {
    file: File;
    tag?: string; // <<< CHANGED from category to tag
}

/**
 * Payload structure for asking a question to the agent.
 * Added 'tag_filter'.
 */
export interface AskPayload {
  question: string;
  filenames?: string[];
  tag_filter?: string | null;
  chat_history?: Message[];
}

/**
 * Expected data structure of the successful JSON response from the `/ask` endpoint.
 */
export interface AskResponseData {
  answer: string;
  source_documents?: { source: string; page: number | string }[];
  intermediate_steps?: IntermediateStep[];
}

/**
 * Basic information about an indexed document.
 * Added optional 'tag' and 'file_type'.
 */
export interface DocumentInfo {
    filename: string;
    tag?: string | null;
    file_type?: string | null;
}

/**
 * Response structure for the endpoint listing indexed documents.
 * Uses the updated DocumentInfo.
 */
export interface DocumentList {
    documents: DocumentInfo[];
}

/**
 * Response structure for the endpoint reporting the current AI provider status.
 */
export interface ProviderStatus {
    current_provider: 'ollama' | 'openai' | string;
    message: string;
}

/**
 * Payload structure for requesting an AI provider switch.
 */
export interface SetProviderPayload {
    provider: 'ollama' | 'openai';
}

// --- NEW: Interface for streamed data chunks ---
// Matches the events yielded by the backend service
export interface StreamEventData {
  token?: string;
  step?: IntermediateStep; // Re-use existing IntermediateStep type
  error?: string | { message: string }; // Can be simple string or object
}

// --- NEW: Callback types for stream events ---
export type StreamCallbacks = {
  onOpen?: () => void;
  onToken?: (token: string) => void;
  onStep?: (step: IntermediateStep) => void;
  onStepFinal?: (step: IntermediateStep) => void;
  onComplete?: () => void;
  onError?: (error: StreamEventData['error']) => void;
};

// --- API Functions ---

/**
 * Uploads a file with an optional tag to the backend /documents/upload endpoint.
 * @param payload - Contains the file and optional tag.
 * @returns Promise resolving to an object with filename and success message.
 */
export const uploadFile = async (payload: UploadFilePayload): Promise<{ filename: string; message: string }> => {
    console.log(`Uploading file: ${payload.file.name}, Tag: ${payload.tag || 'N/A'}`); // <<< Updated log
    const formData = new FormData();
    formData.append('file', payload.file);
    // --- Use 'tag' instead of 'category' ---
    if (payload.tag) {
        formData.append('tag', payload.tag); // <<< CHANGED key to 'tag'
    }
    // --------------------------------------

    const response = await fetch(`${API_BASE_URL}/documents/upload`, { // <<< Corrected endpoint path
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        let errorDetail = `Upload failed with status: ${response.status}`;
        try {
            const errorData = await response.json();
            errorDetail = errorData.detail || errorDetail;
        } catch (e) { /* Ignore */ }
        console.error("Upload API Error:", errorDetail);
        throw new Error(errorDetail);
    }
    return response.json();
};

/**
 * Sends a question to the backend agent's /ask endpoint.
 * Includes optional filename and tag filters.
 * @param payload - Contains the question, optional filters, and optional chat history.
 * @returns Promise resolving to the AskResponseData object.
 */
export const askQuestion = async (payload: AskPayload): Promise<AskResponseData> => {
    console.log("Sending request to /ask endpoint with payload:", payload);
    const response = await fetch(`${API_BASE_URL}/ask`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      // --- Use filenames list in the body ---
      body: JSON.stringify({
          question: payload.question,
          // Conditionally include filters
          ...(payload.filenames && payload.filenames.length > 0 && { filenames: payload.filenames }),
          ...(payload.tag_filter && { tag_filter: payload.tag_filter }),
          // Conditionally include chat history
          ...(payload.chat_history && { chat_history: payload.chat_history }),
      }),
      // ------------------------------------
    });

    if (!response.ok) {
      let errorDetail = `Request failed: ${response.status} ${response.statusText}`;
      try {
        const errorData = await response.json();
        errorDetail = errorData.detail || errorDetail;
      } catch (e) { /* Ignore */ }
      console.error("Ask question API error response:", { status: response.status, detail: errorDetail });
      throw new Error(errorDetail);
    }

    const responseData: AskResponseData = await response.json();
    console.log("Received response from /ask:", responseData);
    return responseData;
};

/**
 * Fetches the list of currently indexed documents (including tags) from the /documents endpoint.
 * @returns Promise resolving to the list of document info objects.
 */
export const getDocumentList = async (): Promise<DocumentList> => {
    console.log("Fetching document list (with tags)..."); // <<< Updated log
    const response = await fetch(`${API_BASE_URL}/documents`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
    });
    if (!response.ok) {
        let errorDetail = `Request failed: ${response.status} ${response.statusText}`;
        try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* ignore */ }
        console.error("Get document list error:", errorDetail);
        throw new Error(errorDetail);
    }
    // The response JSON structure should match DocumentList, which now uses
    // DocumentInfo including the optional 'tag'.
    const data: DocumentList = await response.json();
    console.log("Received document list:", data);
    return data;
};

/**
 * Deletes a specified document from the backend via the /documents/{filename} endpoint.
 * @param filename - The name of the file to delete.
 * @returns Promise resolving when deletion is successful (status 204). Throws error on failure.
 */
export const deleteDocument = async (filename: string): Promise<void> => {
    const encodedFilename = encodeURIComponent(filename);
    console.log(`Requesting deletion of document: ${filename} (Encoded: ${encodedFilename})`);
    const response = await fetch(`${API_BASE_URL}/documents/${encodedFilename}`, {
        method: 'DELETE',
    });

    if (response.status === 204) {
        console.log(`Successfully deleted ${filename}`);
        return; // Success (No Content)
    }

    // Handle error cases
    let errorDetail = `Failed to delete document: ${response.status} ${response.statusText}`;
    try {
        const errorData = await response.json();
        errorDetail = errorData.detail || errorDetail;
    } catch (e) { /* Ignore */ }
    console.error(`Delete document error for ${filename}:`, errorDetail);
    throw new Error(errorDetail);
};

/**
 * Fetches the current AI provider status from the /config/provider endpoint.
 * @returns Promise resolving to the provider status object.
 */
export const getCurrentProvider = async (): Promise<ProviderStatus> => {
    console.log("Fetching current AI provider status...");
    const response = await fetch(`${API_BASE_URL}/config/provider`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
    if (!response.ok) {
      let errorDetail = `Request failed: ${response.status} ${response.statusText}`;
      try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* ignore */ }
      console.error("Get provider status error:", errorDetail);
      throw new Error(errorDetail);
    }
    const data: ProviderStatus = await response.json();
    console.log("Received provider status:", data);
    return data;
};

/**
 * Sends a request to the backend to switch the active AI provider via /config/provider endpoint.
 * @param payload - Contains the desired provider ('ollama' or 'openai').
 * @returns Promise resolving to the updated provider status object.
 */
export const switchProvider = async (payload: SetProviderPayload): Promise<ProviderStatus> => {
    console.log(`Requesting switch to AI provider: ${payload.provider}`);
    const response = await fetch(`${API_BASE_URL}/config/provider`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      let errorDetail = `Request failed: ${response.status} ${response.statusText}`;
      try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; } catch (e) { /* ignore */ }
      console.error("Switch provider error:", errorDetail);
      throw new Error(errorDetail);
    }
    const data: ProviderStatus = await response.json();
    console.log("Received switch provider response:", data);
    return data;
};

/**
 * Sends a question to the backend's /ask-stream endpoint and handles the SSE stream.
 * @param payload - Contains the question, optional filters, and optional chat history.
 * @param callbacks - Object containing functions to handle stream events (onOpen, onToken, onStep, onComplete, onError).
 * @returns An AbortController instance to allow cancelling the stream.
 */
export const askQuestionStream = (
    payload: AskPayload,
    callbacks: StreamCallbacks
): AbortController => {
    console.log("Connecting to /ask-stream endpoint with payload:", payload);
    const abortController = new AbortController();
    const { onOpen, onToken, onStep, onComplete, onError } = callbacks;

    const fetchStream = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/ask-stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                },
                body: JSON.stringify(payload),
                signal: abortController.signal,
            });

            if (!response.ok) {
                let errorDetail = `Request failed: ${response.status} ${response.statusText}`;
                try {
                    const errorData = await response.json();
                    errorDetail = errorData.detail || errorData.error || errorDetail;
                } catch (e) { /* Ignore if response isn't JSON */ }
                console.error("Ask stream API error response:", { status: response.status, detail: errorDetail });
                if (onError) onError(errorDetail);
                if (onComplete) onComplete();
                return;
            }
            if (!response.body) {
                throw new Error('Response body is null');
            }

            // --- Revised Line-Based Parsing Logic --- 
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = ''; // Holds unprocessed data across reads
            let currentEvent: string | null = null;
            let currentData = '';

            if (onOpen) onOpen();

            while (true) {
                const { done, value } = await reader.read();
                
                // --- Log Raw Chunk --- 
                if (value) {
                    const rawChunk = decoder.decode(value, { stream: true });
                    console.debug(`[SSE Parser] Raw chunk received (decoded): "${rawChunk.replace(/\n/g, '\\n')}"`);
                    buffer += rawChunk; // Append new data chunk
                } else if (!done) {
                    console.debug("[SSE Parser] Received empty chunk value before done.");
                }
                // ---------------------

                console.debug(`[SSE Parser] Buffer state: "${buffer.replace(/\n/g, '\\n')}"`);

                if (done) {
                    console.log("[SSE Parser] Stream reading finished (done).");
                    // Process any final data left in the buffer
                    if (currentData) { // Check if we have data from a final non-terminated message
                        console.warn("[SSE Parser] Processing final data after stream closed.");
                        parseAndHandleSSEData(currentEvent, currentData, callbacks);
                    }
                    break; // Exit loop
                }

                // --- Renamed buffer variable to avoid conflict ---
                let internalBuffer = buffer;
                // -----------------------------------------------
                
                let lineEndIndex;
                // Process all complete lines (ending with \n) in the buffer
                while ((lineEndIndex = internalBuffer.indexOf('\n')) >= 0) {
                    const line = internalBuffer.substring(0, lineEndIndex).trim(); // Extract line, trim whitespace
                    internalBuffer = internalBuffer.substring(lineEndIndex + 1); // Remove processed line (and \n) from buffer

                    console.debug(`[SSE Parser] Processing line: "${line}"`); // <<< Log Line

                    if (line === '') {
                        console.debug("[SSE Parser] Empty line found (message terminator)."); // <<< Log Terminator
                        // Empty line: Dispatch the accumulated message
                        if (currentData) {
                            parseAndHandleSSEData(currentEvent, currentData, callbacks);
                        }
                        // Reset for next message
                        currentEvent = null;
                        currentData = '';
                    } else if (line.startsWith('event:')) {
                        currentEvent = line.substring(6).trim();
                    } else if (line.startsWith('data:')) {
                        // Append data, handling potential multi-line data fields
                        const dataContent = line.substring(5).trim();
                        currentData = currentData ? `${currentData}\n${dataContent}` : dataContent;
                    } else if (line.startsWith(':')) {
                        // Ignore SSE comments
                    } 
                    // Ignore other lines (like id:)
                }
                 // Update the main buffer with any remaining unprocessed part
                buffer = internalBuffer;
                // Loop continues, buffer now contains only the potentially incomplete trailing part of the last chunk
            }
        } catch (error: any) {
            if (error.name === 'AbortError') {
                console.log('Stream fetch aborted by client.');
            } else {
                console.error('Error reading or fetching stream:', error);
                if (onError) onError(`Stream connection error: ${error.message || error}`);
            }
        } finally {
             console.log("[SSE Parser] Stream processing loop finished or errored.");
             if (onComplete) onComplete();
        }
    };

    // Helper function remains the same
    const parseAndHandleSSEData = (event: string | null, data: string, cbs: StreamCallbacks) => {
        const eventType = event || 'message';
        try {
            const parsedData: StreamEventData = JSON.parse(data);
             console.debug(`[SSE Parser] Parsed data for event '${eventType}':`, parsedData);

            if (eventType === 'token' && parsedData.token !== undefined && cbs.onToken) {
                cbs.onToken(parsedData.token);
            } else if (eventType === 'step' && parsedData.step && cbs.onStep) {
                console.log("[SSE Parser] Identified 'step' event (Partial). Calling onStep with:", parsedData.step);
                cbs.onStep(parsedData.step);
            } else if (eventType === 'step_final' && parsedData.step && cbs.onStepFinal) {
                console.log("[SSE Parser] Identified 'step_final' event (Full). Calling onStepFinal with:", parsedData.step);
                console.log('[SSE Parser] Received step_final event data:', parsedData);
                cbs.onStepFinal(parsedData.step);
            } else if (eventType === 'error' && parsedData.error && cbs.onError) {
                cbs.onError(parsedData.error);
            } else if (eventType === 'end') {
                console.log("[SSE Parser] Received 'end' event via data stream.");
            } else if (eventType === 'message') {
                 console.warn("[SSE Parser] Received unnamed 'message' event:", parsedData);
             }
        } catch (e) {
            console.error('[SSE Parser] Failed to parse SSE JSON data:', data, e);
            if (cbs.onError) cbs.onError(`Failed to parse stream data: ${e}`);
        }
    };

    fetchStream();
    return abortController;
};