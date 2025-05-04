// components/DocumentSelector.tsx
'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { getDocumentList, DocumentInfo } from '../lib/api';
import { // shadcn select components
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Button } from '@/components/ui/button'; // For optional refresh button
// --- Use Radix Icon --- 
// import { RefreshCw } from 'lucide-react'; // Icon for refresh
import { ReloadIcon } from '@radix-ui/react-icons';
// ----------------------
import { cn } from '@/lib/utils'; // Added cn import

interface DocumentSelectorProps {
    selectedDocument: string | null;
    onChange: (selection: string | null) => void;
    refreshTrigger: number; // Accept the trigger state
    disabled?: boolean;
}

const ALL_DOCUMENTS_VALUE = 'all';

export default function DocumentSelector({ selectedDocument, onChange, refreshTrigger, disabled }: DocumentSelectorProps) {
    const [documents, setDocuments] = useState<DocumentInfo[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchDocuments = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        console.log("DocumentSelector: Fetching documents..."); // Debug log
        try {
            const list = await getDocumentList();
            setDocuments(list.documents || []);
        } catch (err: any) {
            setError(err.message || 'Failed to load document list.');
            console.error("DocumentSelector fetch error:", err); // Log error
        } finally {
            setIsLoading(false);
        }
    }, []);

    // useEffect now depends on refreshTrigger
    useEffect(() => {
        fetchDocuments();
    }, [fetchDocuments, refreshTrigger]); // Add refreshTrigger here!

    const handleValueChange = (value: string) => {
        // If 'all' is selected, pass null. Otherwise, pass the filename.
        onChange(value === ALL_DOCUMENTS_VALUE ? null : value);
    };

    // Determine the value for the select element based on the prop
    const selectValue = selectedDocument === null ? ALL_DOCUMENTS_VALUE : selectedDocument;

    return (
        <div className="mb-4 space-y-2">
             <label htmlFor="doc-selector" className="block text-sm font-medium text-gray-700">
                Query Specific Document (Optional):
            </label>
            <div className="flex items-center gap-2">
                 <Select
                     value={selectValue}
                     onValueChange={handleValueChange}
                     disabled={isLoading || disabled}
                 >
                    <SelectTrigger id="doc-selector" className="flex-grow">
                        <SelectValue placeholder="Select document scope..." />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value={ALL_DOCUMENTS_VALUE}>All Uploaded Documents</SelectItem>
                        {isLoading && <SelectItem value="loading" disabled>Loading...</SelectItem>}
                        {!isLoading && documents.length === 0 && <SelectItem value="empty" disabled>No documents indexed</SelectItem>}
                        {documents.map((doc) => (
                            <SelectItem key={doc.filename} value={doc.filename}>
                                {doc.filename}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                {/* Optional Manual Refresh Button */}
                <Button variant="outline" size="icon" onClick={fetchDocuments} disabled={isLoading} aria-label="Refresh document list">
                     {/* --- Use Radix Icon --- */}
                     <ReloadIcon className={cn("h-4 w-4", isLoading && 'animate-spin')} />
                     {/* ---------------------- */}
                 </Button>
            </div>

            {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
             <p className="text-xs text-gray-500 mt-1">Select a file to focus the search, or choose 'All'.</p>
        </div>
    );
}