// components/chat/ChatMessages.tsx
'use client';

import React, { useRef, useEffect } from 'react';
import MessageBlock from './MessageBlock'; // Use the block component
import { Message as ApiMessage } from '@/lib/api';
import { MagicWandIcon } from '@radix-ui/react-icons'; // Keep for welcome
import { Terminal } from 'lucide-react'; // Keep for welcome text
import { LayoutPanelLeft } from 'lucide-react';

interface ChatMessagesProps {
    messages: ApiMessage[];
    isAsking: boolean; // Still useful for showing welcome message or global loading state
    // currentAIMessageId removed as MessageBlock now relies on its own message prop and isAsking
}

// -----------------------------

export default function ChatMessages({ messages, isAsking }: ChatMessagesProps) {
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
        // This outer div handles the scrolling
        <div ref={scrollContainerRef} className="flex-grow overflow-y-auto p-4 md:p-6 scroll-smooth bg-background dark:bg-gray-950/70"> {/* Adjusted background */}
             {/* This inner div centers and constrains the width of the messages */}
             <div className="max-w-4xl mx-auto w-full space-y-8"> {/* Increased space-y, Added max-w, mx-auto */}
                {messages.length === 0 && !isAsking ? (
                    // Welcome Message (Unchanged)
                    <div className="flex flex-col items-center justify-center h-[calc(100vh-10rem)] text-center text-muted-foreground"> {/* Adjusted height */}
                         <MagicWandIcon className="w-16 h-16 text-muted-foreground/50 mb-4" />
                         <h3 className="text-lg font-semibold text-foreground mb-1">Assistant Ready</h3>
                         <p className="text-sm px-4 max-w-xs"> Use the sidebar <span className="inline-block mx-1 text-lg align-text-bottom">☰</span> to manage tasks, then ask a question below. </p>
                          <p className="text-xs mt-2 px-4 max-w-xs"> Workflow results <span className="inline-block mx-0.5"><LayoutPanelLeft size={12} /></span> will appear in the right pane. </p>
                    </div>
                ) : (
                    messages.map((msg) => (
                        <MessageBlock
                            key={msg.id ?? `msg-${msg.sender}-${Math.random()}`} // Ensure stable key if id exists
                            message={msg}
                            isAsking={isAsking && msg.sender === 'ai' && !msg.text && !msg.error} // Pass more specific streaming state?
                        />
                    ))
                )}
                {/* Scroll target div */}
                <div ref={messagesEndRef} />
            </div>
        </div>
    );
}