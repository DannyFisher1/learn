// components/chat/RagContextDisplay.tsx
'use client';

import React, { useState } from 'react';
import { RagContextDocument } from '@/lib/api'; // Import the type
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from '@/components/ui/scroll-area';
import { FileText, Tag as TagIcon, ClipboardCopy } from 'lucide-react'; // Icons
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner'; // For copy feedback
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
interface RagContextDisplayProps {
    contextDocs: RagContextDocument[] | null;
}

// Simple component to render a single context document snippet
const ContextDocSnippet = ({ doc }: { doc: RagContextDocument }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const maxSnippetLength = 150; // Characters to show before truncating

    const handleCopy = () => {
        navigator.clipboard.writeText(doc.page_content)
            .then(() => toast.success("Context snippet copied!"))
            .catch(err => toast.error("Failed to copy snippet."));
    };

    return (
         <Card className="bg-muted/60 shadow-sm overflow-hidden text-xs">
             <CardHeader className="p-2 flex flex-row items-center justify-between space-y-0 border-b">
                 <div className="flex items-center gap-1.5 overflow-hidden mr-2">
                    <FileText size={14} className="flex-shrink-0 text-muted-foreground" />
                    <span className="font-medium text-foreground/90 truncate" title={doc.metadata.source_file || 'Unknown Source'}>
                        {doc.metadata.source_file || 'Unknown Source'}
                    </span>
                    {doc.metadata.page && (
                         <span className="text-muted-foreground text-[10px]">(p. {doc.metadata.page})</span>
                     )}
                     {doc.metadata.tag && (
                         <Badge variant="outline" className="text-[9px] h-auto py-0 px-1.5 ml-1 font-normal">
                            <TagIcon size={10} className="mr-0.5"/>{doc.metadata.tag}
                         </Badge>
                     )}
                 </div>
                 <TooltipProvider delayDuration={100}>
                    <Tooltip>
                         <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-6 w-6 flex-shrink-0" onClick={handleCopy}>
                                <ClipboardCopy size={12} />
                            </Button>
                         </TooltipTrigger>
                         <TooltipContent side="top"><p>Copy Snippet</p></TooltipContent>
                     </Tooltip>
                 </TooltipProvider>
             </CardHeader>
             <CardContent className="p-2">
                 <p
                     className={cn(
                         "whitespace-pre-wrap break-words text-muted-foreground text-[11px] leading-relaxed",
                         !isExpanded && "line-clamp-4" // Show ~4 lines when collapsed
                     )}
                     onClick={() => setIsExpanded(!isExpanded)} // Toggle on click
                     style={{ cursor: doc.page_content.length > maxSnippetLength ? 'pointer' : 'default' }}
                 >
                     {doc.page_content}
                 </p>
                 {doc.page_content.length > maxSnippetLength && (
                      <button
                         onClick={() => setIsExpanded(!isExpanded)}
                         className="text-[10px] text-primary hover:underline mt-1"
                     >
                         {isExpanded ? 'Show less' : 'Show more'}
                     </button>
                  )}
             </CardContent>
         </Card>
    );
};


export default function RagContextDisplay({ contextDocs }: RagContextDisplayProps) {
    // Note: The empty state is handled by the parent component (page.tsx)
    // This component assumes contextDocs is a valid array when rendered.
    if (!contextDocs || contextDocs.length === 0) {
        // Should ideally not be rendered by parent if contextDocs is null/empty,
        // but include a fallback just in case.
        return <div className="p-4 text-xs text-muted-foreground">No context available.</div>;
    }

    return (
        <ScrollArea className="h-full w-full">
            <div className="space-y-3 p-4">
                 <h3 className="text-sm font-semibold text-muted-foreground sticky top-0 bg-card pb-2 pt-0 border-b mb-2 -mt-4 z-10"> {/* Sticky header */}
                     Retrieved Context ({contextDocs.length})
                 </h3>
                 {contextDocs.map((doc) => (
                    <ContextDocSnippet key={doc.id} doc={doc} />
                 ))}
            </div>
        </ScrollArea>
    );
}