// components/chat/IntegratedInput.tsx
'use client';

import React, { useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import TextareaAutosize from 'react-textarea-autosize';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { PaperPlaneIcon, StopIcon, InfoCircledIcon } from '@radix-ui/react-icons'; // Using Radix icons
import { cn } from '@/lib/utils';

// Define the props required by this new input component
interface IntegratedInputProps {
    input: string;
    // Accept direct string changes too
    handleInputChange: (event: React.ChangeEvent<HTMLTextAreaElement> | string) => void;
    // Accept direct string submissions too
    handleSubmit: (event?: React.FormEvent | string) => void;
    handleKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void; // Keep keydown for Enter submit
    stopStreaming?: () => void;
    isAsking: boolean;
    askError: string | null;
    scopeText: string; // The text describing the current scope (e.g., "All Documents", "File: X.pdf")
    // NEW: Callback to trigger opening the sidebar (e.g., when clicking the scope text)
    onToggleSidebar?: () => void;
}

export default function IntegratedInput({
    input,
    handleInputChange,
    handleSubmit,
    handleKeyDown,
    stopStreaming,
    isAsking,
    askError,
    scopeText,
    onToggleSidebar // <-- Receive sidebar toggle callback
}: IntegratedInputProps) {
    const textAreaRef = useRef<HTMLTextAreaElement>(null);

    // Focus textarea when isAsking becomes false
    useEffect(() => {
        if (!isAsking) {
            // Short delay can help ensure element is ready after state change
            const timer = setTimeout(() => textAreaRef.current?.focus(), 50);
            return () => clearTimeout(timer);
        }
    }, [isAsking]);

    // Submit/Stop Button Handler (logic remains similar)
    const handleButtonClick = (event: React.MouseEvent<HTMLButtonElement>) => {
        event.preventDefault();
        if (isAsking && stopStreaming) {
            stopStreaming();
        } else if (!isAsking && input.trim()) {
            handleSubmit();
        }
    };

    // Internal Form Submit Handler
    const internalHandleSubmit = (event: React.FormEvent) => {
        event.preventDefault();
        if (!isAsking && input.trim()) {
            handleSubmit();
        }
    };

    return (
        // Removed form tag initially, can add back if needed for accessibility/semantic reasons
        // Use padding and background that matches/blends with the message area above it
        <div className="p-3 md:p-4 border-t bg-background flex-shrink-0 space-y-2">
            {/* Top row for scope and errors */}
            <div className="flex justify-between items-center px-1 min-h-[1.25rem]"> {/* Fixed height to prevent layout shifts */}
                {/* Scope Display - Make it interactive */}
                <TooltipProvider delayDuration={100}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                             <button
                                 onClick={onToggleSidebar}
                                 className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
                                 aria-label="Toggle document sidebar"
                             >
                                <InfoCircledIcon className="w-3 h-3 flex-shrink-0" />
                                <span className="truncate max-w-[200px] md:max-w-[300px]"> {/* Limit width */}
                                     Scope: {scopeText}
                                </span>
                            </button>
                        </TooltipTrigger>
                        <TooltipContent side="top">
                            <p>Click to view/change document scope</p>
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>

                {/* Error display */}
                {askError && !isAsking && (
                    <p className="text-xs text-destructive text-right flex-shrink-0 ml-2">{askError}</p>
                )}
            </div>

            {/* Main input row */}
            <div className="flex items-end gap-2">
                 {/* Removed ChatOptionsMenu */}

                 {/* Textarea - updated styling */}
                 <TextareaAutosize
                    ref={textAreaRef}
                    value={input}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask a question..."
                    disabled={isAsking}
                    className={cn(
                        // Base styling for flex, width, interaction
                        "flex w-full resize-none overflow-hidden min-h-[40px] max-h-[150px]", // Allow more vertical space
                        // Appearance: remove default border initially, add focus ring
                        "rounded-lg border border-transparent bg-muted/60 px-3 py-2 text-sm",
                        "placeholder:text-muted-foreground",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:border-primary/30 focus-visible:bg-background", // Enhance focus style
                        "disabled:cursor-not-allowed disabled:opacity-60"
                    )}
                    aria-label="Chat input"
                    rows={1}
                    maxRows={6} // Keep max rows
                />

                 {/* Removed ModelSelector - moved to top bar */}

                {/* Send / Stop Button */}
                <TooltipProvider delayDuration={100}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                type="button" // Use type="button" if not submitting a form directly
                                onClick={handleButtonClick}
                                size="icon"
                                disabled={!isAsking && !input.trim()}
                                aria-label={isAsking ? "Stop generating" : "Send message"}
                                variant={isAsking ? "destructive" : "default"}
                                className={cn(
                                    "h-9 w-9 flex-shrink-0 self-end rounded-lg transition-all", // Match input border radius
                                    // Add slight scaling effect on hover/focus when enabled
                                    !isAsking && input.trim() && "hover:scale-105 active:scale-95"
                                )}
                            >
                                {isAsking ? <StopIcon className="h-4 w-4" /> : <PaperPlaneIcon className="h-4 w-4" />}
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="top">
                            <p>{isAsking ? "Stop Generating" : "Send Message (Enter)"}</p>
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            </div>
        </div>
    );
}