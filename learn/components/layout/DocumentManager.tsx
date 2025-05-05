'use client';

import React, { useState, useEffect, useCallback, ChangeEvent, RefObject } from 'react';
import { DocumentInfo, getDocumentList, deleteDocument } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from "@/components/ui/label";
import {
    Trash2,
    FileText,
    FileImage,
    FileAudio,
    FileVideo,
    FileArchive,
    FileQuestion,
    FileCode2,
    Loader2,
    Search,
    UploadCloud,
    Filter,
    X,
    RefreshCw,
    PlusCircle
} from 'lucide-react';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { UploadDropdownRef } from '@/components/common/UploadDropdown'; // Keep ref type

// --- Props Interface (Removed isOpen and onToggle) ---
interface DocumentManagerProps {
    selectedFilenames: Set<string>;
    onFilenameToggle: (filename: string | null) => void; // null for deselect all
    triggerRefresh: number; // Listen to this prop to trigger refresh
    onDocumentsManaged: () => void; // Callback after delete/upload
    uploadDropdownRef: RefObject<UploadDropdownRef | null>; // Allow null
}

const getFileIcon = (fileType: string | null | undefined) => {
    if (!fileType) return <FileQuestion className="h-4 w-4 text-muted-foreground" />;
    if (fileType.startsWith('image/')) return <FileImage className="h-4 w-4 text-blue-500" />;
    if (fileType.startsWith('audio/')) return <FileAudio className="h-4 w-4 text-purple-500" />;
    if (fileType.startsWith('video/')) return <FileVideo className="h-4 w-4 text-red-500" />;
    if (fileType.startsWith('text/csv') || fileType.includes('spreadsheet')) return <FileText className="h-4 w-4 text-green-600" />; // Treat CSVs like text
    if (fileType.startsWith('text/')) return <FileText className="h-4 w-4 text-gray-600" />;
    if (fileType.includes('pdf')) return <FileText className="h-4 w-4 text-red-700" />;
    if (fileType.includes('zip') || fileType.includes('archive')) return <FileArchive className="h-4 w-4 text-yellow-600" />;
    if (fileType.includes('script') || fileType.includes('code') || fileType.includes('json') || fileType.includes('xml')) return <FileCode2 className="h-4 w-4 text-indigo-600" />;
    return <FileQuestion className="h-4 w-4 text-muted-foreground" />;
};

