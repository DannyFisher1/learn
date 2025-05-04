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
    AgentAction
} from '@/lib/api';

// Import Components
import ThemeToggle from '@/components/ui/ThemeToggle';
import ModelSelector from '@/components/common/ModelSelector';
import { UploadDropdownRef } from '@/components/common/UploadDropdown';
import UploadDropdown from '@/components/common/UploadDropdown';
import CollapsibleSidebar from '@/components/layout/CollapsibleSidebar';
import IntegratedInput from '@/components/chat/IntegratedInput';
import ChatMessages from '@/components/chat/ChatMessages';
import StepsDisplay from '@/components/chat/StepsDisplay';
import RagContextDisplay from '@/components/chat/RagContextDisplay';
import ObservationDisplay from '@/components/chat/ObservationDisplay';

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
    const [currentAIMessageId, setCurrentAIMessageId] = useState<string | null>(null);
    const streamAbortController = useRef<AbortController | null>(null);

    // --- Document Scope & Management State ---
    const [selectedFilenames, setSelectedFilenames] = useState<Set<string>>(new Set());
    const [selectedTag, setSelectedTag] = useState<string | null>(null);
    const [refreshDocListTrigger, setRefreshDocListTrigger] = useState(0);
    const uploadDropdownRef = useRef<UploadDropdownRef>(null);

    // --- UI Layout & Context State ---
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    // ** Right Pane State **
    const [activeContextSteps, setActiveContextSteps] = useState<IntermediateStep[] | null>(null);
    const [activeRagContext, setActiveRagContext] = useState<RagContextDocument[] | null>(null);
    const [activeObservationData, setActiveObservationData] = useState<any | null>(null);
    const [activeObservationTool, setActiveObservationTool] = useState<string | null>(null);
    // ** Removed activeContextMessageId as click trigger is removed **

    // --- Document Management Callbacks ---
    const triggerDocListRefresh = useCallback(() => {
        setRefreshDocListTrigger(prev => prev + 1);
        console.log("[Page] Document list refresh triggered.");
    }, []);

    // --- Scope Selection Callbacks ---
    const handleFilenameSelectionToggle = useCallback((filename: string | null) => {
        if (filename === null) { setSelectedFilenames(new Set()); return; }
        setSelectedFilenames(prev => {
            const newSet = new Set(prev);
            if (newSet.has(filename)) { newSet.delete(filename); } else { newSet.add(filename); }
            console.log("[Page] Selected filenames changed:", newSet);
            return newSet;
        });
    }, []);

    // --- UI Callbacks ---
    const toggleSidebar = useCallback(() => { setIsSidebarOpen(prev => !prev); }, []);

    // --- Chat Logic Callbacks ---
    const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement> | string) => {
        setInput(typeof event === 'string' ? event : event.target.value);
    };

    const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); handleSubmit(); }
    };

    // --- Updated stopStreaming ---
    const stopStreaming = useCallback(() => {
        if (streamAbortController.current) {
            streamAbortController.current.abort(); streamAbortController.current = null;
            console.log("[Page] Stream aborted.");
        } else { console.log("[Page] No active stream to abort."); }
        setIsAsking(false);
        setCurrentAIMessageId(null);
        // Clear all context displays on stop
        setActiveRagContext(null);
        setActiveObservationData(null);
        setActiveObservationTool(null);
        setActiveContextSteps(null);
    }, []); // No dependencies needed that change

    // --- UPDATED handleSubmit ---
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
        // Clear all right-pane displays for new request
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

            // --- Define Stream Callbacks with Refined Context Logic ---
            const callbacks: StreamCallbacks = {
                onOpen: () => console.log(`[Page] Stream opened: ${aiMessageId}`),

                onToken: (token) => {
                    // **MODIFIED:** Only clear RAG context. Keep Observation/Steps visible.
                    setActiveRagContext(null);
                    // setActiveObservationData(null); setActiveObservationTool(null); // DO NOT CLEAR OBSERVATION HERE
                    // setActiveContextSteps(null); // DO NOT CLEAR STEPS HERE
                    setMessages(prev => prev.map(msg => msg.id === aiMessageId ? { ...msg, text: msg.text + token } : msg));
                },

                onRagContext: (contextDocs) => {
                    console.log(`[Page] RAG Context (${contextDocs.length} docs)`);
                    // Show RAG context, clear others
                    setActiveContextSteps(null);
                    setActiveObservationData(null);
                    setActiveObservationTool(null);
                    setActiveRagContext(contextDocs); // Display RAG context
                },

                onStep: (step) => {
                    console.log("[Page] onStep (Partial):", step.action);
                    // --- MODIFICATION: Only clear observation if it's not already showing --- //
                    // Show raw steps, clear RAG.
                    setActiveRagContext(null);
                    // **Only clear observation pane if it wasn't just intentionally set**
                    // We can check if activeObservationData is currently null before clearing it.
                    // A slightly safer check might involve a dedicated flag, but this should work.
                    if (activeObservationData === null) { // Check if observation pane is currently empty
                         setActiveObservationData(null); // Ensure it's clear
                         setActiveObservationTool(null);
                    }
                    // ---------------------------------------------------------------------- //

                    const stepToAdd = isAgentAction(step.action) ? { ...step, observation: '⏳ Processing...' } : step;
                    setMessages(prev => { // Update message state
                        const msgIndex = prev.findIndex(m => m.id === aiMessageId);
                        if (msgIndex === -1) return prev;
                        const targetMsg = prev[msgIndex];
                        const updatedSteps = [...(targetMsg.intermediate_steps || []), stepToAdd];
                        setActiveContextSteps(updatedSteps); // Update right pane with steps
                        const updatedMsg = { ...targetMsg, intermediate_steps: updatedSteps };
                        const newMessages = [...prev]; newMessages[msgIndex] = updatedMsg;
                        return newMessages;
                    });
                },

                onStepFinal: (finalStep) => {
                    // Fix 1: Log the entire step object
                    console.log("[Page] onStepFinal received step:", finalStep);
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

                    // --- Add Detailed Logging Before Decision ---
                    console.log(`[Page] onStepFinal - Checking observation for Pane Display:`, {
                        observationValue: observation,
                        isArray: Array.isArray(observation),
                        typeofValue: typeof observation,
                        isProcessing: observation === '⏳ Processing...',
                        conditionResult: (observation && observation !== '⏳ Processing...' && (Array.isArray(observation) || (typeof observation === 'object' && observation !== null)))
                    });
                    // -------------------------------------------

                    // Update Context Pane based on final observation
                    if (observation && observation !== '⏳ Processing...' && (Array.isArray(observation) || (typeof observation === 'object' && observation !== null))) {
                         console.log(`[Page] Displaying Formatted Observation for tool: ${toolName}`);
                         setActiveObservationData(observation); // Show formatted observation
                         setActiveObservationTool(toolName);
                         setActiveContextSteps(null); // Hide raw steps when showing observation
                    } else {
                         console.log("[Page] Observation is simple/missing, showing steps display.");
                         setActiveObservationData(null); // Ensure observation is clear
                         setActiveObservationTool(null);
                         // Fix 2: Use newStepsArray directly for setActiveContextSteps
                         // Need to find the final steps array from the *just updated* state.
                         // Reading state again is tricky, let's use the calculated array if possible.
                         // Note: newStepsArray was calculated within the setMessages update above.
                         // We need access to it here. Let's recalculate it briefly or pass it.
                         // For simplicity here, let's rely on the fact that setMessages above updated the steps.
                         // We might need a useEffect if this proves unreliable.

                         // Find the updated message again (safer approach)
                         setMessages(prev => {
                             const updatedMessage = prev.find(m => m.id === aiMessageId);
                             const finalStepsForDisplay = updatedMessage?.intermediate_steps;
                             setActiveContextSteps(finalStepsForDisplay || null); // Show final steps (or null if none)
                             return prev; // No actual message change here, just reading
                         });
                    }
                }, // End onStepFinal

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
                    // Fix 3: DO NOT clear observation/steps on normal completion
                    setActiveRagContext(null); // Still clear RAG context
                    // setActiveObservationData(null); // Keep observation visible
                    // setActiveObservationTool(null); // Keep observation tool name
                    // setActiveContextSteps(null); // Keep steps visible (if they were the last thing shown)
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
        input, isAsking, selectedFilenames, selectedTag, messages, stopStreaming
        // Removed showContextForMessage, activeContextMessageId
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
            <UploadDropdown ref={uploadDropdownRef} onUploadComplete={(success) => { if (success) { triggerDocListRefresh(); } }}/>

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
                    {/* Chat Messages - Removed context props */}
                    <ChatMessages
                        messages={messages}
                        isAsking={isAsking}
                        currentAIMessageId={currentAIMessageId}
                        // No context props needed here anymore
                    />
                    {/* Integrated Input */}
                    <IntegratedInput
                        input={input} handleInputChange={handleInputChange}
                        handleSubmit={handleSubmit} handleKeyDown={handleKeyDown}
                        stopStreaming={stopStreaming} isAsking={isAsking}
                        askError={askError} scopeText={getScopeText()}
                        onToggleSidebar={toggleSidebar}
                    />
                 </section>

                 {/* Right Context Pane - Conditional Rendering */}
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
                        <StepsDisplay steps={activeContextSteps} />
                    ) : (
                         // Default placeholder
                         <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground p-6">
                             <Info size={40} className="mb-4 opacity-40" />
                             <p className="text-sm font-medium text-foreground/90">Context Pane</p>
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