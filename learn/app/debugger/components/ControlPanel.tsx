// app/debugger/components/ControlPanel.tsx
'use client';

import React from 'react';
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from '@/components/ui/scroll-area';
import { AlertCircle, Play, Square, Terminal, ChevronsRight } from 'lucide-react';
import ExecutionLog from '@/app/debugger/components/ExecutionLog'; // Import ExecutionLog

interface ControlPanelProps {
    query: string;
    setQuery: (query: string) => void;
    isRunning: boolean;
    runError: string | null;
    handleRunGraph: () => void;
    isGraphLoading: boolean; // To disable button while graph loads
    executionLog: string[]; // Pass executionLog state
}

export default function ControlPanel({
    query,
    setQuery,
    isRunning,
    runError,
    handleRunGraph,
    isGraphLoading,
    executionLog,
}: ControlPanelProps) {
    return (
        <div className="w-80 flex flex-col border-r dark:border-gray-700 bg-background overflow-hidden flex-shrink-0">
            {/* Input Area */}
            <div className="p-4 border-b dark:border-gray-700 space-y-3 flex-shrink-0">
                <div className="space-y-1">
                    <label htmlFor="query-input" className="text-sm font-medium">
                        Enter Query
                    </label>
                    <Textarea
                        id="query-input"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Enter query to trace..."
                        rows={4}
                        className="resize-none text-sm"
                        disabled={isRunning || isGraphLoading}
                    />
                </div>
                {runError && (
                    <div className="flex items-center gap-2 text-xs text-destructive bg-destructive/10 p-2 rounded-md border border-destructive/30">
                        <AlertCircle className="w-4 h-4 flex-shrink-0" />
                        <span className="break-all">{runError}</span>
                    </div>
                )}
                <Button
                    variant={isRunning ? "destructive" : "default"}
                    onClick={handleRunGraph}
                    disabled={isGraphLoading || (!isRunning && !query.trim())}
                    className="w-full"
                >
                    {isRunning ? (
                        <><Square className="w-4 h-4 mr-2" /> Stop Execution</>
                    ) : (
                        <><Play className="w-4 h-4 mr-2" /> Run Graph</>
                    )}
                </Button>
            </div>

            {/* Execution Log */}
            <ExecutionLog executionLog={executionLog} isGraphLoading={isGraphLoading} />
        </div>
    );
}