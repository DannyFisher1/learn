// components/chat/StepsDisplay.tsx
'use client';

import React from 'react';
import { IntermediateStep, AgentAction } from '@/lib/api'; // Import types
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area'; // For scrollable steps
import { Bot, Terminal, Eye, BoxSelect, Info } from 'lucide-react'; // Use Lucide consistently

// Helper type guard (can be shared in a utils file if needed)
function isAgentAction(action: any): action is AgentAction {
    return typeof action === 'object' && action !== null && 'tool' in action && 'tool_input' in action;
}

interface StepsDisplayProps {
    steps: IntermediateStep[] | null; // Array of steps or null if none active
}

export default function StepsDisplay({ steps }: StepsDisplayProps) {

    if (!steps || steps.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground p-4">
                 <Info size={48} className="mb-4 opacity-50" />
                 <p className="text-sm">Select an AI message <Terminal size={14} className="inline align-text-bottom mx-0.5" /> in the chat</p>
                 <p className="text-sm mt-1">to view the detailed agent steps here.</p>
            </div>
        );
    }

    return (
        <ScrollArea className="h-full"> {/* Make the whole area scrollable if steps overflow */}
             <div className="space-y-4 p-1"> {/* Add some padding */}
                 {steps.map((step, idx) => (
                    <Card key={`step-${idx}`} className="bg-muted/50 shadow-sm">
                         <CardHeader className="p-2 pb-1">
                            <CardTitle className="text-xs font-medium text-muted-foreground flex items-center">
                                <Terminal size={12} className="mr-1.5" />
                                Step {idx + 1}
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="p-2 pt-1 text-xs space-y-2">
                             {/* Display Action (Tool Usage) */}
                             {isAgentAction(step.action) ? (
                                <div className="border-l-2 border-blue-400 pl-2 py-1">
                                    <div className="flex items-center gap-1 font-medium text-foreground/90 mb-1">
                                         <BoxSelect size={14} className="flex-shrink-0" /> Action: Use Tool
                                    </div>
                                    <Badge variant="outline" className="my-0.5 text-[10px] h-auto py-0.5 px-1.5 bg-background">
                                        {step.action.tool || 'Unknown Tool'}
                                    </Badge>
                                    <div className="mt-1 font-mono bg-background p-1.5 rounded text-muted-foreground text-[11px] overflow-x-auto whitespace-pre-wrap break-all">
                                         <span className="font-semibold text-foreground/70">Input:</span> {typeof step.action.tool_input === 'string'
                                            ? step.action.tool_input
                                            : JSON.stringify(step.action.tool_input, null, 2)}
                                    </div>
                                </div>
                             ) : (
                                 // Render if action is just a string (less common now but fallback)
                                  <p><span className="font-medium">Action:</span> {String(step.action)}</p>
                             )}

                            {/* Display Observation (Tool Result) */}
                            <div className="border-l-2 border-green-400 pl-2 py-1">
                                 <div className="flex items-center gap-1 font-medium text-foreground/90 mb-1">
                                     <Eye size={14} className="flex-shrink-0" /> Observation:
                                 </div>
                                 {/* Tool Output */}
                                 <div className="mt-0.5 text-muted-foreground bg-background p-1.5 rounded text-[11px] overflow-x-auto whitespace-pre-wrap break-all">
                                    {step.observation === '⏳ Processing...' ? (
                                        <span className="italic text-foreground/70">{step.observation}</span>
                                    ) : (
                                        // Attempt to format JSON if observation is a string that looks like JSON
                                        // Basic check - might need refinement
                                        (typeof step.observation === 'string' && step.observation.trim().startsWith('{') && step.observation.trim().endsWith('}'))
                                        ? (<pre><code>{JSON.stringify(JSON.parse(step.observation), null, 2)}</code></pre>)
                                        : (typeof step.observation === 'object'
                                           ? (<pre><code>{JSON.stringify(step.observation, null, 2)}</code></pre>)
                                           : String(step.observation)) // Fallback to string
                                    )
                                    }
                                 </div>
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>
        </ScrollArea>
    );
}