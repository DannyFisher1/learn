'use client';

import React, { useRef } from 'react';
import { Button } from '@/components/ui/button';
import TextareaAutosize from 'react-textarea-autosize';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import ModelSelector from '../common/ModelSelector'; // Adjusted path
import ChatOptionsMenu from './ChatOptionsMenu'; // Assuming ChatOptionsMenu is in the same directory
import { UploadDropdownRef } from '../common/UploadDropdown'; // Adjusted path
import { PaperPlaneIcon, ReloadIcon, BookmarkIcon as TagIcon, StopIcon } from '@radix-ui/react-icons';
import { cn } from '@/lib/utils';

interface ChatInputAreaProps {
    input: string;
    handleInputChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
    handleKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
    handleSubmit: (event?: React.FormEvent) => void;
    isAsking: boolean;
    stopStreaming?: () => void;
    askError: string | null;
    selectedFilenames: Set<string>;
    selectedTag: string | null;
    onFilenameToggle: (filename: string | null) => void;
    uploadDropdownRef: React.RefObject<UploadDropdownRef | null>;
    triggerDocListRefresh: number;
    getScopeText: () => string; // Pass the helper function down
    onDocumentsManaged: () => void;
}

export default function ChatInputArea({ 
    input, 
    handleInputChange, 
    handleKeyDown, 
    handleSubmit, 
    isAsking, 
    stopStreaming,
    askError, 
    selectedFilenames, 
    selectedTag, 
    onFilenameToggle,
    uploadDropdownRef,
    triggerDocListRefresh,
    getScopeText,
    onDocumentsManaged
}: ChatInputAreaProps) {
    const textAreaRef = useRef<HTMLTextAreaElement>(null); // Keep local ref if needed for focus

    // Focus textarea when isAsking becomes false (moved from parent)
    React.useEffect(() => {
        if (!isAsking) {
            setTimeout(() => textAreaRef.current?.focus(), 0);
        }
    }, [isAsking]);

    // --- Submit/Stop Button Handler ---
    const handleButtonClick = (event: React.MouseEvent<HTMLButtonElement>) => {
        event.preventDefault(); // Prevent default button behavior
        if (isAsking && stopStreaming) {
             stopStreaming(); // Call stop function if asking
        } else if (!isAsking && input.trim()) {
             handleSubmit(); // Call submit function if not asking and input is present
        }
    };
    // -----------------------------

    // --- Form Submit Handler ---
    const internalHandleSubmit = (event: React.FormEvent) => {
        event.preventDefault(); // Prevent default form submission (page reload)
        if (!isAsking && input.trim()) { // Only submit if not already asking
             handleSubmit();
        }
    };
    // ---------------------------

    return (
        <form onSubmit={internalHandleSubmit} className="p-3 border-t bg-background flex-shrink-0">
            {/* Scope display */}
            <p className="text-xs text-muted-foreground mb-2 px-1 flex items-center gap-1">
                <span>Query Scope:</span>
                {selectedTag && selectedFilenames.size === 0 && <TagIcon className="w-3 h-3 inline-block text-primary"/>}
                <span>{getScopeText()}</span>
            </p>
            {/* Error display */}
            {askError && !isAsking && <p className="text-xs text-destructive mb-2 px-1">{askError}</p>}

            <div className="flex items-end gap-2">
                {/* Options Menu */}
                <ChatOptionsMenu 
                    selectedFilenames={selectedFilenames}
                    onFilenameToggle={onFilenameToggle}
                    uploadDropdownRef={uploadDropdownRef}
                    triggerDocListRefresh={triggerDocListRefresh}
                    onDocumentsManaged={onDocumentsManaged}
                />

                {/* Textarea */}
                <TextareaAutosize
                    ref={textAreaRef}
                    value={input}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask a question (Shift+Enter for new line)..."
                    disabled={isAsking}
                    className={cn(
                        "flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
                        "flex-grow resize-none overflow-hidden min-h-[40px]"
                    )}
                    aria-label="Chat input"
                    rows={1}
                    maxRows={6}
                />

                {/* Model Selector */}
                <TooltipProvider delayDuration={100}>
                     <Tooltip>
                         <TooltipTrigger asChild>
                             <div className="self-end mb-[1px]">
                                 <ModelSelector />
                             </div>
                         </TooltipTrigger>
                         <TooltipContent side="top"><p>Select AI Provider</p></TooltipContent>
                     </Tooltip>
                 </TooltipProvider>

                {/* Send / Stop Button */}
                <TooltipProvider delayDuration={100}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                type="button"
                                onClick={handleButtonClick}
                                size="icon"
                                disabled={!isAsking && !input.trim()}
                                aria-label={isAsking ? "Stop generating" : "Send message"}
                                variant={isAsking ? "destructive" : "default"}
                                className="h-9 w-9 flex-shrink-0 self-end mb-[1px]"
                            >
                                {isAsking ? <StopIcon className="h-4 w-4" /> : <PaperPlaneIcon className="h-4 w-4" />}
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="top"><p>{isAsking ? "Stop Generating" : "Send Message"}</p></TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            </div>
        </form>
    );
}
