// components/layout/WorkspacePane.tsx
'use client';

import React from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { AlertCircle, CheckCircle, Info, LayoutPanelLeft, Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { cn } from '@/lib/utils';

// --- Interface for Content Prop ---
// Ensure this aligns with what page.tsx sets in setWorkspaceContent
interface WorkspaceContent {
    type: 'markdown_report' | 'project_result' | 'json_data' | 'error' | 'info' | string; // Allow string for flexibility
    data: any; // Data structure depends on the type
    title?: string;
}

interface WorkspacePaneProps {
    content: WorkspaceContent | null;
    isLoading: boolean;
}

// --- Basic Markdown Components for Reports ---
// Consider extracting shared markdown config with MessageBlock later
const reportMarkdownComponents: Partial<Components> = {
    // Use default renderers or customize as needed (e.g., code blocks)
    code({ node, inline, className, children, ...props }: any) {
        const match = /language-(\w+)/.exec(className || '');
        const language = match ? match[1] : 'text';
        return !inline ? (
            <SyntaxHighlighter
                style={vscDarkPlus as any} language={language} PreTag="div"
                className="!p-3 !my-3 text-xs font-mono !bg-[#1e1e1e] rounded border border-border/30"
                wrapLongLines={true} {...props}>
                {String(children).replace(/\n$/, '')}
            </SyntaxHighlighter>
        ) : (
            <code className={cn("inline-code rounded bg-muted/80 dark:bg-muted/30 px-[0.4em] py-[0.1em] font-mono text-xs", className)} {...props}>{children}</code>
        );
    },
    a({ node, children, ...props }) { const href = props.href && typeof props.href === 'string' ? props.href : '#'; return ( <a {...props} href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:text-primary/80">{children}</a> ); },
    // Add other renderers if desired (tables, headings, etc.)
};
// ---

export default function WorkspacePane({ content, isLoading }: WorkspacePaneProps) {

    const renderContent = () => {
        // 1. Loading State
        if (isLoading) {
            return (
                <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground animate-pulse">
                    <Loader2 className="w-12 h-12 text-muted-foreground/50 mb-4 animate-spin" />
                    <p className="text-sm">Loading Results...</p>
                </div>
            );
        }

        // 2. No Content (Placeholder) State
        if (!content) {
            return (
                <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
                    <LayoutPanelLeft className="w-16 h-16 text-muted-foreground/30 mb-4" />
                    <h3 className="text-lg font-semibold text-foreground/80 mb-1">Workspace</h3>
                    <p className="text-sm px-4 max-w-xs">
                         Select a completed job from the sidebar to view its results here.
                    </p>
                </div>
            );
        }

        // 3. Render based on Content Type
        switch (content.type) {
            case 'markdown_report':
                return (
                    <Card className="h-full flex flex-col shadow-sm overflow-hidden">
                        <CardHeader className="border-b py-3 px-4 flex-shrink-0">
                            <CardTitle className="text-base">{content.title || "Research Report"}</CardTitle>
                        </CardHeader>
                        <CardContent className="flex-grow p-0 overflow-hidden"> {/* Use flex-grow and overflow */}
                             <ScrollArea className="h-full p-4"> {/* ScrollArea takes full height */}
                                 <ReactMarkdown
                                    components={reportMarkdownComponents}
                                    remarkPlugins={[remarkGfm]}
                                 >
                                     {content.data?.report_markdown || content.data || "No report content available."}
                                 </ReactMarkdown>
                             </ScrollArea>
                        </CardContent>
                    </Card>
                );

             case 'project_result':
                 return (
                    <Card className="h-full flex flex-col shadow-sm">
                        <CardHeader className="border-b py-3 px-4">
                            <CardTitle className="text-base">{content.title || "Project Generation Result"}</CardTitle>
                            {content.data?.final_message && <CardDescription>{content.data.final_message}</CardDescription>}
                        </CardHeader>
                        <CardContent className="flex-grow p-4 space-y-2 overflow-y-auto"> {/* Allow content scroll */}
                            <p className="text-sm font-medium">Output Directory:</p>
                             <code className="text-xs bg-muted px-2 py-1 rounded font-mono break-all block"> {/* Use block */}
                                 {content.data?.output_dir || "N/A"}
                             </code>
                             {/* Add other project details */}
                             {content.data?.tests_passed !== undefined && (
                                 <p className="text-sm">Tests Passed: {String(content.data.tests_passed)}</p>
                             )}
                        </CardContent>
                    </Card>
                 );

            case 'json_data':
                return (
                    <Card className="h-full flex flex-col shadow-sm overflow-hidden">
                        <CardHeader className="border-b py-3 px-4 flex-shrink-0">
                             <CardTitle className="text-base">{content.title || "Job Result Data"}</CardTitle>
                        </CardHeader>
                        <CardContent className="flex-grow p-0 overflow-hidden"> {/* Use flex-grow and overflow */}
                            <ScrollArea className="h-full"> {/* ScrollArea takes full height */}
                                 <SyntaxHighlighter
                                    language="json"
                                    style={vscDarkPlus as any}
                                    className="!m-0 !p-4 text-xs h-full" // Ensure highlighter fills scroll area
                                    wrapLongLines={false} // Allow horizontal scroll for long lines
                                    showLineNumbers={true}
                                 >
                                     {JSON.stringify(content.data, null, 2)}
                                 </SyntaxHighlighter>
                             </ScrollArea>
                         </CardContent>
                    </Card>
                );

            case 'error':
                 return (
                    <Card className="border-destructive h-full shadow-sm">
                        <CardHeader className="flex flex-row items-center space-x-2 border-b border-destructive/50 py-3 px-4 text-destructive">
                             <AlertCircle className="w-5 h-5"/>
                             <CardTitle className="text-base">{content.data?.title || "Error"}</CardTitle>
                        </CardHeader>
                        <CardContent className="p-4 overflow-y-auto"> {/* Allow scroll for long errors */}
                             <p className="text-sm text-destructive">{content.data?.message || "An unknown error occurred."}</p>
                        </CardContent>
                    </Card>
                 );

             case 'info':
                 return (
                    <Card className="h-full shadow-sm">
                         <CardHeader className="flex flex-row items-center space-x-2 border-b py-3 px-4 text-muted-foreground">
                             <Info className="w-5 h-5"/>
                             <CardTitle className="text-base text-foreground">{content.data?.title || "Information"}</CardTitle>
                        </CardHeader>
                        <CardContent className="p-4 overflow-y-auto">
                             <p className="text-sm">{content.data?.message || "No details."}</p>
                        </CardContent>
                    </Card>
                 );

            default: // Fallback for unknown types or placeholder state
                return (
                    <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
                         <LayoutPanelLeft className="w-16 h-16 text-muted-foreground/30 mb-4" />
                         <h3 className="text-lg font-semibold text-foreground/80 mb-1">Workspace</h3>
                         <p className="text-sm px-4 max-w-xs"> Select a completed job to view results. </p>
                         {content?.type && <p className="text-xs mt-2">(Received unknown type: {content.type})</p>}
                    </div>
                );
        }
    };

    return (
        // The outer div takes the height provided by the Panel in page.tsx
        <div className="h-full w-full p-1"> {/* Add small padding around the card */}
            {renderContent()}
        </div>
    );
}