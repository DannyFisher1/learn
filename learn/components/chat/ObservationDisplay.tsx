// components/chat/ObservationDisplay.tsx
'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from '@/components/ui/badge';
import { ExternalLink, Search, MessageSquare, ListChecks, BoxSelect, Star, MessageCircle as MessageIcon } from 'lucide-react'; // Added icons
import { formatDistanceToNow } from 'date-fns'; // For relative time formatting

// --- Define interfaces for specific tool outputs (match backend structure) ---
// Ensure these match the keys actually returned by your backend tools
interface SearchResult {
    title: string;
    link: string; // URL of the result
    snippet?: string; // Text snippet/description
    // Add any other fields your Searx tool might return if needed
}

interface RedditPost {
    post_title: string;
    post_score: number;
    post_id: string;
    post_subreddit: string;
    post_url: string; // Permalink to the post
    post_created_utc?: number; // Optional: Add if tool provides it
    post_text?: string;
    post_num_comments?: number; // Optional: Add if tool provides it
    post_author?: string; // Add author if available
    // thumbnail?: string; // Potentially add thumbnail URL if provided
}

// --- Props for the main component ---
interface ObservationDisplayProps {
    observation: any; // The structured data from the tool
    toolName: string | null; // The name of the tool that produced the observation
}

// --- Helper function to get base domain for favicon ---
const getBaseDomain = (url: string): string | null => {
    try {
        const parsedUrl = new URL(url);
        return parsedUrl.hostname;
    } catch (e) {
        return null; // Invalid URL
    }
};

// --- Helper function to format relative time ---
const formatRelativeTime = (timestamp: number): string => {
    try {
        // Reddit provides UTC timestamp in seconds, convert to milliseconds for Date
        return formatDistanceToNow(new Date(timestamp * 1000), { addSuffix: true });
    } catch (e) {
        return 'Invalid date';
    }
};


// --- Helper Components for Rendering Specific Observation Types ---

// Renders Web Search Results - Enhanced Card Style
const WebSearchResults = ({ results }: { results: SearchResult[] }) => {
    if (!results || results.length === 0) {
        return <p className="text-xs text-muted-foreground px-4 py-2">No web search results found.</p>;
    }
    return (
        <div className="space-y-2.5"> {/* Slightly tighter spacing */}
            {results.map((result, index) => {
                const domain = getBaseDomain(result.link);
                const faviconUrl = domain ? `https://www.google.com/s2/favicons?domain=${domain}&sz=16` : undefined; // Google Favicon API (simple)

                return (
                    <Card key={`web-${index}-${result.link}`} className="bg-muted/40 dark:bg-muted/20 overflow-hidden text-xs shadow-sm border border-border/30 hover:border-primary/30 transition-colors group">
                        <CardContent className="p-2.5"> {/* Single content block */}
                            <div className="flex items-center gap-2 mb-1">
                                {faviconUrl && (
                                    <img src={faviconUrl} alt="" width={16} height={16} className="rounded flex-shrink-0" onError={(e) => e.currentTarget.style.display='none'} /> // Hide if favicon fails
                                )}
                                <a
                                    href={result.link}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-[10px] text-muted-foreground group-hover:text-primary truncate block"
                                    title={result.link}
                                >
                                    {domain || result.link}
                                </a>
                             </div>
                             <a
                                href={result.link}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="font-medium text-foreground group-hover:text-primary group-hover:underline decoration-primary/50 underline-offset-2 mb-1 block text-[13px] leading-tight"
                                title={result.title}
                            >
                                {result.title || "Untitled Result"}
                            </a>
                            <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2"> {/* Limit snippet lines */}
                                {result.snippet || "No snippet available."}
                            </p>
                        </CardContent>
                    </Card>
                );
            })}
        </div>
    );
};

