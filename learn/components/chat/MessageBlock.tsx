// components/chat/MessageBlock.tsx (Renamed from Message.tsx)
'use client';

import React from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
// Choose a theme for code blocks - `vscDarkPlus` is another good option
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { Message as ApiMessage } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Bot, User, Terminal, FileTextIcon, LinkIcon } from 'lucide-react'; // Added LinkIcon
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";
import { Separator } from '@/components/ui/separator'; // For visual separation

// --- Updated Props Interface ---
interface MessageBlockProps { // Renamed interface
    message: ApiMessage;
    isStreaming?: boolean;
    isActiveContext?: boolean;
    onShowContext?: (messageId: string | null) => void;
}
// --------------------

// --- Custom Renderers for Markdown ---
// Enhance link rendering and adjust code block styling
const markdownComponents: Partial<Components> = {
    // Code blocks - adjust background, padding, font size
    code({ node, inline, className, children, ...props }: any) {
        const match = /language-(\w+)/.exec(className || '');
        return !inline && match ? (
            <div className="relative my-3"> {/* Container for potential copy button */}
                <SyntaxHighlighter
                    style={vscDarkPlus as any} // Using a different theme example
                    language={match[1]}
                    PreTag="div"
                     // More subtle background, increased padding, slightly smaller font
                    className="!bg-muted/50 dark:!bg-black/30 rounded p-3 text-[13px] leading-relaxed overflow-x-auto"
                    showLineNumbers={false}
                    wrapLongLines={true}
                    {...props}
                >
                    {String(children).replace(/\n$/, '')}
                </SyntaxHighlighter>
                 {/* TODO: Add a copy button here later */}
            </div>
        ) : (
             // Inline code styling remains similar
            <code className={cn("inline-code rounded bg-muted px-[0.4rem] py-[0.2rem] font-mono text-sm", className)} {...props}>
                {children}
            </code>
        );
    },
    // Links - make them more distinct
    a({ node, children, ...props }) {
        return (
            <a
                {...props}
                target="_blank" // Open external links in new tab
                rel="noopener noreferrer" // Security measure
                className="text-primary underline decoration-primary/50 decoration-dotted underline-offset-2 hover:decoration-solid hover:brightness-110 transition-all"
            >
                 <LinkIcon size={12} className="inline-block mr-0.5 align-text-bottom text-primary/80" />
                 {children}
            </a>
        );
    },
     // Headings - reduce margins
    h1({node, ...props}) { return <h1 className="text-xl font-semibold mt-4 mb-2" {...props} />; },
    h2({node, ...props}) { return <h2 className="text-lg font-semibold mt-3 mb-1.5" {...props} />; },
    h3({node, ...props}) { return <h3 className="text-base font-semibold mt-3 mb-1" {...props} />; },
    // Add more heading levels if needed (h4, h5, h6)

    // Lists - adjust spacing
    ul({node, ...props}) { return <ul className="list-disc pl-5 my-2 space-y-1" {...props} />; },
    ol({node, ...props}) { return <ol className="list-decimal pl-5 my-2 space-y-1" {...props} />; },

    // Blockquotes - style differently
     blockquote({node, ...props}) {
        return <blockquote className="border-l-4 border-border pl-3 italic my-2 text-muted-foreground" {...props} />;
    },
    // Paragraphs - default spacing
    p({node, ...props}) { return <p className="my-1.5" {...props} />; },
};
// -------------------------------------

