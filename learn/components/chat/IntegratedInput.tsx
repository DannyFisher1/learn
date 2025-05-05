// components/chat/IntegratedInput.tsx
'use client';

import React, { useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import TextareaAutosize from 'react-textarea-autosize';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { PaperPlaneIcon, StopIcon, InfoCircledIcon } from '@radix-ui/react-icons'; // Using Radix icons
import { cn } from '@/lib/utils';
import { SendHorizontal, StopCircle, AlertCircle } from 'lucide-react'; // Removed ChevronRight, Menu

// Define the props required by this new input component
interface IntegratedInputProps {
    input: string;
    // Accept direct string changes too
    handleInputChange: (event: React.ChangeEvent<HTMLTextAreaElement> | string) => void;
    // Accept direct string submissions too
    handleSubmit: (event?: React.FormEvent | string) => Promise<void>;
    handleKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void; // Keep keydown for Enter submit
    stopStreaming: () => void;
    isAsking: boolean;
    askError: string | null;
}

const IntegratedInput: React.FC<IntegratedInputProps> = ({
    input,
    handleInputChange,
    handleSubmit,
    handleKeyDown,
    stopStreaming,
    isAsking,
    askError,
}) => {
    const textAreaRef = useRef<HTMLTextAreaElement>(null);

    // Focus textarea when isAsking becomes false
    useEffect(() => {
        if (!isAsking) {
            // Short delay can help ensure element is ready after state change
            const timer = setTimeout(() => textAreaRef.current?.focus(), 50);
            return () => clearTimeout(timer);
        }
    }, [isAsking]);

    useEffect(() => {
        if (textAreaRef.current) {
            textAreaRef.current.style.height = 'auto'; // Reset height
            const scrollHeight = textAreaRef.current.scrollHeight;
            // Set max height (e.g., 5 lines, assuming line height around 20px)
            const maxHeight = 5 * 24;
            textAreaRef.current.style.height = `${Math.min(scrollHeight, maxHeight)}px`;
        }
    }, [input]);

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
        <div className="flex items-end gap-2 p-4 border-t bg-background">
            {/* Error Display */}
            {askError && (
                <div className="absolute bottom-full left-0 right-0 mb-1 px-4 py-1.5 bg-destructive/10 text-destructive text-xs font-medium border-t border-b border-destructive/30 flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    <span>Error: {askError}</span>
                </div>
            )}

            {/* Text Input Area - Removed scope display */}
            <div className="flex-grow relative">
                <TextareaAutosize
                    ref={textAreaRef}
                    value={input}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask anything... (Shift+Enter for newline)"
                    rows={1}
                    className="w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 pr-10 overflow-y-auto max-h-[120px]"
                    aria-label="Chat input"
                    disabled={isAsking}
                />
                {/* Character count or other indicators could go here absolute inside the textarea */}
            </div>

            {/* Submit/Stop Button */}
            <TooltipProvider delayDuration={100}>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button
                            type="button"
                            onClick={() => isAsking ? stopStreaming() : handleSubmit()}
                            size="icon"
                            className={cn(
                                "rounded-full flex-shrink-0 w-9 h-9 transition-colors duration-200",
                                isAsking
                                    ? "bg-yellow-500 hover:bg-yellow-600 text-white"
                                    : input.trim()
                                        ? "bg-primary hover:bg-primary/90 text-primary-foreground"
                                        : "bg-muted text-muted-foreground cursor-not-allowed"
                            )}
                            disabled={!isAsking && !input.trim()}
                            aria-label={isAsking ? "Stop generating" : "Send message"}
                        >
                            {isAsking ? <StopCircle className="h-5 w-5" /> : <SendHorizontal className="h-5 w-5" />}
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                        {isAsking ? "Stop Generation" : (input.trim() ? "Send Message" : "Enter a message")}
                    </TooltipContent>
                </Tooltip>
            </TooltipProvider>
        </div>
    );
};

export default IntegratedInput;