// Renders Reddit Search Results - Enhanced Card Style
const RedditSearchResults = ({ results }: { results: RedditPost[] }) => {
    if (!results || results.length === 0) {
        return <p className="text-xs text-muted-foreground px-4 py-2">No Reddit posts found matching the criteria.</p>;
    }
    return (
        <div className="space-y-2.5">
            {results.map((post) => (
                <Card key={`reddit-${post.post_id}`} className="bg-muted/40 dark:bg-muted/20 overflow-hidden text-xs shadow-sm border border-border/30 hover:border-primary/30 transition-colors group">
                    <CardContent className="p-2.5">
                        <a
                            href={post.post_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-foreground group-hover:text-primary group-hover:underline decoration-primary/50 underline-offset-2 mb-1.5 block text-[13px] leading-tight"
                            title={post.post_title}
                        >
                            {post.post_title || "Untitled Post"}
                        </a>
                        {/* Metadata row */}
                        <div className="flex items-center flex-wrap gap-x-2 gap-y-1 text-[10px] text-muted-foreground mb-1.5">
                            <Badge variant="outline" className="px-1.5 py-0 text-[9px] font-normal border-orange-500/50 text-orange-600 dark:text-orange-400">
                                {post.post_subreddit}
                            </Badge>
                            {post.post_author && <span>by u/{post.post_author}</span>}
                            {post.post_created_utc && <span>{formatRelativeTime(post.post_created_utc)}</span>}
                        </div>
                         {/* Score / Comments Row */}
                         <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground mb-1.5">
                             <span className="inline-flex items-center gap-0.5"><Star size={10} className="text-amber-500" /> {post.post_score ?? 'N/A'}</span>
                             {post.post_num_comments !== undefined && <span className="inline-flex items-center gap-0.5"><MessageIcon size={10} /> {post.post_num_comments}</span>}
                         </div>
                         {/* Optional body snippet */}
                         {post.post_text && (
                            <p className="text-[11px] text-muted-foreground/90 leading-relaxed max-h-16 overflow-hidden line-clamp-3 border-l-2 border-border/40 pl-2 mt-1">
                                {post.post_text}
                            </p>
                         )}
                    </CardContent>
                </Card>
            ))}
        </div>
    );
};

// Renders Generic JSON Data (Fallback - Unchanged)
const JsonDisplay = ({ data }: { data: any }) => {
    let formattedJson = '';
    try { formattedJson = JSON.stringify(data, null, 2); } catch (e) { formattedJson = String(data); }
    return ( <pre className="text-[10px] bg-muted/80 dark:bg-black/30 p-2 rounded overflow-x-auto border"><code>{formattedJson}</code></pre> );
};

// --- Main Observation Display Component ---
export default function ObservationDisplay({ observation, toolName }: ObservationDisplayProps) {

    const renderContent = () => {
        if (observation === null || observation === undefined) {
             return <p className="text-xs text-muted-foreground px-4 py-2">No observation data available for this step.</p>;
        }

        // --- Improved Tool Checking & Rendering ---
        if (toolName === 'search_the_web' && Array.isArray(observation)) {
             // Add more robust check? Assume SearchResult if it's an array and first item has title/link
             if (observation.length === 0 || (observation[0] && typeof observation[0].title === 'string' && typeof observation[0].link === 'string')) {
                 return <WebSearchResults results={observation as SearchResult[]} />;
             }
        }

        if (toolName === 'search_reddit' && Array.isArray(observation)) {
             // Assume RedditPost if array and first item has expected keys
             if (observation.length === 0 || (observation[0] && typeof observation[0].post_title === 'string' && typeof observation[0].post_subreddit === 'string' && typeof observation[0].post_score === 'number')) {
                 return <RedditSearchResults results={observation as RedditPost[]} />;
             }
        }

        if (toolName === 'summarize_document_content' && typeof observation === 'string') {
             return ( <div className="prose prose-sm dark:prose-invert max-w-none text-foreground p-1"><p className="whitespace-pre-wrap">{observation}</p></div> );
        }

        if ((toolName === 'get_package_info' || toolName === 'inspect_package')) {
             let jsonData = observation;
             if (typeof observation === 'string') { try { jsonData = JSON.parse(observation); } catch (e) { /* Ignore*/ } }
             if (typeof jsonData === 'object' && jsonData !== null) { return <JsonDisplay data={jsonData} />; }
        }
        // --- End Specific Tool Checks ---

        // Fallback rendering
        if (typeof observation === 'object' && observation !== null) { return <JsonDisplay data={observation} />; }
        return <p className="text-xs text-muted-foreground whitespace-pre-wrap p-1">{String(observation)}</p>;
    };

    // Determine Title Icon (Unchanged)
    const TitleIcon = toolName === 'search_the_web' ? Search : toolName === 'search_reddit' ? MessageSquare : toolName === 'summarize_document_content' ? ListChecks : BoxSelect;

    return (
        <ScrollArea className="h-full w-full">
            <div className="space-y-3 p-4">
                 <h3 className="text-sm font-semibold text-muted-foreground sticky top-0 bg-card/95 backdrop-blur-sm pb-2 pt-4 border-b mb-2 -mt-4 z-10 flex items-center gap-1.5"> {/* // Adjusted sticky header */}
                     <TitleIcon size={14} className="flex-shrink-0" />
                     Tool Result: {toolName ? <Badge variant="outline" className="font-mono text-[10px] font-normal">{toolName}</Badge> : 'Details'}
                 </h3>
                 {renderContent()}
            </div>
        </ScrollArea>
    );
}