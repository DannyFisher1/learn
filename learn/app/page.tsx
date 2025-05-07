// app/page.tsx
'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
    Message as ApiMessage,
    AskPayload,
    StreamLogCallbacks, // *** USE THE CORRECT IMPORT ***
    StreamLogData,      // *** USE THE CORRECT IMPORT ***
    askQuestionStream,
    // DocumentInfo,
    RagContextDocument,
    AgentAction
} from '@/lib/api'; // Ensure api.ts has StreamLogCallbacks/StreamLogData

// Import Components
import ThemeToggle from '@/components/ui/ThemeToggle';
import ModelSelector from '@/components/common/ModelSelector';
import { UploadDropdownRef } from '@/components/common/UploadDropdown';
import UploadDropdown from '@/components/common/UploadDropdown';
import DocumentManager from '@/components/layout/DocumentManager';
import IntegratedInput from '@/components/chat/IntegratedInput';
import ChatMessages from '@/components/chat/ChatMessages';
import { Button } from "@/components/ui/button";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover";

// Import Icons
import { Filter, ChevronDown } from 'lucide-react';

// Constants
const ALL_DOCUMENTS_VALUE = 'all';

// --- Helper Type Guard ---
function isAgentAction(action: any): action is AgentAction {
    return typeof action === 'object' && action !== null && 'tool' in action;
}

