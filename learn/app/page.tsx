// app/page.tsx
'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
    Message as ApiMessage,
    IntermediateStep,
    AskPayload,
    StreamCallbacks,
    askQuestionStream,
    DocumentInfo,
    RagContextDocument,
    AgentAction // Import type
} from '@/lib/api';

// Import Components
import ThemeToggle from '@/components/ui/ThemeToggle';
import ModelSelector from '@/components/common/ModelSelector';
import { UploadDropdownRef } from '@/components/common/UploadDropdown';
import UploadDropdown from '@/components/common/UploadDropdown';
import CollapsibleSidebar from '@/components/layout/CollapsibleSidebar';
import IntegratedInput from '@/components/chat/IntegratedInput';
import ChatMessages from '@/components/chat/ChatMessages';
import StepsDisplay from '@/components/chat/StepsDisplay'; // Displays raw steps
import RagContextDisplay from '@/components/chat/RagContextDisplay'; // Displays RAG context
import ObservationDisplay from '@/components/chat/ObservationDisplay'; // Displays formatted observations

// Import Icons
import { Info, Terminal } from 'lucide-react';

// Constants
const ALL_DOCUMENTS_VALUE = 'all';

// --- Helper Type Guard ---
function isAgentAction(action: any): action is AgentAction {
    return typeof action === 'object' && action !== null && 'tool' in action && 'tool_input' in action;
}

