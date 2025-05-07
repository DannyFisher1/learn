// app/debugger/components/GraphCanvas.tsx
'use client';

import React, { useEffect } from 'react';
import {
    ReactFlow,
    MiniMap,
    Controls,
    Background,
    Node,
    Edge,
    NodeMouseHandler,
    BackgroundVariant,
    ReactFlowProvider,
    Handle, // Ensure Handle is imported if used in node components
    Position, // Ensure Position is imported if used in node components
    MarkerType
} from '@xyflow/react';
import { Loader2, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils'; // Assuming cn is in lib/utils

// --- Re-declare or import Node Type Components if not globally available ---
// For simplicity, if these are small, they can be here. If larger or reused, import them.
const LLMNodeComponent = React.memo(({ data }: { data: any }) => (
    <> <Handle type="target" position={Position.Top} isConnectable={false} /> <div className={cn(`px-4 py-2 rounded-lg shadow-md border-2 w-full h-full flex items-center justify-center text-sm transition-all duration-300`, data.isActive ? 'border-blue-500 bg-blue-500/20 ring-2 ring-blue-500 ring-offset-1' : 'border-blue-500/80 bg-blue-500/10', data.isSelected ? 'ring-2 ring-green-500 ring-offset-1 border-green-500' : '', data.isActive ? 'font-semibold':'')}>{data.label}</div> <Handle type="source" position={Position.Bottom} isConnectable={false} /> </>
));
const ToolNodeComponent = React.memo(({ data }: { data: any }) => (
    <> <Handle type="target" position={Position.Top} isConnectable={false} /> <div className={cn(`px-4 py-2 rounded-lg shadow-md border-2 w-full h-full flex items-center justify-center text-sm transition-all duration-300`, data.isActive ? 'border-purple-500 bg-purple-500/20 ring-2 ring-purple-500 ring-offset-1' : 'border-purple-500/80 bg-purple-500/10', data.isSelected ? 'ring-2 ring-green-500 ring-offset-1 border-green-500' : '', data.isActive ? 'font-semibold':'')}>{data.label}</div> <Handle type="source" position={Position.Right} isConnectable={false} /> </>
));
const OutputNodeComponent = React.memo(({ data }: { data: any }) => (
    <> <Handle type="target" position={Position.Left} isConnectable={false} /> <div className={cn(`px-4 py-2 rounded-lg border-2 w-full h-full flex items-center justify-center text-sm font-medium transition-all duration-300`, data.isActive ? 'border-green-500 bg-green-500/20 ring-2 ring-green-500 ring-offset-1' : 'border-green-500/80 bg-green-500/10', data.isSelected ? 'ring-2 ring-offset-1 ring-blue-400 border-blue-400' : '', data.isActive ? 'font-semibold':'')}>{data.label}</div></>
));
const DefaultNodeComponent = React.memo(({ data }: { data: any }) => (
    <> <Handle type="target" position={Position.Top} isConnectable={false} /> <div className={cn(`px-4 py-2 rounded-lg shadow-md border text-card-foreground w-full h-full flex items-center justify-center text-sm transition-all duration-300`, data.isActive ? 'bg-card ring-2 ring-gray-700 dark:ring-gray-400 ring-offset-1' : 'bg-card', data.isSelected ? 'ring-2 ring-offset-1 ring-blue-400 border-blue-400' : '')}>{data.label}</div> <Handle type="source" position={Position.Bottom} isConnectable={false} /> </>
));

const nodeTypes = { 
  llmNode: LLMNodeComponent, 
  toolNode: ToolNodeComponent, 
  output: OutputNodeComponent, 
  default: DefaultNodeComponent 
};
// --- End Node Type Components ---


interface GraphCanvasProps {
    nodes: Node[];
    edges: Edge[];
    onNodesChange: (changes: any) => void;
    onEdgesChange: (changes: any) => void;
    isGraphLoading: boolean;
    graphError: string | null;
    // activeNodeIdDuringRun, selectedNodeForInspectionId are implicitly handled by node.data.isActive/isSelected
    onNodeClick: NodeMouseHandler;
}

export default function GraphCanvas({
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    isGraphLoading,
    graphError,
    onNodeClick,
}: GraphCanvasProps) {

    useEffect(() => {
        console.log('[GraphCanvas] Props update:', { 
            isGraphLoading, 
            graphError, 
            nodesCount: nodes.length, 
            edgesCount: edges.length 
        });
    }, [isGraphLoading, graphError, nodes, edges]);

    return (
      <ReactFlowProvider>
        <div className="flex-1 flex flex-col relative bg-gray-50 dark:bg-gray-900/50 overflow-hidden">
            {isGraphLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10">
                    <Loader2 className="w-8 h-8 text-primary animate-spin" />
                    <p className="ml-2 text-muted-foreground">Loading graph structure...</p>
                </div>
            )}
            {!isGraphLoading && graphError && (
                <div className="flex flex-col items-center justify-center h-full text-destructive p-4">
                    <AlertTriangle size={48} className="mb-2" />
                    <p className="text-lg font-medium">Error Loading Graph</p>
                    <p className="text-sm text-muted-foreground text-center">{graphError}</p>
                </div>
            )}
            {!isGraphLoading && !graphError && nodes.length > 0 && (
                 <div className="flex-grow rounded-md relative h-full w-full"> 
                     <ReactFlow
                        nodes={nodes}
                        edges={edges}
                        onNodesChange={onNodesChange}
                        onEdgesChange={onEdgesChange}
                        nodeTypes={nodeTypes}
                        fitView
                        fitViewOptions={{ padding: 0.25, duration: 200 }} // Adjusted padding & duration
                        defaultEdgeOptions={{
                            type: 'smoothstep',
                            markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15 },
                            style: { strokeWidth: 1.5 }
                        }}
                        minZoom={0.2} // Slightly more zoom out
                        maxZoom={2}
                        proOptions={{ hideAttribution: true }}
                        connectionLineStyle={{ stroke: 'hsl(var(--primary))', strokeWidth: 2 }}
                        onNodeClick={onNodeClick}
                        nodesDraggable={true} // Allow dragging nodes after run for inspection
                        nodesConnectable={false} // Usually false for a display-only debugger
                        elementsSelectable={true} // Allow selecting nodes for inspection
                     >
                         <Controls className="[&>button]:bg-background [&>button]:border [&>button]:shadow-sm dark:[&>button]:bg-gray-700 dark:[&>button]:border-gray-600" />
                         <MiniMap
                            nodeStrokeWidth={3}
                            zoomable
                            pannable
                            nodeColor={(n: Node) => {
                                if (n.data?.isActive) return 'hsl(var(--primary))'; // Running
                                if (n.data?.isSelected) return 'hsl(var(--accent))'; // Inspected
                                if (n.type === 'output') return '#22c55e';
                                if (n.type === 'llmNode') return '#3b82f6';
                                if (n.type === 'toolNode') return '#a855f7';
                                return '#a1a1aa';
                            }}
                            className="!bg-background dark:!bg-gray-800 border dark:border-gray-700"
                        />
                        <Background variant={BackgroundVariant.Dots} gap={18} size={0.6} className="opacity-60 dark:opacity-20" /> {/* Slightly adjusted */}
                     </ReactFlow>
                 </div>
            )}
            {!isGraphLoading && !graphError && nodes.length === 0 && (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                    Graph structure loaded, but no nodes were defined or an issue occurred.
                </div>
            )}
        </div>
      </ReactFlowProvider>
    );
}