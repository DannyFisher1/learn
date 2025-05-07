// app/debugger/components/DetailsTabs.tsx
'use client';

import React, { useMemo } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from '@/components/ui/scroll-area';
import { Activity, MessagesSquare, Info, Eye, Zap, Terminal as TerminalIcon, Package, Bot, Ruler } from 'lucide-react'; // Using Ruler for ToolIcon
import NodeInspectionPanel from './NodeInspectionPanel'; // Will pass correct props
import MessageHistoryDisplay from './MessageHistoryDisplay'; // Will pass correct props
import { AllNodeExecutionDetails } from '@/app/debugger/page'; // Import types from page
import { Node as FlowNode } from '@xyflow/react';
import { Message as ApiMessage } from '@/lib/api';
import { Badge } from '@/components/ui/badge'; // For tool name badge

// Helper to format data for pre display (can be moved to utils if used elsewhere)
const formatDataForPreDisplay = (data: any) => {
    if (data === undefined) return "undefined";
    if (data === null) return "null";
    if (typeof data === 'string') return data;
    try {
        return JSON.stringify(data, null, 2);
    } catch (e) {
        return String(data);
    }
};

interface DetailsTabsProps {
    allNodeExecutionDetails: AllNodeExecutionDetails;
    selectedNodeForInspectionId: string | null; // This is the invocationId (e.g., "agent:1" or just "agent")
    nodes: FlowNode[]; // Full list of graph nodes for label lookup
    currentStateMessages: ApiMessage[];
    finalAnswer: string;
    isRunning: boolean;
    lastToolCall: { name?: string; args?: any; id?: string } | null; // Typed for clarity
    lastToolResult: { id?: string; result?: any } | null;           // Typed for clarity
    activeNodeIdDuringRun: string | null; // To show which node is live
}

