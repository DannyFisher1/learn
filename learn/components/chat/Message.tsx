// components/chat/Message.tsx
'use client';

import React from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism'; // Code block theme
// Import types, including IntermediateStep, from your API definition file
import { Message as ApiMessage, IntermediateStep } from '@/lib/api'; // Corrected path
import { cn } from '@/lib/utils'; // Class merging utility
import { Bot, User, Terminal, Eye, BoxSelect } from 'lucide-react'; // Icons
// Ensure KaTeX CSS is imported GLOBALLY (e.g., in layout.tsx or globals.css)
// import 'katex/dist/katex.min.css'; // <-- DO NOT import here, import globally

import { // shadcn components
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from '@/components/ui/badge'; // For Tool Name

// Props expected by the Message component
interface MessageProps {
    message: ApiMessage;
    isStreaming?: boolean; // Add optional prop to indicate if this message is actively streaming
}

// Helper type guard to check if an action object has the expected structure
function isAgentAction(action: any): action is { tool: string; tool_input: any; log: string } {
    // Check for null explicitly as typeof null is 'object'
    return typeof action === 'object' && action !== null && 'tool' in action && 'tool_input' in action && 'log' in action;
}

// Custom code block renderer for react-markdown using react-syntax-highlighter
const markdownComponents: Partial<Components> = {
  code({ node, inline, className, children, ...props }: any) {
    const match = /language-(\w+)/.exec(className || '');
    // Render block code with syntax highlighting
    return !inline && match ? (
      <SyntaxHighlighter
        style={oneDark as any} // Using 'as any' to bypass potential style type mismatches
        language={match[1]} // Detected language
        PreTag="div" // Use div instead of pre for better styling control
        className="code-block !bg-gray-800/80 dark:!bg-gray-900/80 rounded my-2 text-[13px] leading-relaxed" // Custom class and styling
        showLineNumbers={false} // Optional: show line numbers
        wrapLongLines={true} // Wrap long lines instead of horizontal scroll
        {...props}
      >
        {String(children).replace(/\n$/, '')}
      </SyntaxHighlighter>
    ) : (
      // Render inline code with specific styling
      <code className={cn("inline-code rounded bg-muted px-[0.4rem] py-[0.2rem] font-mono text-sm", className)} {...props}>
        {children}
      </code>
    );
  },
};

// The main Message component
export default function Message({ message, isStreaming }: MessageProps) {
    // Determine sender type
    const isUser = message.sender === 'user';
    // Check for presence of source documents
    const hasSources = !isUser && message.sources && message.sources.length > 0;
    // Check for presence of intermediate agent steps
    const hasIntermediateSteps = !isUser && message.intermediate_steps && message.intermediate_steps.length > 0;

    return (
        // Main container for the message row
        <div className={cn(
            "flex items-start gap-3 w-full", // Flex layout with spacing
            isUser ? "justify-end pl-8 sm:pl-12 md:pl-16" : "justify-start pr-8 sm:pr-12 md:pr-16" // Alignment and padding
        )}>
            {/* Icon Column for AI */}
            {!isUser && (
                 <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 text-primary items-center justify-center flex mt-1 self-start">
                    <Bot className="w-5 h-5" />
                </div>
            )}

            {/* Message Content Column */}
            <div className={cn(
                "max-w-[80%] sm:max-w-[75%]", // Constrain message width
                isUser ? "order-1" : "order-2" // Ensure correct visual order with icons
            )}>
                {/* Message Bubble using Card */}
                <Card className={cn(
                    "rounded-xl shadow-sm", // Styling for the bubble
                    isUser ? "bg-primary text-primary-foreground" : "bg-card border" // Different colors for user/AI
                )}>
                    <CardContent className="px-3 py-2 text-sm break-words"> {/* Padding */}

                        {/* Main Message Text Area */}
                        <div className={cn(
                             "prose prose-sm dark:prose-invert max-w-none", // Base prose styling
                             // Fine-tune prose styles
                             "prose-p:my-1 prose-ul:my-2 prose-li:my-0.5",
                             "prose-headings:my-2 prose-blockquote:my-2 prose-pre:my-0 prose-pre:bg-transparent prose-pre:p-0",
                             "prose-code:font-normal prose-code:before:content-none prose-code:after:content-none", // Reset prose code defaults for inline code
                             // Link colors based on sender
                             isUser ? "text-primary-foreground prose-a:text-primary-foreground/90 hover:prose-a:text-primary-foreground"
                                    : "text-card-foreground prose-a:text-primary hover:prose-a:underline"
                        )}>
                            {isUser ? (
                                // User message: Render plain text respecting whitespace/newlines
                                <p className="whitespace-pre-wrap my-0">{message.text}</p>
                            ) : (
                                // AI message: Render using ReactMarkdown with plugins
                                <ReactMarkdown
                                    remarkPlugins={[remarkGfm, remarkMath]} // Enable GFM features and math parsing
                                    rehypePlugins={[rehypeKatex]} // Render math using KaTeX
                                    components={markdownComponents} // Use custom code renderer
                                >
                                    {/* Render the message text (which will be updated by streaming) */}
                                    {/* Add blinking cursor if streaming and text is potentially incomplete */}
                                    {`${message.text || (hasIntermediateSteps ? "" : "...")}${isStreaming ? '█' : ''}`}
                                    {/* Simple cursor for now, can replace with blinking span if preferred */}
                                </ReactMarkdown>
                            )}
                        </div>

                        {/* Intermediate Steps Accordion (Conditional) */}
                        {hasIntermediateSteps && (
                            <div className="mt-2 pt-2 border-t border-border/50"> {/* Separator */}
                                <Accordion type="single" collapsible className="w-full" defaultValue={ isUser ? undefined : "steps" }> {/* Optionally open by default for AI */}
                                    <AccordionItem value="steps" className="border-b-0"> {/* No bottom border */}
                                        <AccordionTrigger className="text-xs py-1 hover:no-underline text-muted-foreground data-[state=open]:text-foreground">
                                            <Terminal className="w-3 h-3 mr-1.5"/> {/* Icon */}
                                            Agent Steps ({message.intermediate_steps?.length})
                                        </AccordionTrigger>
                                        <AccordionContent className="pt-1 pb-0">
                                            {/* Scrollable container for steps */}
                                            <div className="space-y-3 pl-2 max-h-60 overflow-y-auto pr-1">
                                                {message.intermediate_steps?.map((step: IntermediateStep, idx: number) => (
                                                    <div key={`step-${idx}`} className="text-xs border-l-2 border-primary/30 pl-2 space-y-1">
                                                        {/* Display Action (Tool Usage) with Type Guard */}
                                                        {isAgentAction(step.action) ? (
                                                            // --- Render when step.action is an AgentAction object ---
                                                            <div>
                                                                <div className="flex items-center gap-1 font-medium text-foreground/90 mb-0.5">
                                                                     <BoxSelect className="w-3 h-3 flex-shrink-0" /> Action: Use Tool
                                                                </div>
                                                                <Badge variant="secondary" className="my-0.5 text-[10px] h-auto py-0.5">{step.action.tool}</Badge>
                                                                <div className="font-mono bg-muted p-1.5 rounded text-muted-foreground text-[11px] overflow-x-auto whitespace-pre-wrap break-all mt-1">
                                                                    {/* Accessing step.action.tool_input is now safe */}
                                                                    Input: {typeof step.action.tool_input === 'string' ? step.action.tool_input : JSON.stringify(step.action.tool_input, null, 2)}
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            // --- Render when step.action is just a string ---
                                                             <p><span className="font-medium">Action:</span> {String(step.action)}</p>
                                                        )}

                                                        {/* Display Observation (Tool Result) */}
                                                        <div>
                                                             <div className="flex items-center gap-1 font-medium text-foreground/90 mt-1.5 mb-0.5">
                                                                 <Eye className="w-3 h-3 flex-shrink-0" /> Observation:
                                                             </div>
                                                             {/* Tool Output (Formatted JSON if object) */}
                                                             <div className="mt-0.5 text-muted-foreground bg-muted/50 p-1.5 rounded text-[11px] overflow-x-auto whitespace-pre-wrap break-all">
                                                                {step.observation === '⏳ Processing...' ? ( // Show loading indicator
                                                                    <span className="italic">{step.observation}</span>
                                                                ) : (
                                                                    typeof step.observation === 'object' ? JSON.stringify(step.observation, null, 2) : String(step.observation)
                                                                )
                                                                }
                                                             </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </AccordionContent>
                                    </AccordionItem>
                                </Accordion>
                            </div>
                        )}
                        {/* End Intermediate Steps */}


                        {/* Source Documents Accordion (Conditional) */}
                        {hasSources && (
                            // Adjust top margin/padding if steps are also present
                            <div className={cn( hasIntermediateSteps ? "mt-1 pt-1 border-t border-border/50" : "mt-2 pt-2 border-t border-border/50" )}>
                                <Accordion type="single" collapsible className="w-full">
                                    <AccordionItem value="sources" className="border-b-0">
                                        <AccordionTrigger className="text-xs py-1 hover:no-underline text-muted-foreground data-[state=open]:text-foreground">
                                            {message.sources?.length} Source Document{message.sources?.length !== 1 ? 's' : ''}
                                        </AccordionTrigger>
                                        <AccordionContent className="pt-1 pb-0">
                                            {/* List of sources */}
                                            <ul className="list-none space-y-1 pl-2">
                                                {message.sources?.map((source: { source?: string | null; page?: number | string | null }, idx: number) => ( // Added types
                                                    <li key={`source-${idx}`} className="text-xs text-muted-foreground break-all">
                                                        <span className="inline-block mr-1 align-middle">
                                                          <span className="font-medium text-foreground/80">{source.source || 'Unknown Source'}</span>
                                                           {source.page !== 'N/A' ? `, Page ${source.page}` : ''}
                                                        </span>
                                                    </li>
                                                ))}
                                            </ul>
                                        </AccordionContent>
                                    </AccordionItem>
                                </Accordion>
                            </div>
                        )}
                        {/* End Source Documents */}

                    </CardContent>
                </Card>
            </div>

             {/* Icon Column for User */}
             {isUser && (
                 <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent text-accent-foreground items-center justify-center flex mt-1 self-start order-2">
                    <User className="w-5 h-5" />
                </div>
            )}
        </div>
    );
}