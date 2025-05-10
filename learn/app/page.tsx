// learn/app/page.tsx
'use client';

import React, { useState, useCallback, useRef, useEffect, ChangeEvent, KeyboardEvent, FormEvent } from 'react';
import debounce from 'lodash.debounce';
import {
    Message as ApiMessage, AskPayload, StreamEventCallbacks, UiStreamEvent, Source, RagContextDocument,
    StartDeepResearchPayload,
    askQuestionStream,
    getJobResult, // We need getJobResult directly for handleViewJobResults
    JOB_STATUS_COMPLETED, // Status constants are useful here too
    JOB_STATUS_FAILED
} from '@/lib/api';

// Import the custom hook
import { useJobTracking } from '@/hooks/useJobTracking';

// UI Components
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import ThemeToggle from '@/components/ui/ThemeToggle';
import ModelSelector from '@/components/common/ModelSelector';
import { UploadDropdownRef } from '@/components/common/UploadDropdown';
import UploadDropdown from '@/components/common/UploadDropdown';
import DocumentManager from '@/components/layout/DocumentManager';
import IntegratedInput from '@/components/chat/IntegratedInput'; 
import ChatMessages from '@/components/chat/ChatMessages';
import Sidebar from '@/components/layout/Sidebar';
import WorkspacePane from '@/components/layout/WorkspacePane';
import { toast } from 'sonner';
import { Filter, ChevronDown, RefreshCw, Loader2 } from 'lucide-react';