export default function DetailsTabs({
    allNodeExecutionDetails,
    selectedNodeForInspectionId,
    nodes,
    currentStateMessages,
    finalAnswer,
    isRunning,
    lastToolCall,
    lastToolResult,
    activeNodeIdDuringRun,
}: DetailsTabsProps) {

    const getSelectedNodeBaseId = (invocationId: string | null): string | null => {
        if (!invocationId) return null;
        return invocationId.split(':')[0];
    };

    const getSelectedNodeLabel = (baseId: string | null): string => {
        if (!baseId) return "None";
        const node = nodes.find(n => n.id === baseId);
        if (node && node.data && React.isValidElement(node.data.label)) {
            const labelElement = node.data.label as React.ReactElement<{ children?: React.ReactNode }>;
            const findText = (children: React.ReactNode): string => {
                let text = '';
                React.Children.forEach(children, (child) => {
                    if (typeof child === 'string') text += child;
                    else if (React.isValidElement(child) && (child.props as { children?: React.ReactNode })?.children) {
                        text += findText((child.props as { children: React.ReactNode }).children);
                    }
                });
                return text.trim();
            };
            return (labelElement.props && findText(labelElement.props.children)) || baseId;
        }
        return baseId;
    };

    const inspectedNodeBaseId = getSelectedNodeBaseId(selectedNodeForInspectionId);
    const inspectedNodeLabel = getSelectedNodeLabel(inspectedNodeBaseId);
    const inspectedNodeDetail = selectedNodeForInspectionId ? allNodeExecutionDetails[selectedNodeForInspectionId] : null;

    const activeNodeBaseId = getSelectedNodeBaseId(activeNodeIdDuringRun);
    const activeNodeLabelText = getSelectedNodeLabel(activeNodeBaseId);
    const activeNodeDetail = activeNodeIdDuringRun ? allNodeExecutionDetails[activeNodeIdDuringRun] : null;


    return (
        <div className="w-96 border-l dark:border-gray-700 bg-card overflow-hidden flex flex-col flex-shrink-0 h-full">
            <Tabs defaultValue="details" className="flex flex-col h-full">
                <TabsList className="grid w-full grid-cols-2 h-12 rounded-none border-b flex-shrink-0">
                    <TabsTrigger value="details" className="text-xs"><Activity className="w-3.5 h-3.5 mr-1.5" />Run Details</TabsTrigger>
                    <TabsTrigger value="history" className="text-xs"><MessagesSquare className="w-3.5 h-3.5 mr-1.5" />Messages</TabsTrigger>
                </TabsList>
                
                <TabsContent value="details" className="flex-1 overflow-y-auto m-0 p-0"> {/* Let ScrollArea handle padding */}
                    <ScrollArea className="h-full w-full p-4" type="always"> {/* Padding on ScrollArea's viewport */}
                        
                        {/* Currently Running Node Info (if isRunning) */}
                        {isRunning && activeNodeIdDuringRun && activeNodeDetail && (
                            <div className="mb-4 p-3 bg-primary/5 dark:bg-primary/10 rounded-lg border border-primary/20">
                                <h3 className="text-xs font-semibold mb-2 text-primary uppercase tracking-wider flex items-center gap-1.5">
                                    <Zap size={13}/> Running: {activeNodeLabelText} 
                                    {activeNodeIdDuringRun !== activeNodeBaseId && ` (Invocation ${activeNodeIdDuringRun.split(':')[1]})`}
                                </h3>
                                {activeNodeDetail.input !== undefined && (
                                    <div className="mb-1.5">
                                        <p className="text-[10px] text-muted-foreground font-mono mb-0.5">INPUT:</p>
                                        <pre className="text-[11px] p-1.5 bg-background dark:bg-black/20 rounded border dark:border-gray-600/50 text-muted-foreground overflow-auto max-h-28"><code>{formatDataForPreDisplay(activeNodeDetail.input)}</code></pre>
                                    </div>
                                )}
                                 {activeNodeDetail.output !== undefined && ( // For streaming tokens to active node
                                    <div>
                                        <p className="text-[10px] text-muted-foreground font-mono mb-0.5">OUTPUT (Streaming):</p>
                                        <pre className="text-[11px] p-1.5 bg-background dark:bg-black/20 rounded border dark:border-gray-600/50 text-muted-foreground overflow-auto max-h-32"><code>{formatDataForPreDisplay(activeNodeDetail.output)}</code></pre>
                                    </div>
                                )}
                                {activeNodeDetail.status === 'running' && activeNodeDetail.output === undefined && (
                                    <p className="text-xs italic text-muted-foreground">Node running, awaiting output...</p>
                                )}
                            </div>
                        )}

                        {/* Inspected Node Details (if a node is clicked post-run or when not running) */}
                        {!isRunning && selectedNodeForInspectionId && inspectedNodeDetail && (
                            <NodeInspectionPanel 
                                nodeId={selectedNodeForInspectionId} // Full invocation ID
                                details={inspectedNodeDetail}
                                nodeLabel={inspectedNodeLabel} // Base label
                            />
                        )}
                        
                        {/* Global run info - displayed regardless of selection if available */}
                        {lastToolCall && (
                            <div className="mb-4">
                                <h3 className="text-xs font-semibold mb-2 flex items-center gap-1.5 text-purple-600 dark:text-purple-400 uppercase tracking-wider"><Ruler size={13}/>Last Tool Call</h3>
                                <div className="p-3 bg-muted/40 dark:bg-white/5 rounded-md border dark:border-gray-700/50 space-y-2">
                                    <div className="flex items-center justify-between">
                                        <Badge variant="secondary" className="font-mono text-xs">{lastToolCall.name || 'N/A'}</Badge>
                                        {lastToolCall.id && <span className="text-[10px] text-muted-foreground font-mono">ID: {lastToolCall.id?.substring(0, 8)}...</span>}
                                    </div>
                                    <pre className="text-[11px] p-2 bg-background dark:bg-black/20 rounded border dark:border-gray-600/50 text-muted-foreground overflow-auto max-h-28"><code>{formatDataForPreDisplay(lastToolCall.args)}</code></pre>
                                </div>
                            </div>
                        )}
                        {lastToolResult && (
                            <div className="mb-4">
                                <h3 className="text-xs font-semibold mb-2 flex items-center gap-1.5 text-green-600 dark:text-green-400 uppercase tracking-wider"><TerminalIcon size={13}/>Tool Result</h3>
                                <div className="p-3 bg-muted/40 dark:bg-white/5 rounded-md border dark:border-gray-700/50">
                                    {lastToolResult.id && <span className="text-[10px] text-muted-foreground font-mono block mb-1.5">For Call ID: {lastToolResult.id?.substring(0, 8)}...</span>}
                                    <pre className="text-[11px] p-2 bg-background dark:bg-black/20 rounded border dark:border-gray-600/50 text-muted-foreground overflow-auto max-h-40"><code>{formatDataForPreDisplay(lastToolResult.result)}</code></pre>
                                </div>
                            </div>
                        )}
                        
                        {finalAnswer && !isRunning && (
                            <div className="mt-4 p-3 bg-primary/10 dark:bg-primary/20 rounded-lg border border-primary/30 dark:border-primary/50">
                                <h3 className="text-xs font-semibold mb-2 text-primary uppercase tracking-wider">Final Answer</h3>
                                <p className="text-sm whitespace-pre-wrap break-words">{finalAnswer}</p>
                            </div>
                        )}

                        {/* Placeholder when nothing specific to show in details tab */}
                        {!isRunning && !selectedNodeForInspectionId && !lastToolCall && !activeNodeIdDuringRun && (
                             <div className="flex flex-col items-center justify-center text-center text-muted-foreground p-6 pt-10"> {/* Adjusted pt */}
                                 <Info size={28} className="mb-3 opacity-40" />
                                 <p className="text-xs mt-1">Run a query to see details, or click a node on the completed graph to inspect its I/O.</p>
                            </div>
                        )}
                         {isRunning && !activeNodeIdDuringRun && !finalAnswer && ( <div className="text-center py-4 text-muted-foreground text-xs italic">Awaiting graph execution details...</div> )}

                    </ScrollArea>
                </TabsContent>

                <TabsContent value="history" className="flex-1 overflow-y-auto m-0 p-0"> {/* Let ScrollArea handle padding */}
                    <ScrollArea className="h-full w-full p-4" type="always">
                       <MessageHistoryDisplay 
                           messages={currentStateMessages} 
                           isRunning={isRunning}
                       />
                    </ScrollArea>
                </TabsContent>
            </Tabs>
        </div>
    );
}