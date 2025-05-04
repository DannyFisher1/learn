'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
    DropdownMenuSub,
    DropdownMenuSubContent,
    DropdownMenuSubTrigger,
    DropdownMenuCheckboxItem,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogTrigger } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  ReloadIcon,
  UploadIcon,
  BookmarkIcon as TagIcon,
  DotsVerticalIcon,
  FileTextIcon,
  DesktopIcon,
  ReaderIcon,
  HomeIcon,
  IdCardIcon,
  QuestionMarkCircledIcon,
  MixerHorizontalIcon,
} from '@radix-ui/react-icons';
import { cn } from '@/lib/utils';
import { getDocumentList, DocumentInfo } from '@/lib/api';
import { UploadDropdownRef } from '../common/UploadDropdown';
import ManageDocumentsModal from '../modals/ManageDocumentsModal';

// --- Constants (Consider moving to lib/constants.ts) ---
const ALL_DOCUMENTS_VALUE = 'all'; // Define constant for clarity
const uploadTags = [
    { label: "Textbook", value: "textbook", icon: FileTextIcon },
    { label: "Lecture Slides", value: "slides", icon: DesktopIcon },
    { label: "Notes", value: "notes", icon: ReaderIcon },
    { label: "Homework", value: "homework", icon: HomeIcon },
    { label: "Quiz/Exam", value: "quiz", icon: IdCardIcon },
    { label: "General", value: "general", icon: QuestionMarkCircledIcon },
];
const tagColorClasses: { [key: string]: string } = {
    "textbook": "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    "slides":   "bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200",
    "notes":    "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
    "homework": "bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200",
    "quiz":     "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
    "general":  "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200",
};
const defaultTagColor = "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200";
// ------------------------------------------------------

interface ChatOptionsMenuProps {
    selectedFilenames: Set<string>;
    onFilenameToggle: (filename: string | null) => void;
    uploadDropdownRef: React.RefObject<UploadDropdownRef | null>;
    triggerDocListRefresh: number;
    onDocumentsManaged: () => void;
}

