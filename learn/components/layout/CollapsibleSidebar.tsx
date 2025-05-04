// components/layout/CollapsibleSidebar.tsx
'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Input } from "@/components/ui/input"; // For potential filter input
import { Dialog, DialogTrigger } from "@/components/ui/dialog"; // For Manage Documents Modal Trigger

import {
    ChevronLeft, ChevronRight, Upload, FileText, Settings, FileUp, Search, RefreshCw, // Lucide icons
    FileTextIcon as RadixFileText, // Radix for specific tags if needed
    HomeIcon, IdCardIcon
} from 'lucide-react'; // Or use Radix consistently

import { DesktopIcon, ReaderIcon, QuestionMarkCircledIcon } from '@radix-ui/react-icons';

import { cn } from '@/lib/utils';
import { getDocumentList, DocumentInfo } from '@/lib/api'; // API function
import { UploadDropdownRef } from '../common/UploadDropdown'; // Ref type
import ManageDocumentsModal from '../modals/ManageDocumentsModal'; // Import the modal

// --- Constants ---
const ALL_DOCUMENTS_VALUE = 'all'; // Special value for selecting all docs

// --- Define Tags for Upload (Similar to old options menu) ---
// Using Lucide icons now
const uploadTags = [
    { label: "Textbook", value: "textbook", icon: FileText },
    { label: "Lecture Slides", value: "slides", icon: DesktopIcon },
    { label: "Notes", value: "notes", icon: ReaderIcon },
    { label: "Homework", value: "homework", icon: HomeIcon },
    { label: "Quiz/Exam", value: "quiz", icon: IdCardIcon },
    { label: "General", value: "general", icon: QuestionMarkCircledIcon },
];

// --- Define Color Classes (reuse from previous components) ---
const tagColorClasses: { [key: string]: string } = {
    "textbook": "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    "slides":   "bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200",
    "notes":    "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
    "homework": "bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200",
    "quiz":     "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
    "general":  "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200",
};
const fileTypeColorClasses: { [key: string]: string } = {
    "pdf": "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
    "docx": "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    "txt": "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
};
const defaultColor = "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200";
// ------------------------------------------------------------

// --- Props Interface ---
interface CollapsibleSidebarProps {
    isOpen: boolean;
    onToggle: () => void;
    selectedFilenames: Set<string>;
    onFilenameToggle: (filename: string | null) => void; // Callback for checkbox changes
    triggerRefresh: number; // To trigger list refresh externally
    onDocumentsManaged: () => void; // Callback after modal actions (e.g., deletion)
    uploadDropdownRef: React.RefObject<UploadDropdownRef | null>; // Ref to trigger upload
}

