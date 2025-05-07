// app/debugger/components/MessageHistoryDisplay.tsx
'use client';
import React from 'react';
import { Message as ApiMessage } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface MessageHistoryDisplayProps {
    messages: ApiMessage[];
    isRunning: boolean; // To show "AI generating..."
}

export default function MessageHistoryDisplay({ messages, isRunning }: MessageHistoryDisplayProps) {
    if (!messages || messages.length === 0) {
        return <div className="text-center py-4 text-muted-foreground text-xs italic">No messages in current state.</div>;
    }

    type MessageDisplayType = 'human' | 'ai' | 'tool' | 'ai_tool_call' | 'system' | 'unknown';

    return (
        <div className="space-y-2">
            {messages.map((msg, index) => {
                let type: MessageDisplayType = 'unknown';
                // Prioritize msg.type if backend provides it consistently from AgentState
                if (msg.type && ['human', 'ai', 'tool', 'ai_tool_call', 'system'].includes(msg.type)) {
                     type = msg.type as MessageDisplayType;
                } else { // Fallback to inference
                    type = msg.tool_call_id ? 'tool' :
                           msg.tool_calls && msg.tool_calls.length > 0 ? 'ai_tool_call' :
                           msg.sender === 'user' ? 'human' :
                           msg.sender === 'ai' ? 'ai' : 'unknown';
                }


                const content = msg.content ?? msg.text ?? '(No content available)';
                const toolCalls = msg.tool_calls;
                const toolCallId = msg.tool_call_id;

                return (
                    <div key={`${msg.id || type}-${index}-${Math.random()}`} className="mb-2 p-2.5 border rounded-md bg-background/30 dark:bg-white/5 text-xs shadow-sm">
                        <div className="flex items-center justify-between mb-1.5">
                            <Badge variant="outline" className={cn("capitalize", {
                                'border-blue-500 text-blue-700 dark:border-blue-400 dark:text-blue-300': type === 'ai' || type === 'ai_tool_call',
                                'border-green-500 text-green-700 dark:border-green-400 dark:text-green-300': type === 'human',
                                'border-purple-500 text-purple-700 dark:border-purple-400 dark:text-purple-300': type === 'tool',
                            })}>
                                {type.replace('_', ' ')}
                            </Badge>
                            {toolCallId && (<span className="text-[10px] text-muted-foreground font-mono">ID: {toolCallId.substring(0, 8)}...</span>)}
                        </div>
                        <div className="prose prose-xs dark:prose-invert max-w-none prose-p:my-1">
                            {(type === 'human' || (type === 'ai' && (!toolCalls || toolCalls.length === 0))) && (
                                <p className="whitespace-pre-wrap break-words">
                                    {content || (isRunning && index === messages.length - 1 && type === 'ai' ? 
                                        <span className="italic text-muted-foreground">AI generating...</span> : 
                                        <i>(Empty message)</i>)}
                                </p>
                            )}
                            {type === 'ai_tool_call' && toolCalls && toolCalls.length > 0 && (
                                <div className="space-y-1 mt-1">
                                    <p className="italic text-muted-foreground text-[10px]">Tool Call(s) Requested:</p>
                                    {toolCalls.map((tc: any, idx: number) => (
                                        <pre key={tc.id || idx} className="text-[10px] bg-muted/50 dark:bg-black/20 p-1.5 rounded border text-muted-foreground overflow-auto">
                                            <code>{JSON.stringify(tc, null, 1)}</code>
                                        </pre>
                                    ))}
                                </div>
                            )}
                            {type === 'tool' && (
                                <div className="mt-1">
                                    <pre className="text-[10px] bg-muted/50 dark:bg-black/20 p-1.5 rounded border text-muted-foreground overflow-auto max-h-40">
                                        <code>{typeof content === 'string' ? content : JSON.stringify(content, null, 1)}</code>
                                    </pre>
                                </div>
                            )}
                             {type === 'system' && ( // Handle system messages if they appear
                                <p className="whitespace-pre-wrap break-words text-muted-foreground italic text-[10px]">
                                    (System): {content}
                                </p>
                            )}
                            {type === 'unknown' && <p className="whitespace-pre-wrap break-words italic text-muted-foreground">{content}</p>}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}