// --- Main Page Component (Using StreamLogCallbacks) ---
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
    // const [selectedTag, setSelectedTag] = useState<string | null>(null);
    const [refreshDocListTrigger, setRefreshDocListTrigger] = useState(0);
    const uploadDropdownRef = useRef<UploadDropdownRef>(null);

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

    // --- Chat Logic Callbacks ---
    const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement> | string) => {
        setInput(typeof event === 'string' ? event : event.target.value);
    };

    const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); handleSubmit(); }
    };

    // --- Stop Streaming ---
    const stopStreaming = useCallback(() => {
        if (streamAbortController.current) {
            streamAbortController.current.abort(); streamAbortController.current = null;
            console.log("[Page] Stream aborted.");
        } else { console.log("[Page] No active stream to abort."); }
        setIsAsking(false);
        setCurrentAIMessageId(null);
    }, []);

    // --- handleSubmit (Using StreamLogCallbacks) ---
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

        const newUserMessage: ApiMessage = { id: userMessageId, sender: 'user', text: query };
        const newAiMessagePlaceholder: ApiMessage = { id: aiMessageId, sender: 'ai', text: '', intermediate_steps: [] };
        setMessages(prev => [...prev, newUserMessage, newAiMessagePlaceholder]);

        try {
            const filenamesArray = Array.from(selectedFilenames);
            const historyToSend = messages
                .filter(m => m.id !== aiMessageId)
                .map(m => ({ sender: m.sender, text: m.text }));

            const payload: AskPayload = {
                question: query,
                filenames: filenamesArray.length > 0 ? filenamesArray : undefined,
                // tag_filter: selectedTag === ALL_DOCUMENTS_VALUE ? undefined : selectedTag,
                chat_history: historyToSend.length > 0 ? historyToSend : undefined
            };
            console.log("[Page] Sending payload:", payload);

            // --- Define Updated Stream Callbacks ---
            const callbacks: StreamLogCallbacks = { // *** USE CORRECT TYPE ***
                onOpen: () => console.log(`[Page] Stream opened: ${aiMessageId}`),

                // Single callback to handle all structured log data
                onLogData: (logData: StreamLogData) => {
                    switch (logData.type) {
                        case 'token':
                            if (logData.token) {
                                // Use the anti-duplication logic here
                                setMessages(prev => {
                                    const msgIndex = prev.findIndex(msg => msg.id === aiMessageId);
                                    if (msgIndex === -1) return prev;
                                    const newMessages = [...prev];
                                    const currentText = newMessages[msgIndex].text || '';
                                    const token = logData.token!; // Assert non-null based on outer check

                                    if (currentText.endsWith(token)) return prev; // Exact suffix

                                    for (let k = Math.min(token.length, currentText.length); k > 0; k--) {
                                        if (currentText.endsWith(token.substring(0, k))) {
                                            const nonOverlappingPart = token.substring(k);
                                            newMessages[msgIndex] = { ...newMessages[msgIndex], text: currentText + nonOverlappingPart };
                                            return newMessages;
                                        }
                                    }
                                    newMessages[msgIndex] = { ...newMessages[msgIndex], text: currentText + token };
                                    return newMessages;
                                });
                            }
                            break;

                        case 'tool_call':
                             if (logData.toolCall) {
                                console.log("[Page] Tool Call Started (Not Displayed):", logData.toolCall);
                                // Update internal message state with partial step
                                const action = { tool: logData.toolCall.name, tool_input: logData.toolCall.args, log: `Starting ${logData.toolCall.name}` };
                                const stepToAdd = { action: action, observation: '⏳ Processing...' };
                                setMessages(prev => {
                                    const msgIndex = prev.findIndex(m => m.id === aiMessageId);
                                    if (msgIndex === -1) return prev;
                                    const targetMsg = prev[msgIndex];
                                    const existingSteps = targetMsg.intermediate_steps || [];
                                    const alreadyExists = existingSteps.some(s => s.observation === '⏳ Processing...' && JSON.stringify(s.action) === JSON.stringify(action)); // Prevent duplicate partials
                                    const updatedSteps = alreadyExists ? existingSteps : [...existingSteps, stepToAdd];
                                    const updatedMsg = { ...targetMsg, intermediate_steps: updatedSteps };
                                    const newMessages = [...prev]; newMessages[msgIndex] = updatedMsg;
                                    return newMessages;
                                });
                             }
                             break;

                         case 'tool_result':
                             if (logData.toolResult) {
                                console.log("[Page] Tool Result Received (Not Displayed):", logData.toolResult);
                                // Update internal message state (replace partial step)
                                setMessages(prev => {
                                    const msgIndex = prev.findIndex(m => m.id === aiMessageId);
                                    if (msgIndex === -1) return prev;
                                    const targetMsg = prev[msgIndex];
                                    const existingSteps = targetMsg.intermediate_steps || [];
                                    let foundPartial = false;
                                    const newStepsArray = existingSteps.map(s => {
                                        // Find matching partial step based on action details *before* it was completed
                                        // This relies on finding the pending step added by 'tool_call' event
                                        // Note: This matching logic might need refinement if tool IDs aren't reliable across events
                                        if (s.observation === "⏳ Processing..." && isAgentAction(s.action)) {
                                             // Attempt to match based on tool name and potentially input if available
                                             // A more robust way would be to associate the tool_call_id from the start event
                                             // For now, just replace the *first* pending step found (less robust)
                                             // Or better: If backend guarantees ToolMessage has ID, we could store pending actions by ID
                                             // Since we don't have the original call ID easily here, we find *a* pending step
                                            // A better approach stores pending steps keyed by ID if possible
                                            if (!foundPartial) { // Replace only the first pending step found
                                                 foundPartial = true;
                                                 const finalAction = { ...(s.action as AgentAction), log: `Completed ${s.action.tool}` };
                                                 return { action: finalAction, observation: logData.toolResult!.result };
                                            }
                                        }
                                        return s;
                                    });
                                    // If no partial step was found to replace (e.g., stream started mid-tool), append it
                                    if (!foundPartial){
                                        console.warn("[Page] Tool result received, but couldn't find matching pending step to replace.");
                                        // We need action details here - difficult without ID matching
                                        // For now, don't add if we can't match
                                        // const actionPlaceholder = { tool: 'UnknownTool', tool_input: 'Unknown', log:'Completed UnknownTool'};
                                        // newStepsArray.push({ action: actionPlaceholder, observation: logData.toolResult.result });
                                    }

                                    const updatedMsg = { ...targetMsg, intermediate_steps: newStepsArray };
                                    const newMessages = [...prev]; newMessages[msgIndex] = updatedMsg;
                                    return newMessages;
                                });
                             }
                             break;

                        case 'error':
                            const errorMsg = typeof logData.error === 'string' ? logData.error : (logData.error as any)?.message || "Streaming error.";
                            console.error(`[Page] Stream error received via onLogData:`, errorMsg);
                            setAskError(errorMsg);
                            setMessages(prev => prev.map(msg => msg.id === aiMessageId ? { ...msg, text: (msg.text || '') + `\n\n**Error:** ${errorMsg}` } : msg));
                            stopStreaming();
                            break;

                        // Ignore node_start, node_end, state_update, final_message in this simplified UI
                        case 'node_start':
                        case 'node_end':
                        case 'state_update':
                        case 'final_message':
                            // console.debug(`[Page] Ignoring log type: ${logData.type}`);
                            break;
                    }
                },

                onError: (error) => { // Fallback for connection errors etc.
                    const errorMsg = typeof error === 'string' ? error : (error as any)?.message || "Streaming connection error.";
                    console.error(`[Page] Stream Connection ERROR:`, errorMsg);
                    // Avoid duplicate error display if already handled by onLogData({type:'error'})
                    if (!askError) {
                         setAskError(errorMsg);
                         setMessages(prev => prev.map(msg => msg.id === aiMessageId ? { ...msg, text: (msg.text || '') + `\n\n**Error:** ${errorMsg}` } : msg));
                    }
                    stopStreaming();
                 },

                onComplete: () => {
                    console.log(`[Page] Stream completed: ${aiMessageId}.`);
                    setIsAsking(false);
                    setCurrentAIMessageId(null);
                    streamAbortController.current = null;
                 },
            };
            // -------------------------------------------

            streamAbortController.current = askQuestionStream(payload, callbacks);

        } catch (error: any) {
             console.error("[Page] Error setting up stream:", error);
             setAskError(error.message || "Failed to start connection.");
             setMessages(prev => prev.filter(msg => msg.id !== aiMessageId && msg.id !== userMessageId));
             setInput(query); setIsAsking(false); setCurrentAIMessageId(null);
             if (streamAbortController.current) { streamAbortController.current = null; }
         }
    }, [ input, isAsking, selectedFilenames, /*selectedTag,*/ messages, stopStreaming ]);


    // Helper to Get Scope Text for Display
    const getScopeText = (): string => {
        const filenamesArray = Array.from(selectedFilenames);
        if (filenamesArray.length === 0) return "All Documents";
        if (filenamesArray.length === 1) {
             const name = filenamesArray[0];
             return name.length > 20 ? name.substring(0, 18) + '...' : name;
        }
        return `${filenamesArray.length} files`;
    };


    // --- Render the Simplified Layout ---
    return (
        <div className="flex flex-col h-screen max-h-screen bg-background text-foreground overflow-hidden dark:bg-gray-900">

            {/* Hidden Upload Component */}
            <UploadDropdown ref={uploadDropdownRef} onUploadComplete={(success) => { if (success) { triggerDocListRefresh(); } }}/>

            {/* Top Bar */}
            <header className="h-14 flex-shrink-0 border-b dark:border-gray-700 flex items-center justify-between px-4">
                <div><span className="font-bold text-lg">LearnMate</span></div>
                <div className="flex items-center gap-2">
                    <Popover>
                        <PopoverTrigger asChild>
                            <Button variant="outline" size="sm" className="h-8 text-xs dark:border-gray-600">
                                <Filter className="mr-2 h-3 w-3" /> Scope: {getScopeText()} <ChevronDown className="ml-2 h-3 w-3" />
                            </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0" align="end">
                            <DocumentManager
                                selectedFilenames={selectedFilenames}
                                onFilenameToggle={handleFilenameSelectionToggle}
                                triggerRefresh={refreshDocListTrigger}
                                onDocumentsManaged={triggerDocListRefresh}
                                uploadDropdownRef={uploadDropdownRef}
                            />
                        </PopoverContent>
                    </Popover>
                    <ModelSelector />
                    <ThemeToggle />
                </div>
            </header>

            {/* Main Content Area - Single Chat Pane */}
            <main className="flex-grow flex flex-col overflow-hidden">
                 <section className="flex-grow flex flex-col overflow-hidden h-full">
                    <ChatMessages
                        messages={messages}
                        isAsking={isAsking}
                        currentAIMessageId={currentAIMessageId}
                    />
                    <IntegratedInput
                        input={input} handleInputChange={handleInputChange}
                        handleSubmit={handleSubmit} handleKeyDown={handleKeyDown}
                        stopStreaming={stopStreaming} isAsking={isAsking}
                        askError={askError}
                    />
                 </section>
            </main>
        </div>
    );
}