// app/page.tsx
'use client';

import React, { useState, useCallback } from 'react';
import ChatInterface from '@/components/ChatInterface';
import ThemeToggle from '@/components/ui/ThemeToggle';
import { MoreVertical } from 'lucide-react'; // Keep this if used elsewhere, or remove if only for sidebar

// Ensure KaTeX CSS is imported globally, e.g., in layout.tsx or globals.css

export default function Home() {
    // --- State for selected filenames (Set for easy add/remove) ---
    // const [selectedDocument, setSelectedDocument] = useState<string | null>(null);
    const [selectedFilenames, setSelectedFilenames] = useState<Set<string>>(new Set());
    // --------------------------------------------------------------
    const [selectedTag, setSelectedTag] = useState<string | null>(null);
    const [refreshDocListTrigger, setRefreshDocListTrigger] = useState(0);

    const triggerDocListRefresh = useCallback(() => {
        setRefreshDocListTrigger(prev => prev + 1);
        console.log("Document list refresh triggered from page.");
    }, []);

    // Handler for tag selection (if separate UI needed later)
    const handleTagSelection = (selection: string | null) => {
        console.log("Tag selection changed:", selection);
        setSelectedTag(selection);
    };

    // --- Handler to toggle a filename in the set ---
    const handleFilenameSelectionToggle = useCallback((filename: string | null) => {
        if (filename === null) { // Special case for 'All Documents'
            setSelectedFilenames(new Set()); // Clear selection
            return;
        }
        setSelectedFilenames(prev => {
            const newSet = new Set(prev);
            if (newSet.has(filename)) {
                newSet.delete(filename);
            } else {
                newSet.add(filename);
            }
            console.log("Selected filenames changed:", newSet);
            return newSet;
        });
    }, []);
    // -----------------------------------------------

    return (
        <main className="relative flex flex-col h-screen max-h-screen overflow-hidden">
            <div className="absolute top-4 right-4 z-10">
                <ThemeToggle />
            </div>

             {/* Header could potentially go here if needed */}

             {/* Chat Area Section - takes full height/width of main */}
             <section className="flex flex-col flex-grow overflow-hidden">
                 <ChatInterface
                     // --- Pass filenames set and toggle handler ---
                     // selectedDocument={selectedDocument}
                     // setSelectedDocument={setSelectedDocument}
                     selectedFilenames={selectedFilenames}
                     onFilenameToggle={handleFilenameSelectionToggle}
                     // ---------------------------------------------
                     selectedTag={selectedTag}
                     triggerDocListRefresh={refreshDocListTrigger}
                     // --- Pass the actual refresh function ---
                     onDocumentsManaged={triggerDocListRefresh} 
                     // ----------------------------------------
                 />
             </section>

             {/* Optional Footer */}
             {/* ... */}
        </main>
    );
}