'use client';

import React, { useRef, useEffect } from 'react';
import Message from './Message'; // Assuming Message is in the same directory
import { Message as ApiMessage } from '@/lib/api';
import { MagicWandIcon } from '@radix-ui/react-icons'; // Or keep DotsVerticalIcon from parent
import { DotsVerticalIcon } from '@radix-ui/react-icons'; // Keep consistent icon for prompt

interface ChatMessagesProps {
    messages: ApiMessage[];
    isAsking: boolean; // To know whether to show the welcome message
    currentAIMessageId?: string | null; // Add optional prop for styling/identifying streaming message
}

export default function ChatMessages({ messages, isAsking, currentAIMessageId }: ChatMessagesProps) {
    const messagesEndRef = useRef<null | HTMLDivElement>(null);

    // Simplified scroll logic, might need adjustment if parent handles scroll
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    return (
        <div className="flex-grow overflow-y-auto p-4 space-y-4 bg-muted/30 scroll-smooth">
            {messages.length === 0 && !isAsking ? (
                <div className="flex flex-col items-center justify-center h-full text-center">
                    <MagicWandIcon className="w-16 h-16 text-muted-foreground/50 mb-4" />
                    <h3 className="text-lg font-semibold text-foreground mb-1">Start Chatting</h3>
                    <p className="text-sm text-muted-foreground px-4 max-w-xs">
                        Upload documents using the <DotsVerticalIcon className="inline h-3 w-3 mx-0.5" /> menu,
                        optionally select scope/tag, then ask a question.
                    </p>
                </div>
            ) : (
                messages.map((msg, index) => (
                    <Message key={msg.id ?? `msg-${index}`} message={msg} isStreaming={msg.id === currentAIMessageId} />
                ))
            )}
            <div ref={messagesEndRef} />
        </div>
    );
}
