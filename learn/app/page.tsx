// app/page.tsx
'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
    Message as ApiMessage,
    IntermediateStep,
    AskPayload,
    StreamCallbacks,
    askQuestionStream,
    DocumentInfo // Import DocumentInfo type
} from '@/lib/api'; // Ensure API functions and types are imported

// Import Components
import ThemeToggle from '@/components/ui/ThemeToggle';
import ModelSelector from '@/components/common/ModelSelector';
import { UploadDropdownRef } from '@/components/common/UploadDropdown';
import UploadDropdown from '@/components/common/UploadDropdown';
import CollapsibleSidebar from '@/components/layout/CollapsibleSidebar'; // Import new layout component
import IntegratedInput from '@/components/chat/IntegratedInput'; // Import new input component
import ChatMessages from '@/components/chat/ChatMessages'; // Import the actual ChatMessages
import StepsDisplay from '@/components/chat/StepsDisplay'; // Import the StepsDisplay component

// Constants
const ALL_DOCUMENTS_VALUE = 'all';

// --- Main Page Component ---
export default function Home() {
    // --- Core Chat State ---
    const [messages, setMessages] = useState<ApiMessage[]>([]);
    const [input, setInput] = useState('');
    const [isAsking, setIsAsking] = useState(false);
    const [askError, setAskError] = useState<string | null>(null);
    const [currentAIMessageId, setCurrentAIMessageId] = useState<string | null>(null);
    const streamAbortController = useRef<AbortController | null>(null);

    // --- Document Scope & Management State ---
    const [selectedFilenames, setSelectedFilenames] = useState<Set<string>>(new Set());
    const [selectedTag, setSelectedTag] = useState<string | null>(null); // Keep for potential future tag filtering in sidebar
    const [refreshDocListTrigger, setRefreshDocListTrigger] = useState(0);
    const uploadDropdownRef = useRef<UploadDropdownRef>(null);

    // --- UI Layout State ---
    const [isSidebarOpen, setIsSidebarOpen] = useState(true); // Sidebar starts open
    const [activeContextSteps, setActiveContextSteps] = useState<IntermediateStep[] | null>(null);
    const [activeContextMessageId, setActiveContextMessageId] = useState<string | null>(null);

    // --- Document Management Callbacks ---
    const triggerDocListRefresh = useCallback(() => {
        setRefreshDocListTrigger(prev => prev + 1);
        console.log("Document list refresh triggered from page.");
    }, []);

    // --- Scope Selection Callbacks (Passed to Sidebar) ---
    const handleFilenameSelectionToggle = useCallback((filename: string | null) => {
        if (filename === null) {
            setSelectedFilenames(new Set()); // Clear selection for "All Documents"
            return;
        }
        setSelectedFilenames(prev => {
            const newSet = new Set(prev);
            if (newSet.has(filename)) {
                newSet.delete(filename);
            } else {
                // Maybe implement single-select logic if desired?
                // For multi-select:
                newSet.add(filename);
            }
            console.log("Selected filenames changed:", newSet);
            return newSet;
        });
    }, []);

    // --- UI Callbacks ---
    const toggleSidebar = useCallback(() => {
        setIsSidebarOpen(prev => !prev);
    }, []);

    const showStepsForMessage = useCallback((messageId: string | null) => {
        if (messageId === null || messageId === activeContextMessageId) { // Allow toggling off
            setActiveContextMessageId(null);
            setActiveContextSteps(null);
            return;
        }
        const targetMsg = messages.find(m => m.id === messageId);
        // Only show context for AI messages that actually have steps
        if (targetMsg && targetMsg.sender === 'ai' && targetMsg.intermediate_steps && targetMsg.intermediate_steps.length > 0) {
            setActiveContextMessageId(messageId);
            setActiveContextSteps(targetMsg.intermediate_steps);
            console.log(`Showing context/steps for message ${messageId}`);
        } else {
            // Clear context if clicking a user message or AI message without steps
             setActiveContextMessageId(null);
             setActiveContextSteps(null);
        }
    }, [messages, activeContextMessageId]); // Dependencies

    // --- Chat Logic Callbacks ---
    const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement> | string) => {
        setInput(typeof event === 'string' ? event : event.target.value);
    };

    const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault(); // Prevent newline
            handleSubmit(); // Trigger submit logic
        }
    };

    const stopStreaming = useCallback(() => {
        if (streamAbortController.current) {
            console.log("[Page] stopStreaming: Aborting stream controller.");
            streamAbortController.current.abort();
            streamAbortController.current = null;
        } else {
            console.log("[Page] stopStreaming: No active stream controller to abort.");
        }
        setIsAsking(false);
        setCurrentAIMessageId(null);
        // Decide whether to clear context pane on stop - perhaps keep steps visible?
        // showStepsForMessage(null);
    }, [/* showStepsForMessage? */]); // Add dependencies if needed

    const handleSubmit = useCallback(async (event?: React.FormEvent | string) => {
        let query = '';
        if (typeof event === 'string') {
            query = event;
        } else {
            if (event) event.preventDefault();
            query = input;
        }

        if (isAsking) { stopStreaming(); return; }
        if (!query.trim()) return;

        const userMessageId = `user-${Date.now()}`;
        const aiMessageId = `ai-${Date.now()}`;

        console.log(`[Page] handleSubmit: Starting request. UserMsgID: ${userMessageId}, AIMsgID: ${aiMessageId}`);

        setInput('');
        setIsAsking(true);
        setAskError(null);
        setCurrentAIMessageId(aiMessageId);
        showStepsForMessage(aiMessageId); // Activate context pane for the new AI message

        const newUserMessage: ApiMessage = { id: userMessageId, sender: 'user', text: query };
        const newAiMessagePlaceholder: ApiMessage = { id: aiMessageId, sender: 'ai', text: '', intermediate_steps: [] };
        setMessages(prev => [...prev, newUserMessage, newAiMessagePlaceholder]);

        try {
            const filenamesArray = Array.from(selectedFilenames);
            const historyToSend = messages.map(m => ({ sender: m.sender, text: m.text }));

            const payload: AskPayload = {
                question: query,
                filenames: filenamesArray.length > 0 ? filenamesArray : undefined,
                tag_filter: selectedTag === ALL_DOCUMENTS_VALUE ? undefined : selectedTag,
                chat_history: historyToSend.length > 0 ? historyToSend : undefined,
            };
            console.log("[Page] handleSubmit: Sending payload:", payload);

            const callbacks: StreamCallbacks = {
                onOpen: () => console.log(`[Page] Stream opened for AIMsgID: ${aiMessageId}.`),
                onToken: (token) => {
                    setMessages(prev => prev.map(msg =>
                        msg.id === aiMessageId ? { ...msg, text: msg.text + token } : msg
                    ));
                },
                onStep: (step) => {
                    console.log("[Page] onStep:", JSON.stringify(step));
                    const stepToAdd = (typeof step.action === 'object' && step.action !== null && 'tool' in step.action)
                        ? { ...step, observation: '⏳ Processing...' }
                        : step;

                    setMessages(prev => {
                        const msgIndex = prev.findIndex(m => m.id === aiMessageId);
                        if (msgIndex === -1) return prev;
                        const targetMsg = prev[msgIndex];
                        const updatedSteps = [...(targetMsg.intermediate_steps || []), stepToAdd];
                        const updatedMsg = { ...targetMsg, intermediate_steps: updatedSteps };
                        if (activeContextMessageId === aiMessageId) setActiveContextSteps(updatedSteps);
                        const newMessages = [...prev];
                        newMessages[msgIndex] = updatedMsg;
                        return newMessages;
                    });
                },
                onStepFinal: (finalStep) => {
                    console.log(`[Page] onStepFinal:`, JSON.stringify(finalStep));
                     setMessages(prev => {
                        const msgIndex = prev.findIndex(m => m.id === aiMessageId);
                        if (msgIndex === -1) return prev;
                        const targetMsg = prev[msgIndex];
                        const existingSteps = targetMsg.intermediate_steps || [];

                        let partialStepIndex = -1;
                        if (typeof finalStep.action === 'object' && finalStep.action !== null && 'tool' in finalStep.action) {
                            const finalAction = finalStep.action;
                            partialStepIndex = existingSteps.findIndex(s =>
                                s.observation === "⏳ Processing..." &&
                                typeof s.action === 'object' && s.action !== null && 'tool' in s.action &&
                                s.action.tool === finalAction.tool &&
                                JSON.stringify(s.action.tool_input) === JSON.stringify(finalAction.tool_input)
                            );
                        }

                        let newStepsArray;
                        if (partialStepIndex !== -1) {
                            newStepsArray = [...existingSteps];
                            newStepsArray[partialStepIndex] = finalStep;
                            console.log(`[Page] Replacing partial step at index ${partialStepIndex}.`);
                        } else {
                            console.warn(`[Page] Partial step not found for final step. Appending.`);
                            const alreadyExists = existingSteps.some(s => JSON.stringify(s) === JSON.stringify(finalStep));
                            newStepsArray = alreadyExists ? existingSteps : [...existingSteps, finalStep];
                        }

                        const updatedMsg = { ...targetMsg, intermediate_steps: newStepsArray };
                        if (activeContextMessageId === aiMessageId) setActiveContextSteps(newStepsArray);
                        const newMessages = [...prev];
                        newMessages[msgIndex] = updatedMsg;
                        return newMessages;
                    });
                },
                onError: (error) => {
                    const errorMsg = typeof error === 'string' ? error : (error as any)?.message || "Streaming error.";
                    console.error(`[Page] Stream error for AIMsgID: ${aiMessageId}:`, errorMsg);
                    setAskError(errorMsg);
                    setMessages(prev => prev.map(msg =>
                        msg.id === aiMessageId ? { ...msg, text: (msg.text || '') + `\n\n**Error:** ${errorMsg}` } : msg
                    ));
                    stopStreaming();
                },
                onComplete: () => {
                    console.log(`[Page] Stream completed for AIMsgID: ${aiMessageId}.`);
                    setIsAsking(false);
                    setCurrentAIMessageId(null);
                    streamAbortController.current = null;
                },
            };

            streamAbortController.current = askQuestionStream(payload, callbacks);

        } catch (error: any) {
            console.error("[Page] handleSubmit: Error setting up stream:", error);
            setAskError(error.message || "Failed to start connection.");
            setMessages(prev => prev.filter(msg => msg.id !== aiMessageId && msg.id !== userMessageId));
            setInput(query);
            setIsAsking(false);
            setCurrentAIMessageId(null);
            showStepsForMessage(null);
            if (streamAbortController.current) { streamAbortController.current = null; }
        }
    }, [input, isAsking, selectedFilenames, selectedTag, messages, stopStreaming, showStepsForMessage, activeContextMessageId]);


    // Helper to Get Scope Text for Display
    const getScopeText = (): string => {
        const filenamesArray = Array.from(selectedFilenames);
        const hasFiles = filenamesArray.length > 0;
        if (!hasFiles) return "All Documents";
        if (filenamesArray.length === 1) return `File: ${filenamesArray[0]}`;
        return `${filenamesArray.length} Files Selected`;
    };


    // --- Render the New Layout ---
    return (
        <div className="flex flex-col h-screen max-h-screen bg-background text-foreground overflow-hidden">

            {/* Hidden Upload Component */}
            <UploadDropdown
                ref={uploadDropdownRef}
                onUploadComplete={(success) => { if (success) { triggerDocListRefresh(); } }}
            />

            {/* Top Bar */}
            <header className="h-14 flex-shrink-0 border-b flex items-center justify-between px-4">
                <div>
                    <span className="font-bold text-lg">N</span>
                </div>
                <div className="flex items-center gap-2">
                    <ModelSelector />
                    <ThemeToggle />
                </div>
            </header>

            {/* Main Content Area */}
            <main className="flex flex-grow overflow-hidden">

                 {/* Collapsible Sidebar */}
                 <CollapsibleSidebar
                     isOpen={isSidebarOpen}
                     onToggle={toggleSidebar}
                     selectedFilenames={selectedFilenames}
                     onFilenameToggle={handleFilenameSelectionToggle}
                     triggerRefresh={refreshDocListTrigger}
                     onDocumentsManaged={triggerDocListRefresh}
                     uploadDropdownRef={uploadDropdownRef}
                 />

                 {/* Center Interaction Pane */}
                 <section className="flex-grow flex flex-col overflow-hidden border-r"> {/* Added border */}
                    {/* Use the actual ChatMessages component */}
                    <ChatMessages
                        messages={messages}
                        isAsking={isAsking}
                        currentAIMessageId={currentAIMessageId}
                        activeContextMessageId={activeContextMessageId}
                        onShowContext={showStepsForMessage}
                    />

                     {/* Integrated Input Area Component */}
                    <IntegratedInput
                        input={input}
                        handleInputChange={handleInputChange}
                        handleSubmit={handleSubmit}
                        handleKeyDown={handleKeyDown} // Pass the keydown handler
                        stopStreaming={stopStreaming}
                        isAsking={isAsking}
                        askError={askError}
                        scopeText={getScopeText()}
                        onToggleSidebar={toggleSidebar} // Pass sidebar toggle
                    />
                 </section>

                 {/* Right Context Pane */}
                 <div className="w-80 flex-shrink-0 bg-card overflow-y-auto"> {/* // Structure for ContextPane */}
                     {/* Use the actual StepsDisplay component */}
                     <StepsDisplay steps={activeContextSteps} />
                 </div>

            </main>
        </div>
    );
}