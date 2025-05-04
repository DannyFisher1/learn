// components/chat/ChatMessages.tsx
'use client';

import React, { useRef, useEffect } from 'react';
import MessageBlock from './MessageBlock'; // Use the renamed component
import { Message as ApiMessage } from '@/lib/api';
import { MagicWandIcon } from '@radix-ui/react-icons';
import { Terminal } from 'lucide-react'; // Keep Terminal for placeholder text

// --- Updated Props Interface ---
// Removed activeContextMessageId and onShowContext
interface ChatMessagesProps {
    messages: ApiMessage[];
    isAsking: boolean; // To know whether to show the welcome message
    currentAIMessageId?: string | null; // To style the currently streaming message
}
// -----------------------------

export default function ChatMessages({
    messages,
    isAsking,
    currentAIMessageId,
    // activeContextMessageId, <-- Removed
    // onShowContext           <-- Removed
}: ChatMessagesProps) {
    const messagesEndRef = useRef<null | HTMLDivElement>(null);
    const scrollContainerRef = useRef<null | HTMLDivElement>(null);

    // Scroll logic remains the same
    useEffect(() => {
        const container = scrollContainerRef.current;
        if (container) {
            const threshold = 100; // Pixels from bottom threshold
            const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
            // Scroll if near bottom, or if it's the very first message(s)
            if (isNearBottom || messages.length <= 2) {
                messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
            }
        } else {
             // Fallback on initial render
             messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
        }
    }, [messages]); // Dependency remains messages array

    return (
        <div ref={scrollContainerRef} className="flex-grow overflow-y-auto p-4 md:p-6 space-y-6 bg-muted/30 scroll-smooth">
            {messages.length === 0 && !isAsking ? (
                // --- Updated Welcome Message ---
                <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
                     <MagicWandIcon className="w-16 h-16 text-muted-foreground/50 mb-4" />
                     <h3 className="text-lg font-semibold text-foreground mb-1">Assistant Ready</h3>
                     <p className="text-sm px-4 max-w-xs">
                         Use the sidebar <span className="inline-block mx-1 text-lg align-text-bottom">☰</span>
                          to manage documents, then ask a question below.
                     </p>
                      <p className="text-xs mt-2 px-4 max-w-xs">
                          Context like agent steps <span className="inline-block mx-0.5"><Terminal size={12} /></span> or retrieved info
                          will appear automatically in the right pane.
                     </p>
                </div>
                // -------------------------------
            ) : (
                 messages.map((msg) => (
                    <MessageBlock
                        key={msg.id ?? `msg-${msg.sender}-${Math.random()}`}
                        message={msg}
                        isStreaming={msg.id === currentAIMessageId}
                        // --- Removed Context Props ---
                        // isActiveContext={msg.id === activeContextMessageId} <-- Removed
                        // onShowContext={onShowContext} <-- Removed
                        // -----------------------------
                    />
                ))
            )}
            {/* Scroll target div */}
            <div ref={messagesEndRef} />
        </div>
    );
}