export default function Home() {
    // --- Chat State ---
    const [messages, setMessages] = useState<ApiMessage[]>([]);
    const [input, setInput] = useState('');
    const [isAsking, setIsAsking] = useState(false);
    const [askError, setAskError] = useState<string | null>(null);
    const streamAbortController = useRef<AbortController | null>(null);
    const aiMessageAccumulators = useRef<Record<string, string>>({});

    // --- Document/Scope State ---
    const [selectedFilenames, setSelectedFilenames] = useState<Set<string>>(new Set());
    const [refreshDocListTrigger, setRefreshDocListTrigger] = useState(0);
    const uploadDropdownRef = useRef<UploadDropdownRef>(null);

    // --- Workspace State ---
    const [workspaceContent, setWorkspaceContent] = useState<{ type: string; data: any; title?: string } | null>(null);
    const [isWorkspaceLoading, setIsWorkspaceLoading] = useState<boolean>(false);

    const handleViewJobResults = useCallback(async (jobId: string) => {
        setIsWorkspaceLoading(true);
        setWorkspaceContent(null);
        toast.info("Loading job results...");
        try {
            const result = await getJobResult(jobId); // getJobResult is directly from lib/api
            if (!result) throw new Error("Job not found or result is null.");

            const workspaceTitle = `${result.task_type.replace(/_/g, ' ')} Result (${jobId.substring(0, 8)})`;
            let newWorkspaceContent: { type: string; data: any; title?: string } | null = null;

            if (result.status === JOB_STATUS_COMPLETED && result.result_data) {
                if (result.task_type === 'deep_research' && typeof result.result_data === 'object' && result.result_data?.report_markdown) {
                    newWorkspaceContent = { type: 'markdown_report', data: result.result_data, title: workspaceTitle };
                } else if (result.task_type === 'project_generation' && typeof result.result_data === 'object' && result.result_data?.output_dir) {
                    newWorkspaceContent = { type: 'project_result', data: result.result_data, title: workspaceTitle };
                } else {
                    newWorkspaceContent = { type: 'json_data', data: result.result_data, title: workspaceTitle };
                }
                toast.success("Results loaded.");
            } else if (result.status === JOB_STATUS_FAILED) {
                newWorkspaceContent = { type: 'error', data: { title: `Job ${jobId.substring(0,8)}... Failed`, message: result.error_message || "No details." } };
                toast.error(`Job ${jobId.substring(0,8)}... failed.`);
            } else { 
                newWorkspaceContent = { type: 'info', data: { title: `Job ${jobId.substring(0,8)}... Status`, message: `Status: ${result.status}. ${result.progress_message || ''}` } };
                toast.info(`Job status: ${result.status}`);
            }
            setWorkspaceContent(newWorkspaceContent);
        } catch (error: any) {
            console.error(`[ViewResults] Failed for job ${jobId}:`, error);
            setWorkspaceContent({ type: 'error', data: { title: `Error Loading Job ${jobId.substring(0,8)}...`, message: error.message || 'Failed.' } });
            toast.error(`Failed to load results: ${error.message || 'Unknown error'}`);
        } finally {
            setIsWorkspaceLoading(false);
        }
    }, []);

    const {
        trackedJobs,
        jobHistory,
        isHistoryViewActive,
        historyPagination,
        isLoadingJobsList,
        cancelJobHandler,
        dismissJobHandler,
        startJobHandler,
        toggleHistoryViewHandler,
        loadMoreHistoryHandler,
        refreshListHandler,
        hardDeleteJobHandler, // <-- Destructure the new handler
    } = useJobTracking({ onJobRequiresView: handleViewJobResults });


    const debouncedUpdateDisplay = useRef(
        debounce((aiMsgId: string, rawText: string) => {
            setMessages(prev => prev.map(msg => (msg.id === aiMsgId && msg.text !== rawText) ? { ...msg, text: rawText } : msg));
        }, 150)
    ).current;

    const triggerDocListRefresh = useCallback(() => { setRefreshDocListTrigger(prev => prev + 1); }, []);
    
    const handleFilenameSelectionToggle = useCallback((filename: string | null) => {
        if (filename === null) { setSelectedFilenames(new Set()); return; }
        setSelectedFilenames(prev => { const newSet = new Set(prev); if (newSet.has(filename)) newSet.delete(filename); else newSet.add(filename); return newSet; });
    }, []);
    
    const handleInputChange = useCallback((event: ChangeEvent<HTMLTextAreaElement> | string) => {
        setInput(typeof event === 'string' ? event : event.target.value);
    }, []);

    const stopStreaming = useCallback(() => {
        if (streamAbortController.current) {
            streamAbortController.current.abort();
            streamAbortController.current = null;
        }
        setIsAsking(false);
        debouncedUpdateDisplay.flush();
    }, [debouncedUpdateDisplay]);
    
    const handleSubmit = useCallback(async (event?: FormEvent<HTMLFormElement> | React.MouseEvent<HTMLButtonElement> | string) => {
        if (typeof event !== 'string' && event?.preventDefault) event.preventDefault();
        let query = '';
        if(typeof event === 'string') query = event;
        else query = input;

        if (isAsking) { stopStreaming(); return; }
        if (!query.trim()) return;

        if (query.startsWith('/research ')) {
             const topic = query.substring('/research '.length).trim();
             if (topic) {
                  setInput('');
                  const researchPayload: StartDeepResearchPayload = { topic: topic, depth: 2 };
                  await startJobHandler('deep_research', researchPayload);
             } else { toast.warning("Please provide a topic for /research"); }
             return;
        }

        const userMessageId = `user-${Date.now()}`; const aiMessageId = `ai-${Date.now()}`;
        setInput(''); setIsAsking(true); setAskError(null);
        aiMessageAccumulators.current[aiMessageId] = '';
        const newUserMessage: ApiMessage = { id: userMessageId, sender: 'user', text: query };
        const newAiMessagePlaceholder: ApiMessage = { id: aiMessageId, sender: 'ai', text: '', statusSteps: [], webSources: [], ragSources: [], retrievedContext: [], error: null, };
        setMessages(prev => [...prev, newUserMessage, newAiMessagePlaceholder]);

        const callbacks: StreamEventCallbacks = {
            onOpen: () => console.log(`[Page] Stream opened: ${aiMessageId}`),
            onEvent: (uiEvent: UiStreamEvent) => {
                setMessages(prevMsgs => {
                    const messageIndex = prevMsgs.findIndex(m => m.id === aiMessageId);
                    if (messageIndex === -1) return prevMsgs;
                    const currentMsg = prevMsgs[messageIndex];
                    let updatedMsgData: Partial<ApiMessage> = {};
                    switch (uiEvent.type) {
                        case 'thinking_started': updatedMsgData = { statusSteps: [(uiEvent.data as { message: string }).message || "Thinking..."], webSources: [], retrievedContext: [], error: null }; break;
                        case 'tool_call_initiated': case 'status_update': const statusMsg = (uiEvent.data as { message: string }).message; if (statusMsg && !(currentMsg.statusSteps || []).includes(statusMsg)) { updatedMsgData = { statusSteps: [...(currentMsg.statusSteps || []), statusMsg] }; } break;
                        case 'sources_found': const newWebSources = (uiEvent.data as { sources: Source[] }).sources || []; const sourcesFoundMsg = `Found ${newWebSources.length} web source(s)`; updatedMsgData = { webSources: newWebSources, statusSteps: [...(currentMsg.statusSteps || []).filter(s => !s.toLowerCase().includes("found") && !s.toLowerCase().includes("source")), sourcesFoundMsg] }; break;
                        case 'rag_context_found': const newRagContext = (uiEvent.data as { context: RagContextDocument[] }).context || []; const contextFoundMsg = `Retrieved ${newRagContext.length} document chunk(s)`; updatedMsgData = { retrievedContext: newRagContext, statusSteps: [...(currentMsg.statusSteps || []).filter(s => !s.toLowerCase().includes("retrieved") && !s.toLowerCase().includes("chunk")), contextFoundMsg] }; break;
                        case 'ai_message_chunk': const newChunk = (uiEvent.data as { content_chunk: string }).content_chunk; if (newChunk) { aiMessageAccumulators.current[aiMessageId] = (aiMessageAccumulators.current[aiMessageId] || '') + newChunk; debouncedUpdateDisplay(aiMessageId, aiMessageAccumulators.current[aiMessageId]); } return prevMsgs; 
                        case 'error_message': const errorData = uiEvent.data as { error: string, details?: string }; const newError = errorData.error + (errorData.details ? ` (${errorData.details})` : ''); updatedMsgData = { error: newError, statusSteps: [...(currentMsg.statusSteps || []), `Error: ${errorData.error}`] }; break;
                    }
                    if (Object.keys(updatedMsgData).length > 0) { const newMessages = [...prevMsgs]; newMessages[messageIndex] = { ...currentMsg, ...updatedMsgData }; return newMessages; }
                    return prevMsgs;
                });
            },
            onError: (error) => { const errorMsg = typeof error === 'string' ? error : (error as any)?.message || "Unknown stream error"; console.error(`[Page] Stream Error for ${aiMessageId}:`, error); debouncedUpdateDisplay.flush(); setAskError(errorMsg); setMessages(prevMsgs => prevMsgs.map(msg => msg.id === aiMessageId ? { ...msg, error: errorMsg, statusSteps: [...(msg.statusSteps || []), `Connection Error: ${errorMsg}`] } : msg )); stopStreaming(); delete aiMessageAccumulators.current[aiMessageId]; },
            onComplete: () => { console.log(`[Page] Stream completed: ${aiMessageId}.`); debouncedUpdateDisplay.flush(); setIsAsking(false); delete aiMessageAccumulators.current[aiMessageId]; },
        };
        try {
            const filenamesArray = Array.from(selectedFilenames);
            const historyToSend = messages.filter(m => m.sender === 'user' || (m.sender === 'ai' && m.text)).map(m => ({ sender: m.sender, text: m.text }));
            const payload: AskPayload = { question: query, filenames: filenamesArray.length > 0 ? filenamesArray : undefined, chat_history: historyToSend.length > 0 ? historyToSend : undefined };
            streamAbortController.current = askQuestionStream(payload, callbacks);
        } catch (error: any) { console.error("[Page] Error setting up stream:", error); setAskError(error.message || "Failed to set up stream."); setMessages(prev => prev.filter(msg => msg.id !== aiMessageId && msg.id !== userMessageId)); setInput(query); setIsAsking(false); delete aiMessageAccumulators.current[aiMessageId]; }
    }, [input, isAsking, selectedFilenames, messages, stopStreaming, debouncedUpdateDisplay, startJobHandler]);
    
    const handleKeyDown = useCallback((event: KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            handleSubmit(); 
        }
    }, [handleSubmit]);

    useEffect(() => {
        return () => { debouncedUpdateDisplay.cancel(); };
    }, [debouncedUpdateDisplay]);

    const getScopeText = (): string => {
        const arr = Array.from(selectedFilenames);
        if (arr.length === 0) return "All Documents";
        if (arr.length === 1) return arr[0].length > 20 ? arr[0].substring(0, 18) + '...' : arr[0];
        return `${arr.length} files`;
    };

    return (
        <TooltipProvider delayDuration={200}>
            <div className="flex flex-col h-screen max-h-screen bg-background text-foreground overflow-hidden dark:bg-gray-950">
                <UploadDropdown ref={uploadDropdownRef} onUploadComplete={(success) => { if (success) { triggerDocListRefresh(); } }}/>
                <header className="h-14 flex-shrink-0 border-b dark:border-gray-800 flex items-center justify-between px-4 bg-card/30 dark:bg-gray-900/50">
                    <div className="flex items-center gap-2">
                        <span className="font-bold text-lg">LearnMate</span>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon"
                                    onClick={refreshListHandler}
                                    disabled={isLoadingJobsList}
                                    className="h-7 w-7 text-muted-foreground hover:text-primary">
                                    {isLoadingJobsList ? <Loader2 className="h-4 w-4 animate-spin"/> : <RefreshCw className="h-4 w-4"/>}
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent side="bottom">
                                {isHistoryViewActive ? "Refresh History" : "Refresh Active Tasks"}
                            </TooltipContent>
                        </Tooltip>
                    </div>
                    <div className="flex items-center gap-2">
                         <Popover>
                             <PopoverTrigger asChild>
                                 <Button variant="outline" size="sm" className="h-8 text-xs dark:border-gray-600">
                                     <Filter className="mr-2 h-3 w-3" /> Scope: {getScopeText()} <ChevronDown className="ml-2 h-3 w-3" />
                                 </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-auto p-0" align="end">
                                 <DocumentManager selectedFilenames={selectedFilenames} onFilenameToggle={handleFilenameSelectionToggle} triggerRefresh={refreshDocListTrigger} onDocumentsManaged={triggerDocListRefresh} uploadDropdownRef={uploadDropdownRef} />
                             </PopoverContent>
                         </Popover>
                         <ModelSelector />
                         <ThemeToggle />
                     </div>
                </header>
                <main className="flex-grow flex flex-row overflow-hidden">
                    <PanelGroup direction="horizontal" className="flex flex-1 border-b dark:border-gray-800">
                        <Panel defaultSize={20} minSize={15} maxSize={40} id="sidebar-panel" order={1} className="!overflow-y-auto bg-card/50 dark:bg-gray-900/60 border-r dark:border-gray-800">
                            <Sidebar
                                jobsToDisplay={isHistoryViewActive ? jobHistory : trackedJobs}
                                isHistoryView={isHistoryViewActive}
                                historyPagination={historyPagination}
                                isLoadingJobs={isLoadingJobsList}
                                onCancelJob={cancelJobHandler}
                                onViewResults={handleViewJobResults}
                                onDismissJob={dismissJobHandler}
                                onToggleHistoryView={toggleHistoryViewHandler}
                                onLoadMoreHistory={loadMoreHistoryHandler}
                                onHardDeleteJob={hardDeleteJobHandler} // <-- Pass the new handler
                            />
                        </Panel>
                        <PanelResizeHandle className="w-1.5 bg-border/50 hover:bg-border transition-colors data-[resize-handle-state=drag]:bg-primary" />
                        <Panel defaultSize={45} minSize={30} id="conversation-panel" order={2} className="flex-grow flex flex-col overflow-hidden h-full">
                            <ChatMessages messages={messages} isAsking={isAsking} />
                        </Panel>
                        <PanelResizeHandle className="w-1.5 bg-border/50 hover:bg-border transition-colors data-[resize-handle-state=drag]:bg-primary" />
                        <Panel defaultSize={35} minSize={20} id="workspace-panel" order={3} className="flex-grow flex flex-col overflow-y-auto h-full bg-muted/10 dark:bg-gray-900/30">
                            <WorkspacePane content={workspaceContent} isLoading={isWorkspaceLoading} />
                        </Panel>
                    </PanelGroup>
                </main>
                 <div className="flex-shrink-0 border-t dark:border-gray-800 px-4 py-2 md:py-3 bg-card/30 dark:bg-gray-900/50">
                    <IntegratedInput
                        input={input}
                        handleInputChange={handleInputChange}
                        handleSubmit={handleSubmit}
                        handleKeyDown={handleKeyDown}
                        stopStreaming={stopStreaming}
                        isAsking={isAsking}
                        askError={askError}
                        onStartWorkflow={startJobHandler}
                    />
                 </div>
            </div>
        </TooltipProvider>
    );
}