export default function ChatOptionsMenu({ 
    selectedFilenames, 
    onFilenameToggle,
    uploadDropdownRef,
    triggerDocListRefresh,
    onDocumentsManaged
}: ChatOptionsMenuProps) {
    // State for document list within the dropdown
    const [documents, setDocuments] = useState<DocumentInfo[]>([]);
    const [docsLoading, setDocsLoading] = useState(false);
    const [docsError, setDocsError] = useState<string | null>(null);

    // Fetch documents when the dropdown opens or refresh is triggered
    const fetchDocumentsForDropdown = useCallback(async () => {
        setDocsLoading(true);
        setDocsError(null);
        console.log("ChatOptionsMenu: Fetching documents...");
        try {
            const list = await getDocumentList();
            setDocuments(list.documents || []);
        } catch (err: any) {
            setDocsError(err.message || 'Failed to load document list.');
            console.error("ChatOptionsMenu fetch error:", err);
        } finally {
            setDocsLoading(false);
        }
    }, []);

    useEffect(() => {
        // Fetch immediately if trigger changes (for external refresh)
        if (triggerDocListRefresh > 0) { // Check prevents initial fetch if trigger starts at 0
             fetchDocumentsForDropdown();
        }
    }, [fetchDocumentsForDropdown, triggerDocListRefresh]);

    // Function to trigger upload from menu item
    const handleUploadMenuItemSelect = (tagValue?: string) => {
        uploadDropdownRef.current?.triggerUpload(tagValue);
    };

    // Helper function to get badge classes for a tag
    const getTagBadgeClasses = (tagValue: string | null | undefined): string => {
        if (!tagValue) return defaultTagColor;
        return tagColorClasses[tagValue.toLowerCase()] || defaultTagColor;
    };

    return (
        <Dialog>
            <DropdownMenu onOpenChange={(open) => { if (open) fetchDocumentsForDropdown(); }}>
                <TooltipProvider delayDuration={100}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <DropdownMenuTrigger asChild>
                                 <Button variant="ghost" size="icon" className="h-9 w-9 flex-shrink-0 self-end mb-[1px]">
                                     <DotsVerticalIcon className="h-4 w-4" />
                                     <span className="sr-only">Options</span>
                                 </Button>
                            </DropdownMenuTrigger>
                        </TooltipTrigger>
                        <TooltipContent side="top"><p>Upload & Scope Options</p></TooltipContent>
                    </Tooltip>
                </TooltipProvider>
                <DropdownMenuContent align="start" className="w-64">
                    <DropdownMenuLabel>Actions</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    {/* Upload Section */}
                    <DropdownMenuSub>
                        <DropdownMenuSubTrigger>
                             <UploadIcon className="mr-2 h-4 w-4" />
                             <span>Upload Document</span>
                        </DropdownMenuSubTrigger>
                        <DropdownMenuSubContent>
                            {uploadTags.map((tagInfo) => (
                                <DropdownMenuItem
                                    key={tagInfo.value}
                                    onSelect={() => handleUploadMenuItemSelect(tagInfo.value)}
                                    className="flex items-center gap-2 cursor-pointer"
                                >
                                    <tagInfo.icon className="h-4 w-4 text-muted-foreground" />
                                    <span>{tagInfo.label}</span>
                                </DropdownMenuItem>
                            ))}
                             <DropdownMenuSeparator />
                              <DropdownMenuItem
                                 onSelect={() => handleUploadMenuItemSelect()} // Trigger with no tag
                                 className="flex items-center gap-2 cursor-pointer"
                             >
                                 <UploadIcon className="h-4 w-4 text-muted-foreground" />
                                 <span>Upload without Tag</span>
                             </DropdownMenuItem>
                        </DropdownMenuSubContent>
                    </DropdownMenuSub>
                    {/* Document Scope Section */}
                    <DropdownMenuSub>
                        <DropdownMenuSubTrigger>
                            <TagIcon className="mr-2 h-4 w-4" />
                            <span>Select Document Scope</span>
                        </DropdownMenuSubTrigger>
                        <DropdownMenuSubContent>
                            <DropdownMenuCheckboxItem
                                checked={selectedFilenames.size === 0}
                                onCheckedChange={(checked) => {
                                    if (checked) {
                                        onFilenameToggle(null);
                                    }
                                }}
                            >
                                All Uploaded Documents
                            </DropdownMenuCheckboxItem>
                            <DropdownMenuSeparator />
                            {docsLoading && <DropdownMenuItem disabled>...</DropdownMenuItem>}
                            {docsError && <DropdownMenuItem disabled>...</DropdownMenuItem>}
                            {!docsLoading && !docsError && documents.length === 0 && <DropdownMenuItem disabled>...</DropdownMenuItem>}
                            {!docsLoading && !docsError && documents.map((doc) => (
                                <DropdownMenuCheckboxItem
                                    key={doc.filename}
                                    checked={selectedFilenames.has(doc.filename)}
                                    onCheckedChange={() => onFilenameToggle(doc.filename)}
                                    className="justify-between gap-2 flex items-center"
                                >
                                    <div className="flex items-center gap-1.5 overflow-hidden">
                                        {/* File Type Indicator */}
                                        {doc.file_type && (
                                             <span className={cn(
                                                "shrink-0 rounded px-1 py-0.5 text-[10px] font-medium leading-none",
                                                doc.file_type.toLowerCase() === 'pdf' ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" :
                                                doc.file_type.toLowerCase() === 'docx' ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" :
                                                doc.file_type.toLowerCase() === 'txt' ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" :
                                                defaultTagColor
                                             )}>
                                                {doc.file_type.toUpperCase()}
                                            </span>
                                        )}
                                        {/* Filename */}
                                        <span className="truncate grow" title={doc.filename}>{doc.filename}</span>
                                    </div>
                                    {doc.tag && (
                                        <Badge
                                            className={cn(
                                                "text-xs shrink-0 border-transparent ml-auto",
                                                getTagBadgeClasses(doc.tag)
                                            )}
                                        >
                                            {doc.tag}
                                        </Badge>
                                    )}
                                </DropdownMenuCheckboxItem>
                            ))}
                        </DropdownMenuSubContent>
                    </DropdownMenuSub>
                    <DropdownMenuSeparator />
                    <DialogTrigger asChild>
                        <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                            <MixerHorizontalIcon className="mr-2 h-4 w-4" />
                            <span>Manage Documents</span>
                        </DropdownMenuItem>
                    </DialogTrigger>
                </DropdownMenuContent>
            </DropdownMenu>
            
            <ManageDocumentsModal triggerRefresh={onDocumentsManaged} />
        </Dialog>
    );
}
