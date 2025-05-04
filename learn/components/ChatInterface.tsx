// components/ChatInterface.tsx
'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
    askQuestionStream,
    StreamCallbacks,
    Message as ApiMessage,
    AskPayload,
    IntermediateStep,
    AgentAction,
    DocumentInfo,
} from '@/lib/api';
import Message from '@/components/chat/Message';
import UploadDropdown, { UploadDropdownRef } from '@/components/common/UploadDropdown';
import ChatMessages from './chat/ChatMessages';
import ChatInputArea from './chat/ChatInputArea';
import { cn } from '@/lib/utils';

// --- Define Props Interface ---
interface ChatInterfaceProps {
    selectedFilenames: Set<string>;
    onFilenameToggle: (filename: string | null) => void;
    selectedTag: string | null;
    triggerDocListRefresh: number;
    onDocumentsManaged: () => void;
}

const ALL_DOCUMENTS_VALUE = 'all'; // Consider moving to constants file

// --- ADD Type Guard --- 
function isAgentAction(action: any): action is AgentAction {
    // Check for null explicitly as typeof null is 'object'
    // Also check if the necessary properties exist
    return typeof action === 'object' && action !== null && 'tool' in action && 'tool_input' in action;
}
// --------------------

export default function ChatInterface({
    selectedFilenames,
    onFilenameToggle,
    selectedTag,
    triggerDocListRefresh,
    onDocumentsManaged
}: ChatInterfaceProps) {
    // --- State ---
    const [messages, setMessages] = useState<ApiMessage[]>([]);
    const [input, setInput] = useState('');
    const [isAsking, setIsAsking] = useState(false);
    const [askError, setAskError] = useState<string | null>(null);
    const [currentAIMessageId, setCurrentAIMessageId] = useState<string | null>(null);

    // --- Refs ---
    const uploadDropdownRef = useRef<UploadDropdownRef>(null);
    const streamAbortController = useRef<AbortController | null>(null);

    // --- Input Handling ---
    const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
        setInput(event.target.value);
    };

    // --- Stop Streaming ---
    const stopStreaming = useCallback(() => {
        if (streamAbortController.current) {
            console.log("[ChatInterface] stopStreaming: Aborting stream controller.");
            streamAbortController.current.abort();
            streamAbortController.current = null;
            setIsAsking(false);
            setCurrentAIMessageId(null);
        } else {
            console.log("[ChatInterface] stopStreaming: No active stream controller to abort.");
        }
    }, []);

    // --- Submit Handler (Handles Streaming) ---
    const handleSubmit = useCallback(async (event?: React.FormEvent) => {
        if (event) event.preventDefault();
        if (isAsking) { stopStreaming(); return; }
        if (!input.trim()) return;

        const currentInput = input;
        const userMessageId = `user-${Date.now()}`;
        const aiMessageId = `ai-${Date.now()}`;

        console.log(`[ChatInterface] handleSubmit: Starting new request. UserMsgID: ${userMessageId}, AIMsgID: ${aiMessageId}`);

        setInput('');
        setIsAsking(true);
        setAskError(null);
        setCurrentAIMessageId(aiMessageId);

        // Add user message and placeholder AI message
        setMessages(prev => [
            ...prev,
            { id: userMessageId, sender: 'user', text: currentInput },
            { id: aiMessageId, sender: 'ai', text: '', intermediate_steps: [] }
        ]);

        try {
            const filenamesArray = Array.from(selectedFilenames);
            const historyToSend = messages.filter(m => m.id !== aiMessageId); // Exclude placeholder from history sent
            const payload: AskPayload = {
                question: currentInput,
                filenames: filenamesArray.length > 0 ? filenamesArray : undefined,
                tag_filter: selectedTag === ALL_DOCUMENTS_VALUE ? undefined : selectedTag,
                chat_history: historyToSend,
            };
            console.log("[ChatInterface] handleSubmit: Sending payload to askQuestionStream:", payload);

            // Define callbacks for the stream
            const callbacks: StreamCallbacks = {
                onOpen: () => {
                    console.log(`[ChatInterface] Stream opened for AIMsgID: ${aiMessageId}.`);
                },
                onToken: (token) => {
                    setMessages(prev => prev.map(msg =>
                        msg.id === aiMessageId
                            ? { ...msg, text: msg.text + token }
                            : msg
                    ));
                },
                onStep: (step) => {
                    console.log("[ChatInterface] onStep callback triggered. Step data:", JSON.stringify(step, null, 2));
                    // Create a placeholder observation if it's an AgentAction
                    const stepToAdd = isAgentAction(step.action)
                        ? { ...step, observation: '⏳ Processing...' } // Add placeholder observation
                        : step; 

                    setMessages(prev => {
                        const targetMsgIndex = prev.findIndex(m => m.id === aiMessageId);
                        if (targetMsgIndex === -1) return prev; // Message not found

                        const targetMsg = prev[targetMsgIndex];
                        const updatedSteps = [...(targetMsg.intermediate_steps || []), stepToAdd]; // Add the new step (potentially with placeholder)
                        const updatedMsg = { ...targetMsg, intermediate_steps: updatedSteps };

                        const newMessages = [...prev];
                        newMessages[targetMsgIndex] = updatedMsg;
                        console.log(`[ChatInterface] setMessages (onStep). Adding partial step to message ${aiMessageId}.`);
                        return newMessages;
                    });
                },
                onStepFinal: (finalStep) => {
                    console.log(`[ChatInterface] onStepFinal CALLED. Final Step received:`, JSON.stringify(finalStep, null, 2));
                    setMessages(prev => {
                        const targetMsgIndex = prev.findIndex(m => m.id === aiMessageId);
                        if (targetMsgIndex === -1) return prev;

                        const targetMsg = prev[targetMsgIndex];
                        const existingSteps = targetMsg.intermediate_steps || [];
                        
                        // --- Find the partial step index (logic remains the same) ---
                        let partialStepIndex = -1;
                        if (isAgentAction(finalStep.action)) {
                            const guardedFinalAction = finalStep.action;
                            partialStepIndex = existingSteps.findIndex(s => {
                                if (!isAgentAction(s.action)) return false;
                                const currentAction: AgentAction = s.action;
                                return (
                                    currentAction.tool === guardedFinalAction.tool &&
                                    JSON.stringify(currentAction.tool_input) === JSON.stringify(guardedFinalAction.tool_input) &&
                                    s.observation === "⏳ Processing..."
                                );
                            });
                        } else {
                            console.warn("[ChatInterface] onStepFinal received step where action is not object:", finalStep.action);
                        }
                        // --------------------------------------------------------------

                        // --- Create the new steps array --- 
                        let newStepsArray;
                        if (partialStepIndex !== -1) {
                            newStepsArray = [...existingSteps]; // Create a new array
                            newStepsArray[partialStepIndex] = finalStep; // Replace the item
                            console.log(`[ChatInterface] Found partial step at index ${partialStepIndex}. Preparing updated steps array.`);
                        } else {
                            console.warn(`[ChatInterface] Partial step not found for final step. Appending.`);
                            // Avoid appending duplicates if the step somehow already exists fully.
                            const alreadyExists = existingSteps.some(s => JSON.stringify(s) === JSON.stringify(finalStep));
                            newStepsArray = alreadyExists ? existingSteps : [...existingSteps, finalStep];
                        }

                        // --- Create a COMPLETELY NEW message object --- 
                        const updatedMessage: ApiMessage = {
                            ...targetMsg, // Copy existing properties (id, sender, text etc.)
                            intermediate_steps: newStepsArray, // Assign the new steps array
                        };
                        // ---------------------------------------------

                        // --- Update the messages array --- 
                        const newMessages = [...prev]; // Create new messages array
                        newMessages[targetMsgIndex] = updatedMessage; // Replace the old message object with the new one
                        console.log(`[ChatInterface] Replacing message at index ${targetMsgIndex} with updated steps.`);
                        return newMessages;
                        // ---------------------------------
                    });
                },
                onError: (error) => {
                    const errorMsg = typeof error === 'string' ? error : (error as any)?.message || "An unknown streaming error occurred.";
                    console.error(`[ChatInterface] Stream error for AIMsgID: ${aiMessageId}:`, errorMsg);
                    setAskError(errorMsg);
                    // Append error to the message, or handle differently
                    setMessages(prev => prev.map(msg =>
                        msg.id === aiMessageId
                            ? { ...msg, text: (msg.text || '') + `\n\n**Error:** ${errorMsg}` }
                            : msg
                    ));
                    setCurrentAIMessageId(null);
                    setIsAsking(false);
                    if (streamAbortController.current) { streamAbortController.current = null; }
                },
                onComplete: () => {
                    console.log(`[ChatInterface] Stream completed for AIMsgID: ${aiMessageId}.`);
                    setIsAsking(false);
                    setCurrentAIMessageId(null);
                    streamAbortController.current = null;
                },
            }; // End callbacks

            // Start the stream
            streamAbortController.current = askQuestionStream(payload, callbacks);

        } catch (error: any) {
            // Catch errors *setting up* the stream
            console.error("[ChatInterface] handleSubmit: Error setting up stream:", error);
            setAskError(error.message || "Failed to start streaming connection.");
            setMessages(prev => prev.filter(msg => msg.id !== aiMessageId && msg.id !== userMessageId)); // Clean up optimistic messages
            setInput(currentInput); // Restore user input
            setIsAsking(false);
            setCurrentAIMessageId(null);
            if (streamAbortController.current) { streamAbortController.current.abort(); streamAbortController.current = null; }
        }
    }, [ input, isAsking, selectedFilenames, selectedTag, messages, stopStreaming ]); // Dependencies

    // --- Keyboard Shortcut ---
    const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (!isAsking && input.trim()) {
                handleSubmit();
            }
        }
    };

    // --- Helper to Get Scope Text for Display ---
    const getScopeText = (): string => {
        const filenamesArray = Array.from(selectedFilenames);
        const hasFiles = filenamesArray.length > 0;
        const hasTag = selectedTag && selectedTag !== ALL_DOCUMENTS_VALUE;

        if (!hasFiles && !hasTag) return "All Documents";
        let fileText = hasFiles ? (filenamesArray.length === 1 ? `File: ${filenamesArray[0]}` : `${filenamesArray.length} Files`) : '';
        let tagText = hasTag ? `Tag: ${selectedTag}` : '';
        return fileText && tagText ? `${fileText} (${tagText})` : fileText || tagText;
    };

    // --- Effect to focus input when not asking ---
    // Assuming ChatInputArea handles its own focus based on isAsking prop is simpler.
    // If needed, restore focus logic here using a ref passed to ChatInputArea.
    useEffect(() => {
        if (!isAsking) {
            // Optional: Focus logic if managed here
             // console.log("[ChatInterface] Attempting to focus input.");
             // const timer = setTimeout(() => { /* focus element */ }, 50);
             // return () => clearTimeout(timer);
        }
    }, [isAsking]);


    // --- Render ---
    return (
        <div className="flex flex-col flex-grow border rounded-lg shadow-sm bg-background overflow-hidden h-full">
            {/* Hidden Upload Component */}
            <UploadDropdown
                ref={uploadDropdownRef}
                onUploadComplete={(success) => {
                    console.log(`[ChatInterface] Upload complete. Success: ${success}`);
                    if (success) { onDocumentsManaged(); }
                }}
            />

            {/* Messages Area */}
            <ChatMessages
                messages={messages}
                isAsking={isAsking}
                currentAIMessageId={currentAIMessageId}
            />

            {/* Input Area */}
            <ChatInputArea
                input={input}
                handleInputChange={handleInputChange}
                handleKeyDown={handleKeyDown}
                handleSubmit={handleSubmit}
                isAsking={isAsking}
                stopStreaming={stopStreaming}
                askError={askError}
                selectedFilenames={selectedFilenames}
                selectedTag={selectedTag}
                onFilenameToggle={onFilenameToggle}
                uploadDropdownRef={uploadDropdownRef}
                triggerDocListRefresh={triggerDocListRefresh}
                getScopeText={getScopeText}
                onDocumentsManaged={onDocumentsManaged}
            />
        </div>
    );
}