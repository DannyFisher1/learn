// components/chat/ObservationDisplay.tsx
'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from '@/components/ui/badge';
import { ExternalLink, Search, MessageSquare, ListChecks, BoxSelect } from 'lucide-react'; // Icons

// --- Define interfaces for specific tool outputs (match backend structure) ---
interface SearchResult {
    title: string;
    link: string;
    snippet: string;
    [key: string]: any; // Allow other potential fields
}

interface RedditPost {
    title: string;
    score: number;
    id: string;
    subreddit: string;
    url: string; // Permalink to the post
    created_utc: number;
    body?: string; // Body might be missing or empty
    num_comments?: number;
    [key: string]: any; // Allow other potential fields
}

// --- Props for the main component ---
interface ObservationDisplayProps {
    observation: any; // The structured data from the tool
    toolName: string | null; // The name of the tool that produced the observation
}

// --- Helper Components for Rendering Specific Observation Types ---

// Renders Web Search Results
const WebSearchResults = ({ results }: { results: SearchResult[] }) => {
    if (!results || results.length === 0) {
        return <p className="text-xs text-muted-foreground px-4 py-2">No web search results found.</p>;
    }
    return (
        <div className="space-y-3">
            {results.map((result, index) => (
                <Card key={`web-${index}-${result.link}`} className="bg-muted/60 overflow-hidden text-xs shadow-sm">
                    <CardHeader className="p-2 pb-1 border-b">
                         <a
                            href={result.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-primary hover:underline truncate block text-sm"
                            title={result.title}
                        >
                            {result.title || "Untitled Result"}
                        </a>
                         <a
                            href={result.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[10px] text-green-600 dark:text-green-500 hover:underline truncate block"
                            title={result.link}
                        >
                            {result.link}
                        </a>
                    </CardHeader>
                    <CardContent className="p-2 text-[11px] text-muted-foreground leading-relaxed">
                        {result.snippet || "No snippet available."}
                    </CardContent>
                </Card>
            ))}
        </div>
    );
};

// Renders Reddit Search Results
const RedditSearchResults = ({ results }: { results: RedditPost[] }) => {
    if (!results || results.length === 0) {
        return <p className="text-xs text-muted-foreground px-4 py-2">No Reddit posts found matching the criteria.</p>;
    }
    return (
        <div className="space-y-3">
            {results.map((post) => (
                <Card key={`reddit-${post.id}`} className="bg-muted/60 overflow-hidden text-xs shadow-sm">
                    <CardHeader className="p-2 pb-1 border-b">
                        <a
                            href={post.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-primary hover:underline block text-sm leading-tight"
                            title={post.title}
                        >
                            {post.title || "Untitled Post"}
                        </a>
                        <div className="flex items-center justify-between text-[10px] text-muted-foreground mt-1">
                            <span>r/{post.subreddit}</span>
                            <span>Score: {post.score ?? 'N/A'}</span>
                            {post.num_comments !== undefined && <span>Comments: {post.num_comments}</span>}
                        </div>
                    </CardHeader>
                    {post.body && ( // Only show body if it exists
                        <CardContent className="p-2 text-[11px] text-muted-foreground leading-relaxed max-h-20 overflow-hidden line-clamp-4">
                            {post.body}
                        </CardContent>
                    )}
                </Card>
            ))}
        </div>
    );
};

// Renders Generic JSON Data (Fallback)
const JsonDisplay = ({ data }: { data: any }) => {
    let formattedJson = '';
    try {
        formattedJson = JSON.stringify(data, null, 2); // Pretty print
    } catch (e) {
        formattedJson = String(data); // Fallback to string conversion
    }
    return (
        <pre className="text-[10px] bg-muted/80 dark:bg-black/30 p-2 rounded overflow-x-auto border">
            <code>{formattedJson}</code>
        </pre>
    );
};

// --- Main Observation Display Component ---
export default function ObservationDisplay({ observation, toolName }: ObservationDisplayProps) {

    // Determine which renderer to use based on the tool name and observation structure
    const renderContent = () => {
        if (!observation) {
             return <p className="text-xs text-muted-foreground px-4 py-2">No observation data available.</p>;
        }

        // Check specific tool names and expected data structure
        if (toolName === 'search_the_web' && Array.isArray(observation)) {
             // Basic check if items look like search results
             if (observation.length === 0 || (observation[0] && typeof observation[0].title === 'string' && typeof observation[0].link === 'string')) {
                 return <WebSearchResults results={observation as SearchResult[]} />;
             }
        }

        if (toolName === 'search_reddit' && Array.isArray(observation)) {
             // Basic check if items look like Reddit posts
             if (observation.length === 0 || (observation[0] && typeof observation[0].title === 'string' && typeof observation[0].subreddit === 'string')) {
                 return <RedditSearchResults results={observation as RedditPost[]} />;
             }
        }

        // Specific handling for Summarize tool (assuming it returns a string)
        if (toolName === 'summarize_document_content' && typeof observation === 'string') {
             // Just render the summary string (maybe wrap in prose?)
             return (
                <div className="prose prose-sm dark:prose-invert max-w-none text-foreground p-1">
                    <p className="whitespace-pre-wrap">{observation}</p>
                </div>
            );
        }

        // Specific handling for Package tools (expect JSON string or object)
        if ((toolName === 'get_package_info' || toolName === 'inspect_package')) {
             let jsonData = observation;
             // Try parsing if it's a string that looks like JSON
             if (typeof observation === 'string') {
                 try { jsonData = JSON.parse(observation); } catch (e) { /* Ignore parse error, render as string below */ }
             }
             // Render as formatted JSON if it's an object now
             if (typeof jsonData === 'object' && jsonData !== null) {
                 return <JsonDisplay data={jsonData} />;
             }
             // Otherwise fall through to render as string
        }

        // Fallback: Render as string or basic JSON for unknown/other tool observations
        if (typeof observation === 'object' && observation !== null) {
            return <JsonDisplay data={observation} />;
        }

        // Final fallback: render as plain string
        return <p className="text-xs text-muted-foreground whitespace-pre-wrap p-1">{String(observation)}</p>;
    };

    // Determine Title Icon based on tool name
    const TitleIcon =
        toolName === 'search_the_web' ? Search :
        toolName === 'search_reddit' ? MessageSquare :
        toolName === 'summarize_document_content' ? ListChecks :
        BoxSelect; // Default icon

    return (
        <ScrollArea className="h-full w-full">
            <div className="space-y-3 p-4">
                 <h3 className="text-sm font-semibold text-muted-foreground sticky top-0 bg-card pb-2 pt-0 border-b mb-2 -mt-4 z-10 flex items-center gap-1.5">
                     <TitleIcon size={14} className="flex-shrink-0" />
                     Tool Result: {toolName ? <Badge variant="secondary" className="font-mono text-[10px]">{toolName}</Badge> : 'Details'}
                 </h3>
                 {renderContent()}
            </div>
        </ScrollArea>
    );
}