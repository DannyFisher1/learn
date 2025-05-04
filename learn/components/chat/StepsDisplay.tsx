// components/chat/StepsDisplay.tsx
'use client';

import React from 'react';
import { IntermediateStep, AgentAction } from '@/lib/api'; // Import types
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from "@/components/ui/scroll-area"; 
import { Terminal, Eye, BoxSelect, Info } from 'lucide-react'; // Use Lucide consistently
import ObservationDisplay from './ObservationDisplay'; // <-- Import ObservationDisplay

// Helper type guard (keep for local use or move to shared utils)
function isAgentAction(action: any): action is AgentAction {
    // Basic check for expected keys
    return typeof action === 'object' && action !== null && 'tool' in action && 'tool_input' in action;
    // Note: 'log' might not always be present depending on agent setup, so check is optional
}

interface StepsDisplayProps {
    steps: IntermediateStep[] | null; // Array of steps or null if none active
}

export default function StepsDisplay({ steps }: StepsDisplayProps) {
    // --- ADD LOGGING ---
    console.log("[StepsDisplay] Received steps prop:", steps);
    // -------------------

    // Display placeholder/instructions if no steps are provided (or if RAG context is active)
    if (!steps || steps.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground p-6"> {/* Increased padding */}
                 <Info size={40} className="mb-4 opacity-40" /> {/* Slightly smaller icon */}
                 <p className="text-sm font-medium text-foreground/90">Context Pane</p>
                 <p className="text-xs mt-1">Select an AI message <Terminal size={12} className="inline align-baseline mx-0.5" /> in the chat</p>
                 <p className="text-xs mt-1">to view detailed agent steps, or</p>
                 <p className="text-xs mt-1">see retrieved document context here during RAG queries.</p>
            </div>
        );
    }

    // Render the list of steps if steps array is provided and not empty
    return (
        // Use ScrollArea for the entire content if it overflows
        <ScrollArea className="h-full w-full">
             {/* Add padding to the container within the scroll area */}
             <div className="space-y-3 p-4">
                 <h3 className="text-sm font-semibold text-muted-foreground sticky top-0 bg-card pb-2 pt-0 border-b mb-2"> {/* Sticky header */}
                    Agent Steps ({steps.length})
                 </h3>
                 {steps.map((step, idx) => {
                    // Extract tool name safely, ensuring it's string or null
                    const action = step.action;
                    const toolName = isAgentAction(action) ? (action.tool || null) : null;

                    return (
                        // Card for each step for visual grouping
                        <Card key={`step-${idx}`} className="bg-muted/50 shadow-sm overflow-hidden"> {/* Added overflow-hidden */}
                            {/* Use CardHeader for step number, less padding */}
                            <CardHeader className="p-2 pb-1 border-b bg-muted/70">
                                <CardTitle className="text-xs font-medium text-muted-foreground flex items-center">
                                    <Terminal size={12} className="mr-1.5 flex-shrink-0" />
                                    Step {idx + 1}
                                </CardTitle>
                            </CardHeader>
                            {/* Use CardContent for action/observation details */}
                            <CardContent className="p-2 text-xs space-y-2">
                                 {/* Action Block */}
                                 {isAgentAction(step.action) ? (
                                    <div className="border-l-2 border-blue-400 pl-2.5 py-1 space-y-1"> {/* Adjusted padding/spacing */}
                                        <div className="flex items-center gap-1 font-semibold text-foreground/95"> {/* Increased contrast */}
                                             <BoxSelect size={13} className="flex-shrink-0" /> Action: Use Tool
                                        </div>
                                        <Badge variant="outline" className="text-[10px] font-mono h-auto py-0.5 px-1.5 bg-background shadow-sm">
                                            {step.action.tool || 'Unknown Tool'}
                                        </Badge>
                                        {/* Input Block - use pre-wrap */}
                                        <div className="mt-1 font-mono bg-background p-2 rounded text-muted-foreground text-[11px] overflow-x-auto whitespace-pre-wrap break-words border">
                                             <span className="font-semibold text-foreground/75 block mb-0.5">Input:</span>
                                             {typeof step.action.tool_input === 'string'
                                                ? step.action.tool_input
                                                : JSON.stringify(step.action.tool_input, null, 2)}
                                        </div>
                                    </div>
                                 ) : (
                                     // Fallback if action is not a standard AgentAction object
                                     <div className="border-l-2 border-gray-400 pl-2.5 py-1">
                                         <p><span className="font-semibold text-foreground/95">Action:</span> {String(step.action)}</p>
                                     </div>
                                 )}

                                {/* Observation Block */}
                                <div className="border-l-2 border-green-400 pl-2.5 py-1 space-y-1"> {/* Adjusted padding/spacing */}
                                     <div className="flex items-center gap-1 font-semibold text-foreground/95"> {/* Increased contrast */}
                                         <Eye size={13} className="flex-shrink-0" /> Observation:
                                     </div>
                                     {/* Observation Content - Now uses ObservationDisplay */}
                                     <div className="mt-0.5 text-muted-foreground bg-background p-1 rounded text-[11px] overflow-x-auto border"> {/* Adjusted padding */}
                                        {step.observation === '⏳ Processing...' ? (
                                            <span className="italic text-foreground/70">{step.observation}</span>
                                        ) : (
                                            <ObservationDisplay observation={step.observation} toolName={toolName} /> // <-- Use ObservationDisplay
                                        )
                                        }
                                     </div>
                                </div>
                            </CardContent>
                        </Card>
                    );
                })}
            </div>
        </ScrollArea>
    );
}