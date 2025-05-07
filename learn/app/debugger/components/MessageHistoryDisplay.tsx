// app/debugger/components/MessageHistoryDisplay.tsx
'use client';
import React from 'react';
import { Message as ApiMessage } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface MessageHistoryDisplayProps {
    messages: ApiMessage[];
    isRunning: boolean;
}

export default function MessageHistoryDisplay({ messages, isRunning }: MessageHistoryDisplayProps) {
    if (!messages || messages.length === 0) {
        return (
            <div className="flex items-center justify-center h-32 rounded-lg bg-muted/50">
                <div className="text-center text-muted-foreground text-sm">
                    No messages in current state
                </div>
            </div>
        );
    }

    type MessageDisplayType = 'human' | 'ai' | 'tool' | 'ai_tool_call' | 'unknown' | 'system';

    return (
        <div className="space-y-3">
            {messages.map((msg, index) => {
                let type: MessageDisplayType = 'unknown';
                if (msg.type && ['human', 'ai', 'tool', 'ai_tool_call', 'system'].includes(msg.type)) {
                    type = msg.type as MessageDisplayType;
                } else {
                    type = msg.tool_call_id ? 'tool' :
                           msg.tool_calls && msg.tool_calls.length > 0 ? 'ai_tool_call' :
                           msg.sender === 'user' ? 'human' :
                           msg.sender === 'ai' ? 'ai' : 'unknown';
                }

                const content = msg.content ?? msg.text ?? '';
                const toolCalls = msg.tool_calls ?? [];
                const toolCallId = msg.tool_call_id;
                const isLastMessage = index === messages.length - 1;
                const isAiGenerating = isRunning && isLastMessage && type === 'ai';

                const messageColors = {
                    ai: 'bg-blue-50 border-blue-200 dark:bg-blue-900/20 dark:border-blue-800/50',
                    ai_tool_call: 'bg-blue-50 border-blue-200 dark:bg-blue-900/20 dark:border-blue-800/50',
                    human: 'bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-800/50',
                    tool: 'bg-purple-50 border-purple-200 dark:bg-purple-900/20 dark:border-purple-800/50',
                    system: 'bg-gray-50 border-gray-200 dark:bg-gray-800 dark:border-gray-700',
                    unknown: 'bg-gray-50 border-gray-200 dark:bg-gray-800 dark:border-gray-700',
                };

                // Format JSON output with syntax highlighting-like styling
                const formatJson = (obj: any) => {
                    const jsonString = JSON.stringify(obj, null, 2);
                    return jsonString
                        .replace(/"(\w+)":/g, '"<span class="text-blue-600 dark:text-blue-400">$1</span>":')
                        .replace(/: "(.*?)"/g, ': "<span class="text-green-600 dark:text-green-400">$1</span>"')
                        .replace(/: (true|false|null|\d+)/g, ': <span class="text-purple-600 dark:text-purple-400">$1</span>');
                };

                return (
                    <div 
                        key={`${msg.id || index}`}
                        className={cn(
                            'rounded-lg border p-3 transition-all shadow-sm hover:shadow-md',
                            messageColors[type]
                        )}
                    >
                        <div className="flex justify-between items-center mb-2 gap-2">
                            <Badge 
                                variant="outline" 
                                className={cn("capitalize text-xs font-medium px-2 py-0.5", {
                                    'border-blue-300 text-blue-700 dark:border-blue-600 dark:text-blue-200': type.includes('ai'),
                                    'border-green-300 text-green-700 dark:border-green-600 dark:text-green-200': type === 'human',
                                    'border-purple-300 text-purple-700 dark:border-purple-600 dark:text-purple-200': type === 'tool',
                                    'border-gray-300 text-gray-700 dark:border-gray-600 dark:text-gray-200': type === 'system' || type === 'unknown',
                                })}
                            >
                                {type.replace('_', ' ')}
                            </Badge>
                            
                            {toolCallId && (
                                <span 
                                    className="text-xs font-mono text-muted-foreground bg-background px-2 py-0.5 rounded truncate max-w-[120px]"
                                    title={toolCallId}
                                >
                                    {toolCallId.substring(0, 4)}...{toolCallId.slice(-4)}
                                </span>
                            )}
                        </div>

                        <div className="mt-1">
                            {(type === 'human' || (type === 'ai' && toolCalls.length === 0)) && (
                                <div className="prose prose-sm dark:prose-invert max-w-none">
                                    {content ? (
                                        <pre className="whitespace-pre-wrap break-words font-sans text-sm bg-background/50 p-2 rounded">
                                            {content}
                                            {isAiGenerating && (
                                                <span className="ml-2 text-muted-foreground text-xs">
                                                    (generating...)
                                                </span>
                                            )}
                                        </pre>
                                    ) : (
                                        <p className="text-muted-foreground italic text-sm">
                                            {isAiGenerating ? 'AI generating...' : '(Empty message)'}
                                        </p>
                                    )}
                                </div>
                            )}

                            {type === 'ai_tool_call' && toolCalls.length > 0 && (
                                <div className="space-y-2">
                                    <p className="text-xs text-muted-foreground italic">
                                        {toolCalls.length} tool call{toolCalls.length > 1 ? 's' : ''} requested:
                                    </p>
                                    {toolCalls.map((tc, idx) => (
                                        <div 
                                            key={tc.id || idx} 
                                            className="bg-background/50 dark:bg-black/20 p-2 rounded border overflow-auto max-h-60"
                                        >
                                            <pre 
                                                className="text-xs font-mono"
                                                dangerouslySetInnerHTML={{
                                                    __html: formatJson(tc)
                                                }}
                                            />
                                        </div>
                                    ))}
                                </div>
                            )}

                            {type === 'tool' && (
                                <div className="bg-background/50 dark:bg-black/20 p-2 rounded border overflow-auto max-h-60">
                                    <pre 
                                        className="text-xs font-mono"
                                        dangerouslySetInnerHTML={{
                                            __html: formatJson(typeof content === 'string' ? JSON.parse(content) : content)
                                        }}
                                    />
                                </div>
                            )}

                            {type === 'system' && (
                                <div className="text-sm text-muted-foreground italic bg-background/50 p-2 rounded">
                                    <p className="whitespace-pre-wrap break-words">
                                        {content || '(System message)'}
                                    </p>
                                </div>
                            )}

                            {type === 'unknown' && (
                                <p className="text-sm text-muted-foreground italic bg-background/50 p-2 rounded">
                                    {content || '(Unknown message type)'}
                                </p>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}