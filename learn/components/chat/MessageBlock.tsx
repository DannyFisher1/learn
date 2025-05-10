// components/chat/MessageBlock.tsx
'use client';

import React, { useState } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { Message as ApiMessage, Source, RagSource, RagContextDocument } from '@/lib/api';
import { cn } from '@/lib/utils';
import {
    Bot, User, FileTextIcon, LinkIcon, ClipboardCopy, Check, AlertTriangle,
    Info, Search, Loader2, FileDown, MessageSquarePlus, ClipboardCheck, CheckCircle2, BookCopy, ExternalLink
} from 'lucide-react';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

interface MessageBlockProps {
    message: ApiMessage;
    isAsking?: boolean; // General app asking state
}

// --- Custom Renderers for Markdown ---
const markdownComponents: Partial<Components> = {
    code({ node, inline, className, children, ...props }: any) {
        const [isCopied, setIsCopied] = useState(false);
        const codeString = String(children).replace(/\n$/, '');
        const match = /language-(\w+)/.exec(className || '');
        const language = match ? match[1] : 'text';
        const handleCopy = () => { navigator.clipboard.writeText(codeString).then(() => { setIsCopied(true); toast.success("Code copied!"); setTimeout(() => setIsCopied(false), 2000); }).catch(err => { toast.error("Failed to copy code."); console.error("Copy failed:", err); }); };
        return !inline ? ( <div className="relative my-4 group code-block-container bg-[#1E1E1E] rounded-md border border-border/30 shadow-sm"> <div className="flex items-center justify-between px-3 py-1 border-b border-border/50"> <span className="text-gray-400 text-[10px] font-mono uppercase select-none">{language}</span> <Button variant="ghost" size="icon" className="h-6 w-6 text-gray-400 hover:text-gray-100 hover:bg-gray-700/50" onClick={handleCopy} aria-label="Copy code"> {isCopied ? <Check size={14} className="text-green-500" /> : <ClipboardCopy size={14} />} </Button> </div> <SyntaxHighlighter style={vscDarkPlus as any} language={language} PreTag="div" className="!p-3 !mb-0 text-[13px] font-mono overflow-x-auto scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-transparent" showLineNumbers={false} wrapLongLines={false} {...props}> {codeString} </SyntaxHighlighter> </div> ) : ( <code className={cn("inline-code rounded bg-muted/80 dark:bg-muted/30 px-[0.4em] py-[0.2em] font-mono text-sm break-words", className)} {...props}>{children}</code> ); },
    a({ node, children, ...props }) { const href = props.href && typeof props.href === 'string' ? props.href : '#'; return ( <a {...props} href={href} target="_blank" rel="noopener noreferrer" className="text-primary font-medium underline decoration-primary/60 decoration-1 underline-offset-2 transition-all hover:decoration-primary hover:decoration-solid hover:brightness-110">{children}</a> ); },
    h1({node, ...props}) { return <h1 className="text-xl font-semibold mt-5 mb-2 border-b pb-1" {...props} />; },
    h2({node, ...props}) { return <h2 className="text-lg font-semibold mt-4 mb-1.5" {...props} />; },
    h3({node, ...props}) { return <h3 className="text-base font-semibold mt-4 mb-1" {...props} />; },
    ul({node, ...props}) { return <ul className="list-disc pl-6 my-2 space-y-1" {...props} />; },
    ol({node, ...props}) { return <ol className="list-decimal pl-6 my-2 space-y-1" {...props} />; },
    li({node, ...props}) { return <li className="my-0.5" {...props} />; },
    blockquote({node, ...props}) { return <blockquote className="border-l-4 border-border pl-4 italic my-2.5 text-muted-foreground" {...props} />; },
    p({node, ...props}) { return <p className="my-1.5 leading-relaxed" {...props} />; },
    hr({node, ...props}) { return <hr className="my-4 border-border/50" {...props} />; },
    table({node, ...props}) { return <table className="table-auto w-full my-3 border-collapse border border-border" {...props} />; },
    th({node, ...props}) { return <th className="border border-border px-2 py-1 text-left font-semibold bg-muted/50" {...props} />; },
    td({node, ...props}) { return <td className="border border-border px-2 py-1" {...props} />; },
};

