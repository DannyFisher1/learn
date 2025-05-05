// components/chat/MessageBlock.tsx
'use client';

import React, { useState } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { Message as ApiMessage } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Bot, User, FileTextIcon, LinkIcon, ClipboardCopy, Check } from 'lucide-react'; // Removed Terminal
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

// --- Updated Props Interface ---
// Removed isActiveContext and onShowContext
interface MessageBlockProps {
    message: ApiMessage;
    isStreaming?: boolean;
}
// --------------------

// Custom Renderers for Markdown (Code block with copy, links, etc. remain the same)
const markdownComponents: Partial<Components> = {
    code({ node, inline, className, children, ...props }: any) {
        const [isCopied, setIsCopied] = useState(false);
        const codeString = String(children).replace(/\n$/, '');
        const match = /language-(\w+)/.exec(className || '');
        const language = match ? match[1] : 'text';

        const handleCopy = () => {
            navigator.clipboard.writeText(codeString).then(() => {
                setIsCopied(true);
                toast.success("Code copied!");
                setTimeout(() => setIsCopied(false), 2000);
            }).catch(err => {
                toast.error("Failed to copy code.");
            });
        };

        return !inline ? (
            <div className="relative my-4 group code-block-container bg-[#1E1E1E] rounded-md border border-gray-700/50 shadow-md">
                 <div className="flex items-center justify-between px-3 py-1 border-b border-gray-700/50">
                    <span className="text-gray-400 text-[10px] font-mono uppercase select-none">{language}</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6 text-gray-400 hover:text-gray-100 hover:bg-gray-700/50" onClick={handleCopy} aria-label="Copy code">
                        {isCopied ? <Check size={14} className="text-green-500" /> : <ClipboardCopy size={14} />}
                    </Button>
                </div>
                <SyntaxHighlighter
                    style={vscDarkPlus as any} language={language} PreTag="div"
                    className="!p-3 text-[13px] font-mono overflow-x-auto scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-transparent"
                    showLineNumbers={false} wrapLongLines={false} {...props}>
                    {codeString}
                </SyntaxHighlighter>
            </div>
        ) : (
            <code className={cn("inline-code rounded bg-muted/80 dark:bg-muted/30 px-[0.4em] py-[0.2em] font-mono text-sm", className)} {...props}>{children}</code>
        );
    },
    a({ node, children, ...props }) {
        const href = props.href && typeof props.href === 'string' ? props.href : '#';
        return ( <a {...props} href={href} target="_blank" rel="noopener noreferrer" className="text-primary font-medium underline decoration-primary/60 decoration-1 underline-offset-2 transition-all hover:decoration-primary hover:decoration-solid hover:brightness-110">{children}</a> );
    },
    h1({node, ...props}) { return <h1 className="text-xl font-semibold mt-5 mb-2 border-b pb-1" {...props} />; },
    h2({node, ...props}) { return <h2 className="text-lg font-semibold mt-4 mb-1.5" {...props} />; },
    h3({node, ...props}) { return <h3 className="text-base font-semibold mt-4 mb-1" {...props} />; },
    ul({node, ...props}) { return <ul className="list-disc pl-6 my-2 space-y-1.5" {...props} />; },
    ol({node, ...props}) { return <ol className="list-decimal pl-6 my-2 space-y-1.5" {...props} />; },
    blockquote({node, ...props}) { return <blockquote className="border-l-4 border-border pl-4 italic my-3 text-muted-foreground" {...props} />; },
    p({node, ...props}) { return <p className="my-2 leading-relaxed" {...props} />; },
};

// --- Main MessageBlock Component ---
export default function MessageBlock({
    message,
    isStreaming,
    // isActiveContext, // <-- Removed
    // onShowContext    // <-- Removed
}: MessageBlockProps) {

    const isUser = message.sender === 'user';
    const hasSources = !isUser && message.sources && message.sources.length > 0;
    // Keep hasIntermediateSteps check if needed for other subtle UI cues, otherwise remove
    // const hasIntermediateSteps = !isUser && message.intermediate_steps && message.intermediate_steps.length > 0;

    // Removed handleShowContextClick handler

    return (
        <div className={cn("flex flex-col w-full")}>
            {isUser && (
                <div className="flex items-start gap-3 mb-3">
                    <div className="flex-shrink-0 w-7 h-7 rounded-full bg-accent text-accent-foreground items-center justify-center flex self-start">
                        <User className="w-4 h-4" />
                    </div>
                    <div className="flex-grow min-w-0 mt-1">
                        <p className="text-[15px] text-foreground whitespace-pre-wrap break-words">
                            {message.text}
                        </p>
                    </div>
                </div>
            )}

            {/* --- AI Response Block --- */}
            {!isUser && (
                <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 text-primary items-center justify-center flex self-start">
                        <Bot className="w-4 h-4" />
                    </div>
                    {/* AI content block - Removed hover/cursor/active styles/onClick */}
                    <div className={cn("flex-grow min-w-0 rounded-md bg-transparent")}>
                        {/* Removed floating Terminal icon */}

                        {/* Main AI Text Output */}
                        <div className={cn(
                            "prose prose-sm dark:prose-invert max-w-none",
                            "prose-p:my-2 prose-ul:my-3 prose-ol:my-3 prose-li:my-1 prose-li:marker:text-muted-foreground",
                            "prose-headings:mt-4 prose-headings:mb-2 prose-blockquote:my-3",
                            "prose-pre:my-0 prose-pre:p-0 prose-pre:bg-transparent",
                            "prose-code:bg-muted/80 prose-code:dark:bg-muted/30 prose-code:px-[0.4em] prose-code:py-[0.2em] prose-code:rounded prose-code:font-mono prose-code:text-sm",
                            "prose-a:font-medium",
                            "text-foreground"
                        )}>
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm, remarkMath]}
                                rehypePlugins={[rehypeKatex]}
                                components={markdownComponents}
                            >
                                {`${message.text || (isStreaming ? '' : 'Thinking...')}${isStreaming ? '█' : ''}`}
                            </ReactMarkdown>
                        </div>

                        {/* Source Documents Accordion (Kept) */}
                        {hasSources && (
                            <div className="mt-4 pt-3 border-t border-border/30">
                                <Accordion type="single" collapsible className="w-full">
                                    <AccordionItem value="sources" className="border-b-0">
                                        <AccordionTrigger className="text-xs py-1 hover:no-underline text-muted-foreground data-[state=open]:text-foreground font-medium hover:bg-muted/50 rounded px-2">
                                             <FileTextIcon className="w-3.5 h-3.5 mr-1.5 flex-shrink-0"/>
                                            Source Document(s) ({message.sources?.length})
                                        </AccordionTrigger>
                                        <AccordionContent className="pt-2 pb-0 text-xs pl-4 pr-2">
                                            <ul className="list-none space-y-1.5">
                                                {message.sources?.map((source, idx) => (
                                                    <li key={`source-${idx}`} className="text-muted-foreground break-words">
                                                        <span className="font-semibold text-foreground/80">{source.source || 'Unknown Source'}</span>
                                                        {source.page !== 'N/A' ? `, Page ${source.page}` : ''}
                                                    </li>
                                                ))}
                                            </ul>
                                        </AccordionContent>
                                    </AccordionItem>
                                </Accordion>
                            </div>
                        )}
                    </div> {/* End AI Content Block */}
                </div> // End AI Response Container
            )}
        </div> // End Main Turn Container
    );
}