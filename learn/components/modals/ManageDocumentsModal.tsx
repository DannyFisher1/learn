'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
    DialogClose,
} from "@/components/ui/dialog";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getDocumentList, deleteDocument, DocumentInfo } from '@/lib/api';
import { TrashIcon, ReloadIcon, BookmarkIcon as TagIcon } from '@radix-ui/react-icons';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

// --- Re-add color constants (or import from constants file) ---
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

interface ManageDocumentsModalProps {
    // Renamed prop to be more explicit
    triggerRefresh: () => void; 
}

export default function ManageDocumentsModal({ triggerRefresh }: ManageDocumentsModalProps) {
    const [documents, setDocuments] = useState<DocumentInfo[]>([]);
    const [isLoadingList, setIsLoadingList] = useState(false);
    const [isDeleting, setIsDeleting] = useState<string | null>(null); // Store filename being deleted
    const [error, setError] = useState<string | null>(null);

    const fetchDocuments = useCallback(async () => {
        setIsLoadingList(true);
        setError(null);
        try {
            const list = await getDocumentList();
            setDocuments(list.documents || []);
        } catch (err: any) {
            setError(err.message || 'Failed to load document list.');
            console.error("ManageDocs fetch error:", err);
        } finally {
            setIsLoadingList(false);
        }
    }, []);

    // Fetch documents when the modal opens
    useEffect(() => {
        fetchDocuments();
    }, [fetchDocuments]);

    const handleDeleteClick = async (filename: string) => {
        setIsDeleting(filename); // Show loading state on the specific button
        setError(null);
        try {
            await deleteDocument(filename);
            toast.success(`Document '${filename}' has been removed.`);
            await fetchDocuments(); // Refresh list within the modal
            triggerRefresh();      // Trigger refresh in parent components (like options menu)
        } catch (err: any) {
            const errorMsg = err.message || "Failed to delete document.";
            setError(errorMsg); // Show error specific to this modal
            toast.error(`Failed to delete '${filename}'`, { description: errorMsg.substring(0, 100) });
            console.error(`Delete error for ${filename}:`, err);
        } finally {
            setIsDeleting(null); // Clear loading state
        }
    };

    // Helper to get tag badge classes
    const getTagBadgeClasses = (tagValue: string | null | undefined): string => {
        if (!tagValue) return defaultColor;
        return tagColorClasses[tagValue.toLowerCase()] || defaultColor;
    };

    // Helper to get file type badge classes
    const getFileTypeBadgeClasses = (fileTypeValue: string | null | undefined): string => {
        if (!fileTypeValue) return defaultColor;
        return fileTypeColorClasses[fileTypeValue.toLowerCase()] || defaultColor;
    };


    return (
        <DialogContent className="sm:max-w-lg"> {/* Increased width slightly */}
            <DialogHeader>
                <DialogTitle>Manage Uploaded Documents</DialogTitle>
                <DialogDescription>
                    View details and remove documents from the knowledge base. Deletion is permanent.
                </DialogDescription>
            </DialogHeader>

            {error && <p className="text-sm text-destructive my-2 text-center px-6">{error}</p>}

            <div className="max-h-[65vh] py-4"> {/* Increased max height */}
                 <div className="flex justify-end mb-2 px-6"> {/* Added padding */}
                     <Button variant="ghost" size="sm" onClick={fetchDocuments} disabled={isLoadingList} aria-label="Refresh document list">
                        <ReloadIcon className={cn("h-4 w-4 mr-1", isLoadingList && 'animate-spin')} />
                         Refresh List
                     </Button>
                 </div>
                <ScrollArea className="h-[55vh] border rounded-md mx-6"> {/* Added padding */}
                    {isLoadingList && (
                        <div className="flex items-center justify-center p-6 h-full">
                           <ReloadIcon className="h-6 w-6 animate-spin text-muted-foreground" />
                           <span className="ml-2 text-muted-foreground">Loading documents...</span>
                        </div>
                    )}
                    {!isLoadingList && documents.length === 0 && (
                        <p className="text-center text-muted-foreground p-6">No documents found.</p>
                    )}
                    {!isLoadingList && documents.length > 0 && (
                        <ul className="space-y-1 p-2"> {/* Reduced spacing slightly */}
                            {documents.map((doc) => (
                                <li key={doc.filename} className="flex items-center justify-between p-2 rounded hover:bg-muted/50 group">
                                    {/* File Info */}
                                    <div className="flex items-center gap-2 overflow-hidden mr-2">
                                         {/* File Type Badge */}
                                         {doc.file_type && (
                                             <span className={cn(
                                                "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium leading-none",
                                                getFileTypeBadgeClasses(doc.file_type)
                                             )}>
                                                {doc.file_type.toUpperCase()}
                                            </span>
                                         )}
                                         {/* Filename */}
                                        <span className="text-sm font-medium truncate" title={doc.filename}>
                                            {doc.filename}
                                        </span>
                                        {/* User Tag Badge */}
                                        {doc.tag && (
                                            <Badge
                                                variant="secondary" // Use variant for base styling, override bg/text below
                                                className={cn(
                                                    "text-xs shrink-0 border-transparent", // Base styles
                                                    getTagBadgeClasses(doc.tag) // Color styles
                                                )}
                                             >
                                                {doc.tag}
                                            </Badge>
                                        )}
                                    </div>

                                    {/* Delete Button (with Confirmation) */}
                                    <AlertDialog>
                                        <AlertDialogTrigger asChild>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className={cn(
                                                    "h-7 w-7 text-muted-foreground hover:text-destructive/90 flex-shrink-0",
                                                    // Make delete visible on hover/focus for cleaner look
                                                    "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity",
                                                    isDeleting === doc.filename && "opacity-100" // Always show if deleting
                                                )}
                                                disabled={isDeleting === doc.filename}
                                                aria-label={`Delete ${doc.filename}`}
                                            >
                                                {isDeleting === doc.filename ? (
                                                    <ReloadIcon className="h-4 w-4 animate-spin" />
                                                ) : (
                                                    <TrashIcon className="h-4 w-4" />
                                                )}
                                            </Button>
                                        </AlertDialogTrigger>
                                        <AlertDialogContent>
                                            <AlertDialogHeader>
                                                <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
                                                <AlertDialogDescription>
                                                    This action cannot be undone. This will permanently delete all data associated with the document:
                                                    <br /><strong className="break-all">{doc.filename}</strong> 
                                                    {doc.tag ? ` (Tag: ${doc.tag})` : ''}
                                                    {doc.file_type ? ` [Type: ${doc.file_type}]` : ''}
                                                </AlertDialogDescription>
                                            </AlertDialogHeader>
                                            <AlertDialogFooter>
                                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                                <AlertDialogAction
                                                    onClick={() => handleDeleteClick(doc.filename)}
                                                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                                 >
                                                    Yes, Delete Document
                                                 </AlertDialogAction>
                                            </AlertDialogFooter>
                                        </AlertDialogContent>
                                    </AlertDialog>
                                </li>
                            ))}
                        </ul>
                    )}
                </ScrollArea>
            </div>

            <DialogFooter className="sm:justify-end px-6 pb-4"> {/* Added padding */}
                <DialogClose asChild>
                    <Button type="button" variant="secondary">
                        Close
                    </Button>
                </DialogClose>
            </DialogFooter>
        </DialogContent>
    );
}