// The main MessageBlock component
export default function MessageBlock({ // Renamed component
    message,
    isStreaming,
    isActiveContext,
    onShowContext
}: MessageBlockProps) {

    const isUser = message.sender === 'user';
    const hasSources = !isUser && message.sources && message.sources.length > 0;
    const hasIntermediateSteps = !isUser && message.intermediate_steps && message.intermediate_steps.length > 0;

    const handleShowContextClick = () => {
        if (!isUser && hasIntermediateSteps && onShowContext) {
            onShowContext(isActiveContext ? null : message.id ?? null);
        }
        // Clear context if user message clicked? Optional.
        // else if (isUser && onShowContext) { onShowContext(null); }
    };

    return (
        // Use a simple div, no Card/bubble. Add padding/margin as needed by parent's space-y
        <div
            className={cn(
                "flex flex-col w-full",
                // Add slight visual distinction for AI messages if desired, e.g., background
                // !isUser && "bg-card rounded-lg p-3" // Example: Subtle background for AI block
            )}
            // Use onClick only on the AI part if desired for context clicking
            // onClick={handleShowContextClick} // Apply click handler based on need
        >
            {/* --- User Query Display --- */}
            {isUser && (
                <div className="flex items-start gap-3 mb-2"> {/* Spacing below user query */}
                    <div className="flex-shrink-0 w-7 h-7 rounded-full bg-accent text-accent-foreground items-center justify-center flex mt-0.5 self-start">
                        <User className="w-4 h-4" />
                    </div>
                    {/* Take full width available */}
                    <div className="flex-grow min-w-0">
                        {/* User text - styled more like normal document text */}
                        <p className="text-base text-foreground whitespace-pre-wrap break-words font-medium">
                            {message.text}
                        </p>
                    </div>
                </div>
            )}

            {/* --- AI Response Block --- */}
            {!isUser && (
                <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 text-primary items-center justify-center flex mt-0.5 self-start">
                        <Bot className="w-4 h-4" />
                    </div>
                    {/* AI content takes full width */}
                    <div className={cn(
                        "flex-grow min-w-0 border rounded-md p-3", // Add border and padding to AI block
                        isActiveContext ? "border-primary/50 bg-primary/5" : "border-transparent bg-card/50", // Highlight if active
                        hasIntermediateSteps && onShowContext && "cursor-pointer hover:border-primary/30" // Clickable indicator
                        )}
                         onClick={handleShowContextClick} // Click handler on the AI block
                    >
                        {/* Clickable Indicator */}
                        {hasIntermediateSteps && !isUser && (
                            <Terminal
                                className="float-right ml-2 mb-1 w-3.5 h-3.5 text-muted-foreground/60 hover:text-primary"
                                aria-label="Show agent steps"
                             />
                        )}

                        {/* Main AI Text Output */}
                         {/* Apply prose styles directly here for markdown content */}
                        <div className={cn(
                            "prose prose-sm dark:prose-invert max-w-none", // Base prose
                             // Adjust prose styles for better spacing in this layout
                             "prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-1",
                             "prose-headings:mt-4 prose-headings:mb-2 prose-blockquote:my-2",
                             "prose-pre:my-0 prose-pre:p-0 prose-pre:bg-transparent", // Reset pre for syntax highlighter
                             "prose-code:font-normal prose-code:before:content-none prose-code:after:content-none", // Reset inline code
                             "prose-a:font-medium", // Style links within prose
                             "text-foreground" // Ensure default text color
                        )}>
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm, remarkMath]}
                                rehypePlugins={[rehypeKatex]}
                                components={markdownComponents} // Use custom renderers
                            >
                                 {/* Handle empty text state during streaming */}
                                {`${message.text || (isStreaming ? '' : '...')}${isStreaming ? '█' : ''}`}
                            </ReactMarkdown>
                        </div>

                        {/* Source Documents Accordion (kept, styling adjusted) */}
                        {hasSources && (
                            <div className="mt-4 pt-3 border-t border-border/50"> {/* More top margin */}
                                <Accordion type="single" collapsible className="w-full">
                                    <AccordionItem value="sources" className="border-b-0">
                                        <AccordionTrigger className="text-xs py-1 hover:no-underline text-muted-foreground data-[state=open]:text-foreground font-medium">
                                            <FileTextIcon className="w-3.5 h-3.5 mr-1.5 flex-shrink-0"/>
                                            Source Document(s) ({message.sources?.length})
                                        </AccordionTrigger>
                                        <AccordionContent className="pt-1 pb-0 text-xs">
                                            <ul className="list-none space-y-1.5 pl-2">
                                                {message.sources?.map((source, idx) => (
                                                    <li key={`source-${idx}`} className="text-muted-foreground break-words">
                                                        <span className="font-medium text-foreground/80">{source.source || 'Unknown Source'}</span>
                                                        {source.page !== 'N/A' ? `, Page ${source.page}` : ''}
                                                    </li>
                                                ))}
                                            </ul>
                                        </AccordionContent>
                                    </AccordionItem>
                                </Accordion>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}