// --- Component Implementation (Removed collapsible logic) ---
const DocumentManager: React.FC<DocumentManagerProps> = ({
    selectedFilenames,
    onFilenameToggle,
    triggerRefresh,
    onDocumentsManaged,
    uploadDropdownRef,
}) => {
    const [documents, setDocuments] = useState<DocumentInfo[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [isDeleting, setIsDeleting] = useState<Record<string, boolean>>({});
    const [availableTags, setAvailableTags] = useState<string[]>([]);
    const [selectedTagFilter, setSelectedTagFilter] = useState<string>('all'); // 'all' or a specific tag

    // Fetch documents function
    const fetchDocs = useCallback(async () => {
        console.log("[DocManager] Fetching documents...");
        setIsLoading(true);
        setError(null);
        try {
            const data = await getDocumentList();
            console.log("[DocManager] Fetched documents:", data);
            setDocuments(data.documents || []);
            // Extract unique tags
            const tags = new Set<string>();
            (data.documents || []).forEach(doc => {
                if (doc.tag) tags.add(doc.tag);
            });
            setAvailableTags(['all', ...Array.from(tags)]);
        } catch (err: any) {
            console.error("[DocManager] Error fetching documents:", err);
            setError(err.message || 'Failed to load documents.');
            setDocuments([]);
            setAvailableTags(['all']);
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Initial fetch and refresh listener
    useEffect(() => {
        fetchDocs();
    }, [fetchDocs, triggerRefresh]);

    // Handle delete
    const handleDelete = useCallback(async (filename: string) => {
        console.log(`[DocManager] Attempting to delete: ${filename}`);
        setIsDeleting(prev => ({ ...prev, [filename]: true }));
        setError(null);
        try {
            await deleteDocument(filename);
            console.log(`[DocManager] Successfully deleted: ${filename}`);
            setDocuments(prev => prev.filter(doc => doc.filename !== filename));
            // If the deleted file was selected, deselect it
            if (selectedFilenames.has(filename)) {
                onFilenameToggle(filename); // Toggle to remove
            }
            onDocumentsManaged(); // Notify parent page
        } catch (err: any) {
            console.error(`[DocManager] Error deleting ${filename}:`, err);
            setError(err.message || `Failed to delete ${filename}.`);
        } finally {
            setIsDeleting(prev => ({ ...prev, [filename]: false }));
        }
    }, [onDocumentsManaged, onFilenameToggle, selectedFilenames]);

    // Handle search term change
    const handleSearchChange = (event: ChangeEvent<HTMLInputElement>) => {
        setSearchTerm(event.target.value);
    };

    // Handle tag filter change
    const handleTagFilterChange = (value: string) => {
        setSelectedTagFilter(value);
    };

    // Filter documents based on search term and selected tag
    const filteredDocuments = documents.filter(doc => {
        const matchesSearch = doc.filename.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesTag = selectedTagFilter === 'all' || doc.tag === selectedTagFilter;
        return matchesSearch && matchesTag;
    });

    const handleUploadClick = () => {
        uploadDropdownRef.current?.triggerUpload();
    };

    const handleSelectAll = (checked: boolean | 'indeterminate') => {
        if (checked === true) {
            filteredDocuments.forEach(doc => {
                if (!selectedFilenames.has(doc.filename)) {
                    onFilenameToggle(doc.filename); // Add if not selected
                }
            });
        } else {
            // Deselect all currently *visible* documents
            filteredDocuments.forEach(doc => {
                 if (selectedFilenames.has(doc.filename)) {
                     onFilenameToggle(doc.filename); // Remove if selected
                 }
             });
            // A simpler way might be just onFilenameToggle(null);
            // but let's stick to toggling visible ones for now.
        }
    };

    const numVisibleSelected = filteredDocuments.filter(doc => selectedFilenames.has(doc.filename)).length;
    const isAllVisibleSelected = filteredDocuments.length > 0 && numVisibleSelected === filteredDocuments.length;
    const isIndeterminate = numVisibleSelected > 0 && numVisibleSelected < filteredDocuments.length;


    // --- Render the content directly ---
    return (
        <div className="flex flex-col h-full p-3 bg-popover text-popover-foreground space-y-3 w-80"> {/* Adjust width as needed */}
            {/* Header */}
            <div className="flex items-center justify-between flex-shrink-0">
                <h2 className="text-lg font-semibold">Documents</h2>
                <div className="flex items-center gap-1">
                    <TooltipProvider delayDuration={100}>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon" onClick={handleUploadClick} className="h-7 w-7">
                                    <UploadCloud className="h-4 w-4" />
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent side="bottom">Upload New Document</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                             <TooltipTrigger asChild>
                                 <Button
                                     variant="ghost"
                                     size="icon"
                                     onClick={fetchDocs}
                                     disabled={isLoading}
                                     className="h-7 w-7"
                                 >
                                     {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                                 </Button>
                             </TooltipTrigger>
                             <TooltipContent side="bottom">Refresh List</TooltipContent>
                         </Tooltip>
                    </TooltipProvider>
                </div>
            </div>

             {/* Search and Filter */}
             <div className="flex flex-col gap-2 flex-shrink-0">
                 <div className="relative">
                     <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                     <Input
                         placeholder="Search documents..."
                         value={searchTerm}
                         onChange={handleSearchChange}
                         className="pl-8 h-8 text-xs"
                     />
                 </div>
                 <div className="flex items-center gap-2">
                     <Filter className="h-4 w-4 text-muted-foreground" />
                     <Select value={selectedTagFilter} onValueChange={handleTagFilterChange}>
                         <SelectTrigger className="h-8 text-xs flex-grow">
                             <SelectValue placeholder="Filter by tag..." />
                         </SelectTrigger>
                         <SelectContent>
                             {availableTags.map(tag => (
                                 <SelectItem key={tag} value={tag} className="text-xs">
                                     {tag === 'all' ? 'All Tags' : tag}
                                 </SelectItem>
                             ))}
                         </SelectContent>
                     </Select>
                 </div>
             </div>


            {/* Select All / Deselect All */}
             <div className="flex items-center space-x-2 flex-shrink-0 border-t pt-2">
                  <Checkbox
                       id="select-all-visible"
                       checked={isAllVisibleSelected ? true : (isIndeterminate ? 'indeterminate' : false)}
                       onCheckedChange={handleSelectAll}
                   />
                 <Label htmlFor="select-all-visible" className="text-xs font-medium">
                     Select/Deselect Visible ({numVisibleSelected}/{filteredDocuments.length})
                 </Label>
             </div>

            {/* Document List */}
            <ScrollArea className="flex-grow border rounded-md">
                <div className="p-2 space-y-1">
                    {isLoading && !documents.length ? (
                        <div className="flex items-center justify-center p-4 text-muted-foreground text-xs">
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Loading...
                        </div>
                    ) : error ? (
                        <div className="p-4 text-red-600 text-xs text-center bg-red-50 border border-red-200 rounded">{error}</div>
                    ) : filteredDocuments.length === 0 ? (
                         <div className="p-4 text-muted-foreground text-xs text-center">
                             {documents.length === 0 ? "No documents uploaded yet." : "No documents match filter."}
                         </div>
                    ) : (
                        filteredDocuments.map(doc => (
                            <div
                                key={doc.filename}
                                className={`flex items-center justify-between p-1.5 rounded hover:bg-muted/50 text-xs group ${selectedFilenames.has(doc.filename) ? 'bg-muted' : ''}`}
                            >
                                <div className="flex items-center space-x-2 flex-grow overflow-hidden mr-1">
                                    <Checkbox
                                        id={`cb-${doc.filename}`}
                                        checked={selectedFilenames.has(doc.filename)}
                                        onCheckedChange={() => onFilenameToggle(doc.filename)}
                                        aria-label={`Select ${doc.filename}`}
                                    />
                                    {getFileIcon(doc.file_type)}
                                    <span className="truncate flex-shrink min-w-0" title={doc.filename}>
                                        {doc.filename}
                                    </span>
                                     {doc.tag && <Badge variant="secondary" className="text-xs flex-shrink-0">{doc.tag}</Badge>}
                                </div>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                                    onClick={() => handleDelete(doc.filename)}
                                    disabled={isDeleting[doc.filename]}
                                    aria-label={`Delete ${doc.filename}`}
                                >
                                    {isDeleting[doc.filename] ? (
                                        <Loader2 className="h-3 w-3 animate-spin" />
                                    ) : (
                                        <Trash2 className="h-3 w-3" />
                                    )}
                                </Button>
                            </div>
                        ))
                    )}
                </div>
            </ScrollArea>

            {/* Footer Actions (Optional - maybe remove Select All/Deselect All) */}
            {/* Consider if Select All/Deselect All buttons are needed if checkbox is there */}
            {/* <div className="flex justify-between flex-shrink-0 pt-2 border-t">
                <Button variant="outline" size="xs" onClick={() => onFilenameToggle(null)} disabled={selectedFilenames.size === 0}>
                    Deselect All
                </Button>
            </div> */}
        </div>
    );
};

export default DocumentManager; 