// learn/components/chat/IntegratedInput.tsx
'use client';

import React, { useRef, useEffect, useState } from 'react';
import TextareaAutosize from 'react-textarea-autosize';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ArrowUp, Square, AlertCircle, PlusCircle } from 'lucide-react'; // Removed Loader2 as it's not used here
import { cn } from '@/lib/utils';
import WorkflowLauncher from '@/components/workflows/WorkflowLauncher';

// Define the props interface clearly
export interface IntegratedInputProps {
    input: string;
    handleInputChange: (event: React.ChangeEvent<HTMLTextAreaElement> | string) => void;
    handleSubmit: (event?: React.FormEvent<HTMLFormElement> | React.MouseEvent<HTMLButtonElement> | string) => void; // Adjusted for button click
    handleKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
    stopStreaming: () => void;
    isAsking: boolean;
    askError: string | null;
    onStartWorkflow: (taskType: string, params: any) => Promise<void>; // Function to initiate workflow from page.tsx
}

const IntegratedInput: React.FC<IntegratedInputProps> = ({
    input,
    handleInputChange,
    handleSubmit,
    handleKeyDown,
    stopStreaming,
    isAsking,
    askError,
    onStartWorkflow,
}) => {
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const [isComposing, setIsComposing] = useState(false);

    // Effect for focusing (optional, can be enabled if needed)
    // useEffect(() => {
    //     textareaRef.current?.focus();
    // }, []);

    return (
        <TooltipProvider> {/* Encapsulate with TooltipProvider if tooltips are direct children */}
            <div className="relative flex items-end gap-2">
                <WorkflowLauncher onStartJob={onStartWorkflow}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button type="button" variant="ghost" size="icon" className="flex-shrink-0 text-muted-foreground hover:text-primary">
                                <PlusCircle className="h-5 w-5" />
                                <span className="sr-only">Start Workflow</span>
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="top">Start New Task</TooltipContent>
                    </Tooltip>
                </WorkflowLauncher>

                <TextareaAutosize
                    ref={textareaRef}
                    value={input}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask anything... or use /command (e.g. /research topic)"
                    className={cn(
                        "flex-grow resize-none py-2 pr-10 pl-3 text-[15px] bg-transparent border border-input rounded-full shadow-sm",
                        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                        "disabled:cursor-not-allowed disabled:opacity-50",
                        "scrollbar-thin scrollbar-thumb-muted"
                    )}
                    minRows={1}
                    maxRows={5}
                    disabled={isAsking}
                    onCompositionStart={() => setIsComposing(true)}
                    onCompositionEnd={() => setIsComposing(false)}
                />
                <div className="absolute right-2 bottom-[5px] flex items-center">
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                type="button" // Changed from "submit" if not part of a <form> directly, or ensure handleSubmit can take MouseEvent
                                size="icon"
                                variant="ghost"
                                className="h-7 w-7 rounded-full text-muted-foreground hover:bg-primary/10 hover:text-primary"
                                onClick={(e) => (isAsking ? stopStreaming() : handleSubmit(e))}
                                disabled={!input.trim() && !isAsking}
                                aria-label={isAsking ? "Stop generating" : "Send message"}
                            >
                                {isAsking ? <Square className="h-4 w-4" /> : <ArrowUp className="h-4 w-4" />}
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="top">
                            {isAsking ? "Stop generating" : "Send"}
                        </TooltipContent>
                    </Tooltip>
                </div>
                {askError && (
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <div className="absolute -top-6 right-0 text-destructive">
                                <AlertCircle className="h-4 w-4" />
                            </div>
                        </TooltipTrigger>
                        <TooltipContent side="top" className="bg-destructive text-destructive-foreground text-xs">
                            {askError}
                        </TooltipContent>
                    </Tooltip>
                )}
            </div>
        </TooltipProvider>
    );
};

export default IntegratedInput;