export default function CollapsibleSidebar({
    isOpen,
    onToggle,
    selectedFilenames,
    onFilenameToggle,
    triggerRefresh,
    onDocumentsManaged,
    uploadDropdownRef
}: CollapsibleSidebarProps) {

    // --- State for Document List within Sidebar ---
    const [documents, setDocuments] = useState<DocumentInfo[]>([]);
    const [filteredDocuments, setFilteredDocuments] = useState<DocumentInfo[]>([]);
    const [docsLoading, setDocsLoading] = useState(false);
    const [docsError, setDocsError] = useState<string | null>(null);
    const [filterTerm, setFilterTerm] = useState('');
    const [isManageModalOpen, setIsManageModalOpen] = useState(false); // Control modal visibility


    // --- Fetch Documents ---
    const fetchDocuments = useCallback(async () => {
        setDocsLoading(true);
        setDocsError(null);
        console.log("Sidebar: Fetching documents...");
        try {
            const list = await getDocumentList();
            const sortedDocs = (list.documents || []).sort((a, b) =>
                a.filename.toLowerCase().localeCompare(b.filename.toLowerCase())
            );
            setDocuments(sortedDocs);
            setFilteredDocuments(sortedDocs); // Initialize filtered list
        } catch (err: any) {
            setDocsError(err.message || 'Failed to load document list.');
            console.error("Sidebar fetch error:", err);
        } finally {
            setDocsLoading(false);
        }
    }, []);

    // Fetch on initial mount and when external trigger changes
    useEffect(() => {
        fetchDocuments();
    }, [fetchDocuments, triggerRefresh]);

    // --- Filter Logic ---
    useEffect(() => {
        if (!filterTerm) {
            setFilteredDocuments(documents); // No filter, show all
        } else {
            const lowerCaseFilter = filterTerm.toLowerCase();
            setFilteredDocuments(
                documents.filter(doc =>
                    doc.filename.toLowerCase().includes(lowerCaseFilter) ||
                    (doc.tag && doc.tag.toLowerCase().includes(lowerCaseFilter))
                )
            );
        }
    }, [filterTerm, documents]);

    // --- Event Handlers ---
    const handleUploadTrigger = (tagValue?: string) => {
        uploadDropdownRef.current?.triggerUpload(tagValue);
        // Optionally close sidebar after triggering upload?
        // if (isOpen) onToggle();
    };

    const handleCheckboxChange = (filename: string, checked: boolean | 'indeterminate') => {
        // Checkbox component gives boolean or 'indeterminate'
        if (checked === true) {
             onFilenameToggle(filename); // Add filename
        } else if (checked === false) {
             onFilenameToggle(filename); // Remove filename
        }
        // 'indeterminate' state is visual only, shouldn't trigger logic change here
    };

    const handleSelectAllDocs = (checked: boolean | 'indeterminate') => {
         if (checked) {
            onFilenameToggle(null); // Pass null to clear selection (selects "All")
         }
         // Cannot uncheck "All" directly, must select specific files
    };

    // Close modal and refresh list after management actions
    const handleModalClose = (refreshNeeded: boolean) => {
        setIsManageModalOpen(false);
        if (refreshNeeded) {
             onDocumentsManaged(); // Trigger refresh in parent (which updates triggerRefresh prop)
        }
    }

    // --- Helper Functions ---
    const getTagBadgeClasses = (tagValue: string | null | undefined): string => {
        if (!tagValue) return defaultColor;
        return tagColorClasses[tagValue.toLowerCase()] || defaultColor;
    };
    const getFileTypeBadgeClasses = (fileTypeValue: string | null | undefined): string => {
        if (!fileTypeValue) return defaultColor;
        return fileTypeColorClasses[fileTypeValue.toLowerCase()] || defaultColor;
    };


    // --- Render ---
    return (
        <Dialog open={isManageModalOpen} onOpenChange={setIsManageModalOpen}>
            <TooltipProvider delayDuration={100}>
                <div className={cn(
                    "relative flex flex-col bg-card border-r overflow-hidden transition-width duration-300 ease-in-out",
                    isOpen ? 'w-72' : 'w-16' // Width changes based on state
                )}>
                    {/* Toggle Button - Positioned for easy access */}
                     <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={onToggle}
                                className="absolute top-3 right-3 h-7 w-7 z-20" // Smaller toggle button
                                aria-label={isOpen ? "Collapse Sidebar" : "Expand Sidebar"}
                            >
                                {isOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="right">
                            <p>{isOpen ? "Collapse Sidebar" : "Expand Sidebar"}</p>
                        </TooltipContent>
                    </Tooltip>

                    {/* Expanded Content */}
                    <div className={cn(
                        "flex flex-col h-full transition-opacity duration-200 ease-in-out",
                        isOpen ? "opacity-100" : "opacity-0 pointer-events-none" // Fade in/out content
                    )}>
                        <h2 className="text-lg font-semibold p-4 pb-2 flex-shrink-0">Documents</h2>

                        {/* Upload Buttons Area */}
                        <div className="px-4 pb-2 flex-shrink-0 border-b">
                            <p className="text-xs text-muted-foreground mb-2">Quick Upload:</p>
                             <div className="grid grid-cols-3 gap-1">
                                 {uploadTags.map(tag => (
                                    <Tooltip key={tag.value}>
                                        <TooltipTrigger asChild>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="h-8 px-2 justify-start gap-1"
                                                onClick={() => handleUploadTrigger(tag.value)}
                                            >
                                                <tag.icon size={14} className="text-muted-foreground" />
                                                <span className="text-xs truncate">{tag.label}</span>
                                            </Button>
                                        </TooltipTrigger>
                                        <TooltipContent side="bottom">
                                            <p>Upload {tag.label}</p>
                                        </TooltipContent>
                                    </Tooltip>
                                 ))}
                                  <Tooltip>
                                      <TooltipTrigger asChild>
                                          <Button variant="outline" size="sm" className="h-8 px-2 justify-start gap-1" onClick={() => handleUploadTrigger()}>
                                              <FileUp size={14} className="text-muted-foreground"/>
                                              <span className="text-xs truncate">Other</span>
                                          </Button>
                                      </TooltipTrigger>
                                      <TooltipContent side="bottom"><p>Upload without Tag</p></TooltipContent>
                                  </Tooltip>
                            </div>
                        </div>

                        {/* Filter and Refresh Area */}
                        <div className="p-4 pb-2 flex-shrink-0 border-b space-y-2">
                            <div className="relative">
                                <Search size={16} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                                <Input
                                    type="text"
                                    placeholder="Filter by name or tag..."
                                    className="pl-8 h-8 text-xs"
                                    value={filterTerm}
                                    onChange={(e) => setFilterTerm(e.target.value)}
                                />
                            </div>
                             <Button variant="ghost" size="sm" onClick={fetchDocuments} disabled={docsLoading} className="w-full justify-center text-xs h-7">
                                 <RefreshCw size={14} className={cn("mr-1", docsLoading && 'animate-spin')} />
                                  Refresh List
                             </Button>
                        </div>

                        {/* Document List Area */}
                        <ScrollArea className="flex-grow p-4 pt-2">
                            {docsLoading && <p className="text-xs text-muted-foreground text-center py-4">Loading...</p>}
                            {docsError && <p className="text-xs text-destructive text-center py-4">{docsError}</p>}
                            {!docsLoading && !docsError && (
                                <div className="space-y-1">
                                    {/* "All Documents" Option */}
                                    <div className="flex items-center space-x-2 py-1.5 px-1 rounded hover:bg-muted/50">
                                        <Checkbox
                                            id="select-all-docs"
                                            checked={selectedFilenames.size === 0} // Checked if no specific files are selected
                                            onCheckedChange={handleSelectAllDocs}
                                            aria-label="Select all documents"
                                         />
                                        <label
                                            htmlFor="select-all-docs"
                                            className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer grow"
                                            onClick={() => handleSelectAllDocs(true)} // Allow clicking label
                                        >
                                            All Documents
                                        </label>
                                    </div>

                                    {/* Separator */}
                                    <hr className="my-1 border-border/50" />

                                    {/* Filtered Document List */}
                                     {filteredDocuments.length === 0 && filterTerm && <p className="text-xs text-muted-foreground text-center py-4">No matches found.</p>}
                                     {filteredDocuments.length === 0 && !filterTerm && <p className="text-xs text-muted-foreground text-center py-4">No documents uploaded yet.</p>}

                                    {filteredDocuments.map((doc) => (
                                        <div key={doc.filename} className="flex items-center space-x-2 py-1.5 px-1 rounded hover:bg-muted/50 group">
                                            <Checkbox
                                                id={`doc-${doc.filename}`}
                                                checked={selectedFilenames.has(doc.filename)}
                                                onCheckedChange={(checked) => handleCheckboxChange(doc.filename, checked)}
                                                aria-label={`Select ${doc.filename}`}
                                            />
                                            <label
                                                htmlFor={`doc-${doc.filename}`}
                                                className="text-sm leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer grow overflow-hidden flex flex-col"
                                                onClick={() => handleCheckboxChange(doc.filename, !selectedFilenames.has(doc.filename))} // Allow clicking label
                                            >
                                                 {/* File Info Row */}
                                                <div className="flex items-center gap-1.5 truncate mb-0.5">
                                                    {/* File Type Badge */}
                                                    {doc.file_type && (
                                                        <span className={cn(
                                                            "shrink-0 rounded px-1 py-0.5 text-[9px] font-semibold leading-none border",
                                                            getFileTypeBadgeClasses(doc.file_type)
                                                        )}>
                                                            {doc.file_type.toUpperCase()}
                                                        </span>
                                                    )}
                                                    {/* Filename */}
                                                    <span className="truncate" title={doc.filename}>{doc.filename}</span>
                                                </div>
                                                 {/* Tag Row (if tag exists) */}
                                                 {doc.tag && (
                                                     <div className="mt-0.5">
                                                         <Badge
                                                             variant="secondary"
                                                             className={cn(
                                                                 "text-[10px] h-auto py-0 px-1.5 border",
                                                                 getTagBadgeClasses(doc.tag)
                                                             )}
                                                          >
                                                             {doc.tag}
                                                         </Badge>
                                                     </div>
                                                 )}
                                            </label>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </ScrollArea>

                        {/* Manage Documents Button */}
                        <div className="p-4 pt-2 border-t flex-shrink-0">
                             <DialogTrigger asChild>
                                 <Button variant="outline" size="sm" className="w-full text-xs h-8">
                                     <Settings size={14} className="mr-1.5" /> Manage Documents
                                 </Button>
                             </DialogTrigger>
                        </div>
                    </div>

                    {/* Collapsed Content (Icons) */}
                    <div className={cn(
                        "flex flex-col items-center pt-4 space-y-4 transition-opacity duration-200 ease-in-out",
                        !isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
                    )}>
                         <Tooltip>
                             <TooltipTrigger asChild>
                                 <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => handleUploadTrigger()}>
                                     <Upload size={18}/>
                                 </Button>
                             </TooltipTrigger>
                             <TooltipContent side="right"><p>Upload Document</p></TooltipContent>
                         </Tooltip>
                         <Tooltip>
                             <TooltipTrigger asChild>
                                 {/* This button now just toggles the sidebar open */}
                                 <Button variant="ghost" size="icon" className="h-9 w-9" onClick={onToggle}>
                                     <FileText size={18}/>
                                 </Button>
                             </TooltipTrigger>
                             <TooltipContent side="right"><p>View Documents</p></TooltipContent>
                         </Tooltip>
                         <Tooltip>
                             <TooltipTrigger asChild>
                                 <DialogTrigger asChild>
                                     <Button variant="ghost" size="icon" className="h-9 w-9">
                                         <Settings size={18}/>
                                     </Button>
                                 </DialogTrigger>
                             </TooltipTrigger>
                             <TooltipContent side="right"><p>Manage Documents</p></TooltipContent>
                         </Tooltip>
                    </div>
                </div>
                {/* Manage Documents Modal Content */}
                {/* Pass callback to handle refresh after deletion */}
                 <ManageDocumentsModal triggerRefresh={() => handleModalClose(true)} />
             </TooltipProvider>
        </Dialog>
    );
}