// --- Main Page Component ---
export default function Home() {
    // --- Core Chat State ---
    const [messages, setMessages] = useState<ApiMessage[]>([]);
    const [input, setInput] = useState('');
    const [isAsking, setIsAsking] = useState(false);
    const [askError, setAskError] = useState<string | null>(null);
    const [currentAIMessageId, setCurrentAIMessageId] = useState<string | null>(null); // Still useful for tracking stream target
    const streamAbortController = useRef<AbortController | null>(null);

    // --- Document Scope & Management State ---
    const [selectedFilenames, setSelectedFilenames] = useState<Set<string>>(new Set());
    const [selectedTag, setSelectedTag] = useState<string | null>(null);
    const [refreshDocListTrigger, setRefreshDocListTrigger] = useState(0);
    const uploadDropdownRef = useRef<UploadDropdownRef>(null);

    // --- UI Layout & Context State ---
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    // --- State for Right Pane Content ---
    const [activeContextSteps, setActiveContextSteps] = useState<IntermediateStep[] | null>(null); // Holds raw steps
    const [activeRagContext, setActiveRagContext] = useState<RagContextDocument[] | null>(null); // Holds RAG snippets
    const [activeObservationData, setActiveObservationData] = useState<any | null>(null); // Holds structured observation
    const [activeObservationTool, setActiveObservationTool] = useState<string | null>(null); // Holds the tool name for observation
    // --- Removed activeContextMessageId ---

    // --- Document Management Callbacks ---
    const triggerDocListRefresh = useCallback(() => {
        setRefreshDocListTrigger(prev => prev + 1);
        console.log("Document list refresh triggered from page.");
    }, []);

    // --- Scope Selection Callbacks ---
    const handleFilenameSelectionToggle = useCallback((filename: string | null) => {
        if (filename === null) { setSelectedFilenames(new Set()); return; }
        setSelectedFilenames(prev => {
            const newSet = new Set(prev);
            if (newSet.has(filename)) { newSet.delete(filename); } else { newSet.add(filename); }
            console.log("Selected filenames changed:", newSet);
            return newSet;
        });
    }, []);

    // --- UI Callbacks ---
    const toggleSidebar = useCallback(() => { setIsSidebarOpen(prev => !prev); }, []);

    // --- Removed showContextForMessage callback ---

    // --- Chat Logic Callbacks ---
    const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement> | string) => {
        setInput(typeof event === 'string' ? event : event.target.value);
    };

    const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            handleSubmit();
        }
    };

    // --- Updated stopStreaming to clear all context displays ---
    const stopStreaming = useCallback(() => {
        if (streamAbortController.current) {
            streamAbortController.current.abort(); streamAbortController.current = null;
            console.log("[Page] Stream aborted.");
        } else { console.log("[Page] No active stream to abort."); }
        setIsAsking(false);
        setCurrentAIMessageId(null);
        setActiveRagContext(null);
        setActiveObservationData(null);
        setActiveObservationTool(null);
        setActiveContextSteps(null); // Also clear raw steps display on stop
    }, []);

    // --- Updated handleSubmit for Automatic Context Display ---
    const handleSubmit = useCallback(async (event?: React.FormEvent | string) => {
        let query = '';
        if (typeof event === 'string') { query = event; }
        else { if (event) event.preventDefault(); query = input; }
        if (isAsking) { stopStreaming(); return; }
        if (!query.trim()) return;

        const userMessageId = `user-${Date.now()}`;
        const aiMessageId = `ai-${Date.now()}`;
        console.log(`[Page] handleSubmit: UserMsg=${userMessageId}, AIMsg=${aiMessageId}`);

        setInput(''); setIsAsking(true); setAskError(null);
        setCurrentAIMessageId(aiMessageId);
        // Clear all right-pane displays immediately
        setActiveContextSteps(null);
        setActiveRagContext(null);
        setActiveObservationData(null);
        setActiveObservationTool(null);

        const newUserMessage: ApiMessage = { id: userMessageId, sender: 'user', text: query };
        const newAiMessagePlaceholder: ApiMessage = { id: aiMessageId, sender: 'ai', text: '', intermediate_steps: [] };
        setMessages(prev => [...prev, newUserMessage, newAiMessagePlaceholder]);

        try {
            const filenamesArray = Array.from(selectedFilenames);
            const historyToSend = messages.map(m => ({ sender: m.sender, text: m.text }));
            const payload: AskPayload = { question: query, filenames: filenamesArray.length > 0 ? filenamesArray : undefined, tag_filter: selectedTag === ALL_DOCUMENTS_VALUE ? undefined : selectedTag, chat_history: historyToSend.length > 0 ? historyToSend : undefined };
            console.log("[Page] Sending payload:", payload);

            // --- Define Stream Callbacks for Automatic Context Display ---
            const callbacks: StreamCallbacks = {
                onOpen: () => console.log(`[Page] Stream opened: ${aiMessageId}`),

                onToken: (token) => {
                    // Clear RAG/Observation when final answer starts streaming
                    setActiveRagContext(null);
                    setActiveObservationData(null);
                    setActiveObservationTool(null);
                    // Leave Steps potentially visible if they arrived before tokens
                    // setActiveContextSteps(null); // Optional: clear steps too
                    setMessages(prev => prev.map(msg => msg.id === aiMessageId ? { ...msg, text: msg.text + token } : msg));
                },

                onRagContext: (contextDocs) => {
                    console.log(`[Page] RAG Context received (${contextDocs.length} docs)`);
                    // Display RAG context, clear others
                    setActiveContextSteps(null);
                    setActiveObservationData(null);
                    setActiveObservationTool(null);
                    setActiveRagContext(contextDocs);
                },

                onStep: (step) => {
                    console.log("[Page] onStep (Partial):", step.action);
                    // Display raw steps, clear others
                    setActiveRagContext(null);
                    setActiveObservationData(null);
                    setActiveObservationTool(null);
                    const stepToAdd = isAgentAction(step.action) ? { ...step, observation: '⏳ Processing...' } : step;
                    // Add step to message state AND display raw steps
                    setMessages(prev => {
                        const msgIndex = prev.findIndex(m => m.id === aiMessageId);
                        if (msgIndex === -1) return prev;
                        const targetMsg = prev[msgIndex];
                        const updatedSteps = [...(targetMsg.intermediate_steps || []), stepToAdd];
                        const updatedMsg = { ...targetMsg, intermediate_steps: updatedSteps };
                        setActiveContextSteps(updatedSteps); // Update right pane with steps
                        const newMessages = [...prev]; newMessages[msgIndex] = updatedMsg;
                        return newMessages;
                    });
                },

                onStepFinal: (finalStep) => {
                    console.log("[Page] onStepFinal:", finalStep.action);
                    setActiveRagContext(null); // Clear RAG display

                    let toolName: string | null = null;
                    if (isAgentAction(finalStep.action)) {
                        toolName = finalStep.action.tool ?? null;
                    }
                    const observation = finalStep.observation;

                    // Update message state first (replace partial step)
                    setMessages(prev => {
                        const msgIndex = prev.findIndex(m => m.id === aiMessageId);
                        if (msgIndex === -1) return prev;
                        const targetMsg = prev[msgIndex];
                        const existingSteps = targetMsg.intermediate_steps || [];
                        const partialStepIndex = existingSteps.findIndex(s => s.observation === "⏳ Processing..." && isAgentAction(s.action) && isAgentAction(finalStep.action) && s.action.tool === finalStep.action.tool && JSON.stringify(s.action.tool_input) === JSON.stringify(finalStep.action.tool_input));
                        let newStepsArray;
                        if (partialStepIndex !== -1) { newStepsArray = [...existingSteps]; newStepsArray[partialStepIndex] = finalStep; }
                        else { const alreadyExists = existingSteps.some(s => JSON.stringify(s) === JSON.stringify(finalStep)); newStepsArray = alreadyExists ? existingSteps : [...existingSteps, finalStep]; }
                        const updatedMsg = { ...targetMsg, intermediate_steps: newStepsArray };
                        const newMessages = [...prev]; newMessages[msgIndex] = updatedMsg;
                        return newMessages;
                    });

                    // Now update the context pane display based on the final observation
                    if (observation && observation !== '⏳ Processing...' && (Array.isArray(observation) || (typeof observation === 'object' && observation !== null))) {
                        console.log(`[Page] Displaying formatted Observation for tool: ${toolName}`);
                        setActiveObservationData(observation); // Show formatted observation
                        setActiveObservationTool(toolName);
                        setActiveContextSteps(null); // Hide raw steps when showing observation
                    } else {
                        // If observation is simple/missing, ensure observation display is clear
                        // and potentially show the final raw steps list
                        console.log("[Page] Observation is simple/missing, clearing observation display (steps might show).");
                        setActiveObservationData(null);
                        setActiveObservationTool(null);
                        // Find updated steps array from state (needed because setMessages is async)
                        const finalStepsForDisplay = messages.find(m => m.id === aiMessageId)?.intermediate_steps;
                        setActiveContextSteps(finalStepsForDisplay || [finalStep]); // Show final steps
                    }
                },

                onError: (error) => {
                    const errorMsg = typeof error === 'string' ? error : (error as any)?.message || "Streaming error.";
                    console.error(`[Page] Stream error:`, errorMsg);
                    setAskError(errorMsg);
                    setMessages(prev => prev.map(msg => msg.id === aiMessageId ? { ...msg, text: (msg.text || '') + `\n\n**Error:** ${errorMsg}` } : msg));
                    stopStreaming(); // Clears all context displays
                 },

                onComplete: () => {
                    console.log(`[Page] Stream completed: ${aiMessageId}.`);
                    setIsAsking(false);
                    setCurrentAIMessageId(null);
                    streamAbortController.current = null;
                    // Clear temporary displays on completion
                    setActiveRagContext(null);
                    setActiveObservationData(null);
                    setActiveObservationTool(null);
                    // Decide if final steps should remain visible
                    // setActiveContextSteps(null);
                 },
            }; // End callbacks

            streamAbortController.current = askQuestionStream(payload, callbacks);

        } catch (error: any) { // Catch errors setting up the stream
             console.error("[Page] Error setting up stream:", error);
             setAskError(error.message || "Failed to start connection.");
             setMessages(prev => prev.filter(msg => msg.id !== aiMessageId && msg.id !== userMessageId));
             setInput(query); setIsAsking(false); setCurrentAIMessageId(null);
             // Clear all context displays on setup error
             setActiveContextSteps(null); setActiveRagContext(null); setActiveObservationData(null); setActiveObservationTool(null);
             if (streamAbortController.current) { streamAbortController.current = null; }
         }
    }, [
        // Dependencies
        input, isAsking, selectedFilenames, selectedTag, messages, // Include messages for history
        stopStreaming // Include stopStreaming
        // Removed showContextForMessage and activeContextMessageId
    ]);


    // Helper to Get Scope Text for Display
    const getScopeText = (): string => {
        const filenamesArray = Array.from(selectedFilenames);
        if (filenamesArray.length === 0) return "All Documents";
        if (filenamesArray.length === 1) return `File: ${filenamesArray[0]}`;
        return `${filenamesArray.length} Files Selected`;
    };


    // --- Render the Layout ---
    return (
        <div className="flex flex-col h-screen max-h-screen bg-background text-foreground overflow-hidden">

            {/* Hidden Upload Component */}
            <UploadDropdown
                ref={uploadDropdownRef}
                onUploadComplete={(success) => { if (success) { triggerDocListRefresh(); } }}
            />

            {/* Top Bar */}
            <header className="h-14 flex-shrink-0 border-b flex items-center justify-between px-4">
                <div><span className="font-bold text-lg">N</span></div>
                <div className="flex items-center gap-2"><ModelSelector /><ThemeToggle /></div>
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
                 <section className="flex-grow flex flex-col overflow-hidden border-r">
                    {/* Chat Messages now doesn't need context props */}
                    <ChatMessages
                        messages={messages}
                        isAsking={isAsking}
                        currentAIMessageId={currentAIMessageId}
                        // removed activeContextMessageId
                        // removed onShowContext
                    />
                    <IntegratedInput
                        input={input}
                        handleInputChange={handleInputChange}
                        handleSubmit={handleSubmit}
                        handleKeyDown={handleKeyDown}
                        stopStreaming={stopStreaming}
                        isAsking={isAsking}
                        askError={askError}
                        scopeText={getScopeText()}
                        onToggleSidebar={toggleSidebar}
                    />
                 </section>

                 {/* Right Context Pane - UPDATED Conditional Rendering for Automatic Display */}
                 <aside className="w-80 flex-shrink-0 bg-card overflow-y-auto border-l">
                    {/* Priority: RAG Context > Formatted Observation > Raw Steps > Placeholder */}
                    {activeRagContext ? (
                        <RagContextDisplay contextDocs={activeRagContext} />
                    ) : activeObservationData ? (
                        <ObservationDisplay
                            observation={activeObservationData}
                            toolName={activeObservationTool}
                        />
                    ) : activeContextSteps && activeContextSteps.length > 0 ? (
                        // Fallback to raw steps display if no other context active
                        <StepsDisplay steps={activeContextSteps} />
                    ) : (
                         // Default placeholder when no context/steps/observation active
                         <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground p-6">
                             <Info size={40} className="mb-4 opacity-40" />
                             <p className="text-sm font-medium text-foreground/90">Context Pane</p>
                             {/* Simplified message */}
                             <p className="text-xs mt-2">Detailed context like agent steps,</p>
                             <p className="text-xs mt-1">retrieved documents, or tool results</p>
                             <p className="text-xs mt-1">will appear here automatically.</p>
                         </div>
                    )}
                 </aside>
            </main>
        </div>
    );
}