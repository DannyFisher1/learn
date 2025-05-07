// app/debugger/components/NodeInspectionPanel.tsx
'use client';

import React from 'react';
import { Eye, Package } from 'lucide-react'; // Using Lucide consistently
import { Badge } from '@/components/ui/badge';
import { NodeDetail } from '@/app/debugger/page'; // Import from parent page.tsx for now

const formatDataForPre = (data: any) => {
    if (data === undefined) return "undefined";
    if (data === null) return "null";
    if (typeof data === 'string' && data.startsWith("Processing...")) return <i className="text-muted-foreground">{data}</i>;
    if (typeof data === 'string') return data;
    try {
        // Special handling for AIMessage or AIMessageChunk output for 'agent' node
        if (typeof data === 'object' && data !== null && (data.type === 'ai' || data.type === 'AIMessageChunk')) {
            let display = `Type: ${data.type}\n`;
            if (data.content) display += `Content: ${String(data.content).substring(0, 200)}${String(data.content).length > 200 ? '...' : ''}\n`;
            if (data.tool_calls && data.tool_calls.length > 0) {
                display += `Tool Calls: ${JSON.stringify(data.tool_calls, null, 2)}`;
            } else if (data.tool_call_chunks && data.tool_call_chunks.length > 0){
                 display += `Tool Call Chunks: ${JSON.stringify(data.tool_call_chunks, null, 2)}`;
            }
            return display;
        }
        return JSON.stringify(data, null, 2);
    } catch (e) {
        return String(data);
    }
};


interface NodeInspectionPanelProps {
    nodeId: string; // Invocation ID e.g. "agent:1"
    details: NodeDetail;
    nodeLabel: string; // Base label e.g. "Agent"
}

export default function NodeInspectionPanel({ nodeId, details, nodeLabel }: NodeInspectionPanelProps) {
    const invocationNumber = nodeId.includes(':') ? `(Invocation ${nodeId.split(':')[1]})` : '';

    return (
        <div className="mb-4 p-3 bg-accent/10 dark:bg-accent/20 rounded-lg border border-accent/30 dark:border-accent/50">
            <h3 className="text-xs font-semibold mb-2 text-accent-foreground uppercase tracking-wider flex items-center gap-1.5">
                <Eye size={14} className="flex-shrink-0" />
                Inspecting: {nodeLabel} <span className="text-muted-foreground normal-case font-normal">{invocationNumber}</span>
            </h3>
            {details.type && (
                <Badge variant="outline" className="mb-2 text-[10px] border-accent/50 text-accent-foreground bg-accent/10">
                    Type: {details.type}
                </Badge>
            )}
            {details.input !== undefined && (
                <div className="mb-2">
                    <p className="text-[10px] text-muted-foreground font-mono mb-0.5">INPUT:</p>
                    <pre className="text-[11px] p-1.5 bg-background dark:bg-black/20 rounded border dark:border-gray-600/50 text-muted-foreground overflow-auto max-h-32">
                        <code>{formatDataForPre(details.input)}</code>
                    </pre>
                </div>
            )}
            {details.output !== undefined && (
                <div>
                    <p className="text-[10px] text-muted-foreground font-mono mb-0.5">OUTPUT:</p>
                    <pre className="text-[11px] p-1.5 bg-background dark:bg-black/20 rounded border dark:border-gray-600/50 text-muted-foreground overflow-auto max-h-48">
                        <code>{formatDataForPre(details.output)}</code>
                    </pre>
                </div>
            )}
            {details.status && <Badge variant={details.status === 'error' ? 'destructive': details.status === 'completed' ? 'default' : 'secondary'} className="mt-2 text-[10px] capitalize">{details.status}</Badge>}
            {(details.input === undefined && details.output === undefined && details.status !== 'running') && (
                <p className="text-xs italic text-muted-foreground">No detailed I/O captured for this invocation.</p>
            )}
             {details.status === 'running' && details.output === undefined && (
                <p className="text-xs italic text-muted-foreground mt-1">Node running, awaiting output...</p>
            )}
        </div>
    );
}