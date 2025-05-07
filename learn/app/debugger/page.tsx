// app/debugger/page.tsx
'use client';

import React, { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import { Node, Edge, useNodesState, useEdgesState, NodeMouseHandler, Position, MarkerType } from '@xyflow/react'; // Added Position, MarkerType

import { AskPayload, StreamLogCallbacks, StreamLogData, askQuestionStream, Message as ApiMessage } from '@/lib/api';
import { getBaseUrl } from '@/lib/utils';

import ControlPanel from './components/ControlPanel';
import GraphCanvas from './components/GraphCanvas'; // This will receive nodeTypes
import DetailsTabs from './components/DetailsTabs';

import { Waypoints, Loader2, Bot, Ruler as ToolIcon } from 'lucide-react'; // Keep Bot, ToolIcon here
import { Badge } from '@/components/ui/badge';

export interface NodeDetail {
    input?: any;
    output?: any;
    type?: string; 
    status?: 'idle' | 'running' | 'completed' | 'error';
    name?: string; 
    error?: string;
}
export interface AllNodeExecutionDetails {
    [invocationId: string]: NodeDetail; 
}

const initialNodes: Node[] = [];
const initialEdges: Edge[] = [];

export default function DebuggerPage() {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
    
    const [isGraphLoading, setIsGraphLoading] = useState(true);
    const [graphError, setGraphError] = useState<string | null>(null);

    const [query, setQuery] = useState('what is my current langgraph version');
    const [isRunning, setIsRunning] = useState(false);
    const [runError, setRunError] = useState<string | null>(null);
    const streamAbortController = useRef<AbortController | null>(null);

    const [executionLog, setExecutionLog] = useState<string[]>([]);
    const [currentStateMessages, setCurrentStateMessages] = useState<ApiMessage[]>([]);
    const [activeNodeIdDuringRun, setActiveNodeIdDuringRun] = useState<string | null>(null);
    const [selectedNodeForInspectionId, setSelectedNodeForInspectionId] = useState<string | null>(null);
    const [lastToolCall, setLastToolCall] = useState<any>(null);
    const [lastToolResult, setLastToolResult] = useState<any>(null);
    const [finalAnswer, setFinalAnswer] = useState<string>("");
    const [allNodeExecutionDetails, setAllNodeExecutionDetails] = useState<AllNodeExecutionDetails>({});
    const nodeInvocationCounts = useRef<{ [baseNodeId: string]: number }>({});

    const nodesRef = useRef(nodes);
    useEffect(() => { nodesRef.current = nodes; }, [nodes]);
    
    const allNodeExecutionDetailsRef = useRef(allNodeExecutionDetails);
    useEffect(() => { allNodeExecutionDetailsRef.current = allNodeExecutionDetails; }, [allNodeExecutionDetails]);

    const logMessage = useCallback((message: string, type: 'info' | 'error' | 'warn' = 'info') => {
        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const logEntry = `${timestamp}: ${message}`;
        console[type](`[DebuggerPage] ${logEntry}`);
        setExecutionLog(prev => [logEntry, ...prev].slice(0, 150));
    }, []);

    const resetRunState = () => {
        setIsRunning(false); setRunError(null); setExecutionLog([]); 
        setCurrentStateMessages([]); setActiveNodeIdDuringRun(null);
        setLastToolCall(null); setLastToolResult(null); setFinalAnswer("");
        setAllNodeExecutionDetails({}); nodeInvocationCounts.current = {};
        setEdges((eds) => eds.map((e) => ({ ...e, animated: false, style: { ...e.style, stroke: '#aaa', strokeWidth: 1.5 } })));
    };

    const fetchGraphStructure = useCallback(async () => {
        setIsGraphLoading(true); setGraphError(null); logMessage("Fetching graph structure...");
        try {
            const response = await fetch(`${getBaseUrl()}/graph/structure`);
            if (!response.ok) { throw new Error(`Failed to fetch graph structure: ${response.statusText}`); }
            const structure = await response.json(); logMessage("Graph structure received.");
            
            const nodeIconMap: { [key: string]: React.ReactNode } = { 
                agent: <Bot className="w-4 h-4 text-blue-600" />,          // Defined here
                action: <ToolIcon className="w-4 h-4 text-purple-600" />, // Defined here
                __end__: null 
            };
            
            const layoutNodes = (nodesToLayout: any[], edgesToLayout: any[]) => {
                const nodeLevels: {[key: string]: number} = {}; const entryNode = structure.entry_point || 'agent'; 
                const calculateLevels = (nodeId: string, level = 0, visited = new Set<string>()) => { if (visited.has(nodeId) || !nodesToLayout.find(n => n.id === nodeId)) return; visited.add(nodeId); nodeLevels[nodeId] = Math.max(level, nodeLevels[nodeId] || 0); edgesToLayout.filter(e => e.source === nodeId).forEach(e => calculateLevels(e.target, level + 1, visited)); };
                if (nodesToLayout.find(n => n.id === entryNode)) { calculateLevels(entryNode); } else if (nodesToLayout.length > 0) { calculateLevels(nodesToLayout[0].id); }
                const levelGroups: {[key: number]: string[]} = {}; Object.entries(nodeLevels).forEach(([id, level]) => { levelGroups[level] = levelGroups[level] || []; levelGroups[level].push(id); });
                const positions: {[key: string]: {x: number, y: number}} = {}; const levelSpacing = 200; const nodeSpacing = 280; 
                Object.entries(levelGroups).forEach(([levelStr, nodeIdsInLevel]) => { const level = parseInt(levelStr); const y = level * levelSpacing + 100; const numNodesInLevel = nodeIdsInLevel.length; const totalWidthForLevel = (numNodesInLevel - 1) * nodeSpacing; const canvasCenterX = 500; let startX = canvasCenterX - totalWidthForLevel / 2; nodeIdsInLevel.forEach((id, index) => { positions[id] = { x: startX + (index * nodeSpacing), y }; if (id === '__end__') { positions[id].y = y - 30; } }); }); return positions;
            };
            const getNodeHandles = (nodeId: string) => { const isAgent = nodeId === 'agent'; const isAction = nodeId === 'action'; const isEnd = nodeId === '__end__'; 
                if (isAgent) return { sourcePosition: Position.Bottom, targetPosition: Position.Top };       // Position used here
                if (isAction) return { sourcePosition: Position.Right, targetPosition: Position.Left };    // Position used here
                if (isEnd) return { sourcePosition: undefined, targetPosition: Position.Left };            // Position used here
                return { sourcePosition: Position.Bottom, targetPosition: Position.Top };                    // Position used here
            };
            const positions = layoutNodes(structure.nodes, structure.edges);
            const fetchedNodes: Node[] = structure.nodes.map((n: any) => { 
                const { sourcePosition, targetPosition } = getNodeHandles(n.id); 
                const nodeStyle = n.id === '__end__' ? { width: 120, height: 50 } : { width: 180, height: 60 }; 
                return { 
                    id: n.id, 
                    type: n.type, // Pass the type string from backend; GraphCanvas will use its nodeTypes map
                    data: { label: <div className="flex items-center gap-2 font-medium">{nodeIconMap[n.id] || n.label} {n.id !== '__end__' ? n.label : 'END'}</div>, isActive: false, isSelected: false }, 
                    position: positions[n.id] || { x: Math.random() * 400, y: Math.random() * 300 }, 
                    sourcePosition, 
                    targetPosition, 
                    style: nodeStyle 
                }; 
            });
            const fetchedEdges: Edge[] = structure.edges.map((e: any) => ({ id: e.id, source: e.source, target: e.target, label: e.label, type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15 }, style: { strokeWidth: 1.5, stroke: '#888' }, animated: false })); // MarkerType used here
            setNodes(fetchedNodes); setEdges(fetchedEdges); logMessage("Graph layout applied.");
        } catch (error: any) { logMessage(`Error fetching graph structure: ${error.message}`, 'error'); setGraphError(error.message); } finally { setIsGraphLoading(false); }
    }, [logMessage, setNodes, setEdges]); // setNodes, setEdges are stable

    useEffect(() => { fetchGraphStructure(); }, [fetchGraphStructure]);

    useEffect(() => {
        setNodes((prevNodes) =>
            prevNodes.map((node) => {
                const isActiveDuringRun = node.id === activeNodeIdDuringRun;
                const isSelectedForInspection = node.id === (selectedNodeForInspectionId?.split(':')[0] || null);
                if (node.data?.isActive === isActiveDuringRun && node.data?.isSelected === isSelectedForInspection) return node;
                return { ...node, data: { ...node.data, isActive: isActiveDuringRun, isSelected: isSelectedForInspection }};
            })
        );
        setEdges((prevEdges) => prevEdges.map((edge) => {
            const isActiveFlow = edge.source === activeNodeIdDuringRun;
            if (edge.animated === isActiveFlow && edge.style?.stroke === (isActiveFlow ? 'hsl(var(--primary))' : '#aaa')) return edge;
            return { ...edge, animated: isActiveFlow, style: { ...edge.style, strokeWidth: isActiveFlow ? 2.5 : 1.5, stroke: isActiveFlow ? 'hsl(var(--primary))' : '#aaa' }};
        }));
    }, [activeNodeIdDuringRun, selectedNodeForInspectionId, setNodes, setEdges]);


    const stopStreaming = useCallback(() => {
        if (streamAbortController.current) { streamAbortController.current.abort(); streamAbortController.current = null; logMessage("Stream aborted by user.");}
        setIsRunning(false); setActiveNodeIdDuringRun(null);
    }, [logMessage]);

    const handleRunGraph = useCallback(async () => {
        if (isRunning) { stopStreaming(); return; }
        if (!query.trim()) return;

        resetRunState(); 
        setIsRunning(true);
        logMessage(`Starting graph run with query: "${query}"`);
        setSelectedNodeForInspectionId(null);

        const payload: AskPayload = { question: query, chat_history: currentStateMessages };

        try {
            const callbacks: StreamLogCallbacks = {
                onOpen: () => logMessage("SSE stream opened."),
                onLogData: (logData: StreamLogData) => {
                    logMessage(`[FRONTEND_EVENT] Type: ${logData.type}, NodeId: ${logData.nodeId || 'N/A'}`);
                    
                    // ** Corrected baseId definition **
                    let baseId = logData.nodeId || (activeNodeIdDuringRun || '').split(':')[0] || null; 
                    if (!baseId && logData.type === 'token') baseId = "agent";


                    if (logData.type === 'node_start' && logData.nodeId) { // logData.nodeId is guaranteed here
                        baseId = logData.nodeId; // Update baseId since we have a specific nodeId for this event
                        setActiveNodeIdDuringRun(logData.nodeId); 
                        
                        nodeInvocationCounts.current[baseId] = (nodeInvocationCounts.current[baseId] || 0) + 1;
                        const invocationId = nodeInvocationCounts.current[baseId] > 1 ? `${baseId}:${nodeInvocationCounts.current[baseId]}` : baseId;
                        
                        const nodeInfo = nodesRef.current.find(n => n.id === baseId);
                        let inputDetail: any = "Processing...";
                        if (baseId === 'agent') {
                            const agentProcessingTool = agent_is_processing_tool_output_ref.current; // Use ref
                            inputDetail = agentProcessingTool && lastToolResult ? lastToolResult.result : (currentStateMessages.length > 0 ? currentStateMessages : [{ sender: 'user', text: query }]);
                        } else if (baseId === 'action' && lastToolCall) {
                            inputDetail = lastToolCall.args;
                        }
                        setAllNodeExecutionDetails(prev => ({ ...prev, [invocationId]: { input: inputDetail, type: nodeInfo?.type || baseId, status: 'running', name: baseId, output: undefined } as NodeDetail }));
                    }
                    
                    if (logData.type === 'node_output' && baseId && logData.output !== undefined) { // Ensure baseId is valid
                        const count = nodeInvocationCounts.current[baseId] || 1;
                        const invocationId = count > 1 ? `${baseId}:${count}` : baseId;
                        setAllNodeExecutionDetails(prev => ({ ...prev, [invocationId]: { ...(prev[invocationId] || {name:baseId}), output: logData.output, status: 'completed' } }));
                    }
                     if (logData.type === 'node_end' && baseId) { // Ensure baseId is valid
                         const count = nodeInvocationCounts.current[baseId] || 1;
                         const invocationId = count > 1 ? `${baseId}:${count}` : baseId;
                         setAllNodeExecutionDetails(prev => {
                            if (prev[invocationId] && prev[invocationId]?.status === 'running') {
                                return {...prev, [invocationId]: { ...prev[invocationId], status: 'completed'}};
                            }
                            return prev;
                         });
                    }

                    switch (logData.type) {
                        case 'token': 
                            if (logData.token) {
                                setFinalAnswer(prev => prev + logData.token);
                                if (activeNodeIdDuringRun === 'agent' ) { 
                                     const agentInvocId = `agent:${nodeInvocationCounts.current['agent'] || 1}`;
                                     setAllNodeExecutionDetails(prev => ({ ...prev, [agentInvocId]: { ...(prev[agentInvocId] || {name: 'agent'}), output: (prev[agentInvocId]?.output || "") + logData.token, status: 'running' } }));
                                }
                            }
                            break;
                        case 'tool_call': 
                            if (logData.toolCall) { 
                                setLastToolCall(logData.toolCall);
                                setLastToolResult(null); 
                                const agentInvocId = `agent:${nodeInvocationCounts.current['agent'] || 1}`;
                                setAllNodeExecutionDetails(prev => ({ ...prev, [agentInvocId]: { ...(prev[agentInvocId] || {name: 'agent'}), output: logData.toolCall, status: 'completed' } }));
                            } 
                            break;
                        case 'tool_result': 
                            if (logData.toolResult) { 
                                setLastToolResult(logData.toolResult);
                                const actionInvocId = `action:${nodeInvocationCounts.current['action'] || 1}`;
                                setAllNodeExecutionDetails(prev => ({ ...prev, [actionInvocId]: { ...(prev[actionInvocId] || {name: 'action'}), output: logData.toolResult?.result, status: 'completed' } }));
                            } 
                            break;
                        case 'state_update': 
                            if (logData.state?.messages) { setCurrentStateMessages(logData.state.messages); } 
                            break;
                        case 'final_message': logMessage(`Final Message: ${logData.message}`); setFinalAnswer(prev => prev || logData.message || "Processing complete."); break;
                        case 'error': const eDetail = typeof logData.error === 'string' ? logData.error : JSON.stringify(logData.error); logMessage(`ERROR: ${eDetail}`, 'error'); setRunError(eDetail || "Unknown error"); stopStreaming(); break;
                        case 'stream_end': logMessage("Stream end signal received."); break;
                    }
                },
                onError: (error) => { const msg = typeof error === 'string' ? error : (error as any)?.message || "Streaming error."; logMessage(`Stream ERROR: ${msg}`, 'error'); setRunError(msg); stopStreaming(); },
                onComplete: () => { logMessage("Stream completed."); setIsRunning(false); streamAbortController.current = null; setActiveNodeIdDuringRun(null); },
            };
            streamAbortController.current = askQuestionStream(payload, callbacks);
        } catch (error: any) {
             logMessage(`Error initiating stream: ${error.message}`, 'error');
             setRunError(error.message || "Failed to start."); setIsRunning(false);
             if (streamAbortController.current) { streamAbortController.current = null; }
         }
    }, [isRunning, stopStreaming, logMessage, query, currentStateMessages, lastToolCall, lastToolResult]); 
    
    const agent_is_processing_tool_output_ref = useRef(false); 

    const onNodeClick: NodeMouseHandler = useCallback((_, node) => {
        if (isRunning) { logMessage("Graph running. Inspect after completion.", "warn"); return; }
        const baseId = node.id;
        const invocationKeys = Object.keys(allNodeExecutionDetailsRef.current) // Use ref
            .filter(key => key === baseId || key.startsWith(baseId + ":"))
            .sort((a, b) => (parseInt(b.split(':')[1] || '1')) - (parseInt(a.split(':')[1] || '1')) );
        if (invocationKeys.length > 0) {
            logMessage(`Node clicked for inspection: ${baseId} (displaying latest: ${invocationKeys[0]})`);
            setSelectedNodeForInspectionId(invocationKeys[0]); 
        } else {
            logMessage(`Node clicked: ${baseId}, no execution details for specific invocations.`);
            setSelectedNodeForInspectionId(baseId); 
        }
    }, [isRunning, logMessage]);

    return (
        <div className="flex flex-col h-screen max-h-screen bg-muted/30 text-foreground overflow-hidden dark:bg-black">
            <header className="h-16 border-b dark:border-gray-700 flex items-center justify-between px-6 bg-background shadow-sm flex-shrink-0">
                <div className="flex items-center gap-3"> <Waypoints className="w-6 h-6 text-primary" /> <h1 className="font-semibold text-xl">LangGraph Debugger</h1> </div>
                <div className="flex items-center gap-3">
                    {isRunning && (<Badge variant="outline" className="animate-pulse border-primary/50 text-primary dark:border-primary/50 dark:text-primary"><Loader2 className="w-3 h-3 mr-2 animate-spin" /> Running...</Badge>)}
                </div>
            </header>

            <main className="flex flex-1 overflow-hidden">
                <ControlPanel
                    query={query}
                    setQuery={setQuery}
                    isRunning={isRunning}
                    runError={runError}
                    handleRunGraph={handleRunGraph}
                    isGraphLoading={isGraphLoading}
                    executionLog={executionLog}
                />
                <GraphCanvas
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    isGraphLoading={isGraphLoading}
                    graphError={graphError}
                    // activeNodeIdDuringRun prop is removed, GraphCanvas uses node.data.isActive
                    // selectedNodeForInspectionId prop is removed, GraphCanvas uses node.data.isSelected
                    onNodeClick={onNodeClick}
                />
                <DetailsTabs
                    allNodeExecutionDetails={allNodeExecutionDetails}
                    selectedNodeForInspectionId={selectedNodeForInspectionId}
                    nodes={nodes} 
                    currentStateMessages={currentStateMessages}
                    finalAnswer={finalAnswer}
                    isRunning={isRunning}
                    lastToolCall={lastToolCall}
                    lastToolResult={lastToolResult}
                    activeNodeIdDuringRun={activeNodeIdDuringRun}
                />
            </main>
        </div>
    );
}