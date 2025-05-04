// components/chat/ChatMessages.tsx
'use client';

import React, { useRef, useEffect } from 'react';
import MessageBlock from '@/components/chat/MessageBlock'; // *** RENAME Message to MessageBlock ***
import { Message as ApiMessage } from '@/lib/api';
import { MagicWandIcon } from '@radix-ui/react-icons';
import { FileIcon, Terminal } from 'lucide-react'; // Use Lucide consistently

// Props Interface (remains mostly the same, passed down)
interface ChatMessagesProps {
    messages: ApiMessage[];
    isAsking: boolean;
    currentAIMessageId?: string | null;
    activeContextMessageId?: string | null;
    onShowContext?: (messageId: string | null) => void;
}

export default function ChatMessages({
    messages,
    isAsking,
    currentAIMessageId,
    activeContextMessageId,
    onShowContext
}: ChatMessagesProps) {
    const messagesEndRef = useRef<null | HTMLDivElement>(null);
    const scrollContainerRef = useRef<null | HTMLDivElement>(null);

    // Scroll logic (remains the same)
    useEffect(() => {
        const container = scrollContainerRef.current;
        if (container) {
            const threshold = 100;
            const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
            if (isNearBottom || messages.length <= 2) { // Scroll if near bottom or very start
                messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
            }
        } else {
             messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages]);

    return (
        // Container takes full height and allows vertical scroll
        <div ref={scrollContainerRef} className="flex-grow overflow-y-auto p-4 md:p-6 space-y-6 bg-muted/30 scroll-smooth"> {/* Increased spacing */}
            {messages.length === 0 && !isAsking ? (
                // Welcome message (can stay similar)
                <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
                     <MagicWandIcon className="w-16 h-16 text-muted-foreground/50 mb-4" />
                     <h3 className="text-lg font-semibold text-foreground mb-1">Assistant Ready</h3>
                     <p className="text-sm px-4 max-w-xs">
                         Use the sidebar <span className="inline-block mx-1 text-lg align-text-bottom">☰</span>
                          to upload or select documents, then ask a question below.
                     </p>
                      <p className="text-xs mt-2 px-4 max-w-xs">
                          Click AI responses <span className="inline-block mx-0.5"><Terminal size={12} /></span>
                          to see agent steps in the context pane.
                     </p>
                </div>
            ) : (
                // *** Render messages using the new MessageBlock component ***
                 messages.map((msg) => (
                    <MessageBlock // *** Use MessageBlock ***
                        key={msg.id ?? `msg-${msg.sender}-${Math.random()}`}
                        message={msg}
                        isStreaming={msg.id === currentAIMessageId}
                        isActiveContext={msg.id === activeContextMessageId}
                        onShowContext={onShowContext}
                    />
                ))
            )}
            {/* Div for scrolling into view */}
            <div ref={messagesEndRef} />
        </div>
    );
}