// --- Icon Helper ---
const getIconForStatus = (status: string): React.ElementType => {
    const lowerStatus = status.toLowerCase();
    if (lowerStatus.includes("error")) return AlertTriangle;
    if (lowerStatus.includes("search") || lowerStatus.includes("looking for") || lowerStatus.includes("rag")) return Search;
    if (lowerStatus.includes("fetch") || lowerStatus.includes("downloading")) return FileDown;
    if (lowerStatus.includes("summarizing") || lowerStatus.includes("analyzing") || lowerStatus.includes("processing")) return Loader2;
    if (lowerStatus.includes("generating") || lowerStatus.includes("preparing response") || lowerStatus.includes("thinking")) return MessageSquarePlus;
    if ((lowerStatus.includes("found") && lowerStatus.includes("sources")) || (lowerStatus.includes("retrieved") && lowerStatus.includes("chunk"))) return ClipboardCheck;
    if (lowerStatus.includes("complete")) return CheckCircle2;
    return Info;
};
// ---

export default function MessageBlock({ message, isAsking }: MessageBlockProps) {
    const isUser = message.sender === 'user';
    const hasWebSources = !isUser && message.webSources && message.webSources.length > 0;
    const hasRagSources = !isUser && message.ragSources && message.ragSources.length > 0;
    const hasRetrievedContext = !isUser && message.retrievedContext && message.retrievedContext.length > 0;
    const hasStatusSteps = !isUser && message.statusSteps && message.statusSteps.length > 0;

    // Determine if this specific message is the one actively being generated/worked on
    const isThisMessageProcessing = !isUser && isAsking && !message.text && !message.error;

    const showTextContent = !!message.text;

    // Helper to get favicon URL
    const getFaviconUrl = (url: string) => {
        try {
            const hostname = new URL(url).hostname;
            return `https://www.google.com/s2/favicons?domain=${hostname}&sz=32`;
        } catch (e) { return null; }
    };

    return (
        <div className={cn("w-full")}> {/* Remove flex/flex-col here */}

            {/* User Input Block */}
            {isUser && (
                <div className="mb-1"> {/* Optional: small bottom margin for user block */}
                    <div className="flex items-center gap-2 mb-1.5">
                         <div className="flex-shrink-0 w-6 h-6 rounded-full bg-accent text-accent-foreground items-center justify-center flex"> <User className="w-3.5 h-3.5" /> </div>
                         <span className="text-sm font-medium text-foreground/80">You</span>
                    </div>
                    <div className="pl-8"> {/* Indent content slightly */}
                         <p className="text-[15px] text-foreground whitespace-pre-wrap break-words">
                            {message.text}
                         </p>
                    </div>
                 </div>
            )}

            {/* AI Response Block - Styled as a Card */}
            {!isUser && (
                <div className={cn(
                    "border rounded-lg p-4", // Card styling
                    "bg-card/40 dark:bg-gray-800/20 border-border/60 dark:border-gray-700/50" // Backgrounds and borders
                )}>
                     {/* Optional Header for AI Block */}
                     <div className="flex items-center gap-2 mb-3">
                         <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary items-center justify-center flex"> <Bot className="w-3.5 h-3.5" /> </div>
                         <span className="text-sm font-semibold text-primary">LearnMate</span>
                     </div>

                     {/* Content Area within the Card */}
                     <div className="pl-8 space-y-3"> {/* Indent content, add vertical space */}

                        {/* Status Steps Display */}
                        {hasStatusSteps && (
                            <div className="space-y-1 border rounded-md p-2 bg-muted/30 dark:bg-gray-700/20 border-border/50">
                                {/* <h4 className="text-xs font-semibold text-muted-foreground mb-1">Progress:</h4> */}
                                {message.statusSteps?.map((step, index) => {
                                     const Icon = getIconForStatus(step);
                                     const showSpinAnimation = Icon === Loader2 && index === message.statusSteps!.length - 1 && isAsking;
                                     const isLastError = Icon === AlertTriangle && index === message.statusSteps!.length - 1;
                                     return ( <div key={`${message.id}-step-${index}`} className={cn( "flex items-center text-xs px-1 py-0.5 rounded", isLastError ? "text-destructive font-medium" : "text-muted-foreground" )}> <Icon className={cn( "w-3.5 h-3.5 mr-1.5 flex-shrink-0", showSpinAnimation && "animate-spin" )} /> {step} </div> );
                                })}
                            </div>
                        )}

                        {/* Error Message Display */}
                        {message.error && ( // Show error prominently if it exists
                            <div className="p-2 text-sm text-destructive-foreground bg-destructive/80 rounded-md flex items-start border border-destructive"> <AlertTriangle className="w-4 h-4 mr-2 flex-shrink-0 mt-0.5" /> <div> <p className="font-medium leading-tight">Error</p> <p className="text-xs mt-0.5">{message.error}</p> </div> </div>
                        )}

                        {/* Main AI Text (Markdown) */}
                        {showTextContent && !message.error && ( // Hide text if error occurred? Optional.
                             <div className={cn( "prose prose-sm dark:prose-invert max-w-none text-foreground", /* prose styles */ )}>
                                <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                                    {`${message.text || ''}${isAsking && message.id === message.id && !message.error && !message.text ? '█' : ''}`}
                                </ReactMarkdown>
                            </div>
                        )}

                        {/* Initial placeholder if actively processing this message */}
                        {isThisMessageProcessing && !hasStatusSteps && !showTextContent && !message.error && (
                            <p className="text-sm text-muted-foreground italic py-1">Generating response...</p>
                        )}

                         {/* Retrieved RAG Context Display */}
                        {hasRetrievedContext && (
                             <div className={cn("mt-3 pt-3", (hasWebSources || hasRagSources) ? "border-t border-dashed border-border/30" : "border-t border-border/40")}>
                                <h4 className="text-xs font-semibold text-muted-foreground mb-2 flex items-center"> <BookCopy className="w-3.5 h-3.5 mr-1.5" /> Retrieved Context </h4>
                                <Accordion type="single" collapsible className="w-full -mt-1">
                                    {message.retrievedContext?.map((ctx, idx) => (
                                        <AccordionItem value={`rag-ctx-${idx}`} key={`rag-ctx-${idx}`} className="border-b border-border/30 last:border-b-0">
                                            <AccordionTrigger className="text-xs py-1.5 hover:no-underline text-muted-foreground data-[state=open]:text-foreground font-medium hover:bg-muted/50 rounded px-2">
                                                <div className="flex items-center space-x-1.5 truncate mr-2"> <FileTextIcon className="w-3.5 h-3.5 flex-shrink-0"/> <span className="truncate font-semibold text-foreground/90" title={ctx.filename}>{ctx.filename}</span> {ctx.page !== 'N/A' && (<span className="text-xs text-muted-foreground flex-shrink-0">(Page {ctx.page})</span>)} </div>
                                            </AccordionTrigger>
                                            <AccordionContent className="pt-1 pb-2 text-xs text-muted-foreground/90 pl-6 pr-2 max-h-28"> <ScrollArea className="h-full pr-2"> <blockquote className="border-l-2 border-border/70 pl-2 italic text-[11px] leading-snug whitespace-pre-wrap break-words"> "{ctx.snippet}" </blockquote> <ScrollBar orientation="vertical" className="w-1.5" /> </ScrollArea> </AccordionContent>
                                        </AccordionItem>
                                    ))}
                                </Accordion>
                             </div>
                        )}

                        {/* Web Sources Display with Popovers */}
                        {hasWebSources && (
                            <div className={cn("mt-3 pt-3", (hasRagSources || hasRetrievedContext) ? "border-t border-dashed border-border/30" : "border-t border-border/40")}>
                                <h4 className="text-xs font-semibold text-muted-foreground mb-2 flex items-center"> <LinkIcon className="w-3.5 h-3.5 mr-1.5" /> Sources </h4>
                                <div className="flex flex-wrap gap-1.5">
                                    {message.webSources?.map((source, idx) => {
                                        const faviconUrl = getFaviconUrl(source.url);
                                        const displayTitle = source.title || new URL(source.url).hostname;
                                        const hasSnippet = source.snippet && source.snippet !== "Snippet not available." && source.snippet !== "Could not extract snippet.";

                                        return (
                                            <Popover key={`web-source-pop-${idx}-${source.url}`}>
                                                <PopoverTrigger asChild>
                                                     <Badge
                                                        variant="outline"
                                                        className="cursor-pointer hover:bg-muted/80 dark:hover:bg-muted/30 transition-colors border-border/70 text-muted-foreground hover:text-foreground font-normal px-2 py-0.5 max-w-[200px] md:max-w-[250px] truncate flex items-center gap-1.5"
                                                        title={displayTitle} // Tooltip for the badge itself (browser default)
                                                     >
                                                        {faviconUrl && <img src={faviconUrl} alt="" width={14} height={14} className="inline-block flex-shrink-0 rounded-sm" loading="lazy" />} {/* Added loading lazy */}
                                                        <span className="truncate">{displayTitle}</span>
                                                     </Badge>
                                                </PopoverTrigger>
                                                {/* Render popover content only if there's a snippet */}
                                                {hasSnippet && (
                                                    <PopoverContent
                                                        side="top"
                                                        align="start"
                                                        className="w-80 md:w-96 z-50 shadow-xl rounded-lg border bg-popover p-0" // Use popover background
                                                        >
                                                        {/* Header with Link */}
                                                        <div className="flex items-center justify-between px-3 py-2 border-b bg-popover-foreground/5">
                                                             <div className="flex items-center gap-1.5 overflow-hidden">
                                                                {faviconUrl && <img src={faviconUrl} alt="" width={14} height={14} className="inline-block flex-shrink-0 rounded-sm" loading="lazy"/>}
                                                                <p className="text-xs font-medium truncate text-popover-foreground" title={displayTitle}>{displayTitle}</p>
                                                            </div>
                                                            <a href={source.url} target="_blank" rel="noopener noreferrer" className="ml-2 text-muted-foreground hover:text-primary flex-shrink-0" aria-label="Open source link">
                                                                <ExternalLink size={14} />
                                                            </a>
                                                        </div>
                                                        {/* Snippet Content */}
                                                        <div className="p-3 max-h-40 overflow-y-auto scrollbar-thin scrollbar-thumb-muted">
                                                            <p className="text-xs leading-relaxed text-popover-foreground/90">
                                                                {source.snippet}
                                                            </p>
                                                        </div>
                                                    </PopoverContent>
                                                )}
                                            </Popover>
                                        )
                                    })}
                                </div>
                            </div>
                        )}

                        {/* Legacy RAG Sources (Accordion) */}
                        {hasRagSources && (
                             <div className={cn("mt-3 pt-3", (hasWebSources || hasRetrievedContext) ? "border-t border-dashed border-border/30" : "border-t border-border/40")}>
                                <Accordion type="single" collapsible className="w-full -mt-2">
                                    <AccordionItem value="legacy-rag-sources" className="border-b-0">
                                        <AccordionTrigger className="text-xs py-1 hover:no-underline text-muted-foreground data-[state=open]:text-foreground font-medium hover:bg-muted/50 rounded px-2">
                                             <FileTextIcon className="w-3.5 h-3.5 mr-1.5 flex-shrink-0"/>
                                            Referenced Document(s) ({message.ragSources?.length})
                                        </AccordionTrigger>
                                        <AccordionContent className="pt-1.5 pb-0 text-xs pl-4 pr-2">
                                            <ul className="list-none space-y-1.5">
                                                {message.ragSources?.map((source, idx) => (
                                                    <li key={`rag-source-${idx}`} className="text-muted-foreground break-words">
                                                        <span className="font-semibold text-foreground/80">{source.source || 'Unknown Source'}</span>
                                                        {source.page && source.page !== 'N/A' ? `, Page ${source.page}` : ''}
                                                    </li>
                                                ))}
                                            </ul>
                                        </AccordionContent>
                                    </AccordionItem>
                                </Accordion>
                            </div>
                        )}
                    </div> {/* End AI Content Area */}
                </div>
            )}
        </div> // End Message Block Container
    );
}