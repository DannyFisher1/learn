// app/debugger/components/ExecutionLog.tsx
'use client';

import React from 'react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChevronsRight } from 'lucide-react'; // Using ChevronsRight

interface ExecutionLogProps {
    executionLog: string[];
    isGraphLoading: boolean;
}

export default function ExecutionLog({ executionLog, isGraphLoading }: ExecutionLogProps) {
    return (
        <div className="flex-1 overflow-hidden flex flex-col">
            <div className="px-4 py-3 border-b dark:border-gray-700 flex items-center gap-2 text-sm font-medium text-muted-foreground flex-shrink-0">
                <ChevronsRight className="w-4 h-4" /> Execution Log
            </div>
            <ScrollArea className="flex-1">
                <div className="p-3 text-xs font-mono">
                    {executionLog.length === 0 ? (
                        <div className="text-center py-4 text-muted-foreground text-xs italic">
                            {isGraphLoading ? 'Loading graph...' : 'Run graph to see logs'}
                        </div>
                    ) : (
                        <div className="space-y-1.5">
                            {executionLog.map((log, index) => (
                                <p key={index} className="whitespace-pre-wrap break-words border-b border-dashed border-border/10 pb-1 last:border-b-0">
                                    <span className="text-muted-foreground/70 mr-1">{log.split(': ')[0]}:</span>
                                    {log.split(': ').slice(1).join(': ')}
                                </p>
                            ))}
                        </div>
                    )}
                </div>
            </ScrollArea>
        </div>
    );
}