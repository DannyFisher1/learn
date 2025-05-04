// components/UploadDropdown.tsx
'use client';

import React, { useState, useRef, useImperativeHandle, forwardRef } from 'react';
import { Button } from '@/components/ui/button';
// --- Remove unused Dropdown imports --- 
// import {
//     DropdownMenu,
//     DropdownMenuContent,
//     DropdownMenuItem,
//     DropdownMenuLabel,
//     DropdownMenuSeparator,
//     DropdownMenuTrigger,
// } from '@/components/ui/dropdown-menu';
// -------------------------------------
// --- Import required Radix Icons if any logic remains that uses them --- 
import { UploadIcon, ReloadIcon } from '@radix-ui/react-icons'; // Example, if needed by commented out code
// ---------------------------------------------------------------------
import { uploadFile, UploadFilePayload } from '@/lib/api'; // Ensure UploadFilePayload matches the updated one
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

// --- Define the tags/categories (icons not needed here anymore) --- 
// const uploadTags = [
//     { label: "Textbook", value: "textbook" },
//     { label: "Lecture Slides", value: "slides" },
//     { label: "Notes", value: "notes" },
//     { label: "Homework", value: "homework" },
//     { label: "Quiz/Exam", value: "quiz" },
//     { label: "General", value: "general" },
// ];
// -----------------------------------------------------------------

interface UploadDropdownProps {
    onUploadComplete?: (success: boolean) => void;
}

// --- Define Ref Handle Type ---
export interface UploadDropdownRef {
    triggerUpload: (tag?: string) => void;
}
// -----------------------------

// --- Use forwardRef ---
const UploadDropdown = forwardRef<UploadDropdownRef, UploadDropdownProps>(({ onUploadComplete }, ref) => {
    const [isUploading, setIsUploading] = useState(false);
    // Keep track of the tag selected *just before* clicking the input
    const [currentUploadTag, setCurrentUploadTag] = useState<string | undefined>(undefined);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (event.target) {
            event.target.value = ''; // Reset input
        }
        if (!file) return;

        // --- Update File Type Validation --- 
        const allowedExtensions = [".pdf", ".txt", ".docx"];
        const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();

        if (!allowedExtensions.includes(fileExtension)) {
            toast.error("Invalid File Type", { description: `Please select a PDF, TXT, or DOCX file. Allowed: ${allowedExtensions.join(', ')}` });
            return;
        }
        // ---------------------------------

        setIsUploading(true);
        const payload: UploadFilePayload = {
            file: file,
            // Use the tag that was set when the input was triggered
            tag: currentUploadTag,
        };
        let uploadSuccess = false;
        const toastId = toast.loading(`Uploading ${file.name}...`, {
             description: `Tag: ${currentUploadTag || 'None Selected'}`,
        });

        try {
            const result = await uploadFile(payload); // Call API
            toast.success("Upload Successful", {
                id: toastId,
                description: `${result.filename} processed.`,
            });
            uploadSuccess = true;
        } catch (error: any) {
            const errorMsg = error.message || "An unknown error occurred.";
            toast.error("Upload Failed", {
                id: toastId,
                description: errorMsg.substring(0, 100),
            });
            console.error("Upload error:", error);
            uploadSuccess = false;
        } finally {
            setIsUploading(false);
            setCurrentUploadTag(undefined); // Clear the tag after upload attempt
            if (onUploadComplete) {
                onUploadComplete(uploadSuccess);
            }
        }
    };

    // --- Expose function via ref handle ---
    useImperativeHandle(ref, () => ({
        triggerUpload: (tag?: string) => {
            if (!isUploading && fileInputRef.current) {
                setCurrentUploadTag(tag); // Set the tag for the upcoming upload
                fileInputRef.current.click(); // Trigger hidden file input
            }
        }
    }));
    // -------------------------------------

    // --- Keep rendering the hidden input. The original button/dropdown can be optionally removed/hidden later. ---
    return (
        <>
            <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileSelect}
                accept=".pdf,.txt,.docx"
                style={{ display: 'none' }}
                disabled={isUploading}
                aria-label="File input for upload"
            />

            {/* Original Trigger - Can be conditionally rendered or removed if only programmatic trigger is desired */}
            {/* <DropdownMenu>
                <DropdownMenuTrigger asChild disabled={isUploading}>
                    <Button ...>
                        {isUploading ? <Loader2 /> : <Upload />}
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent ...>
                    {uploadTags.map((tagInfo) => (
                        <DropdownMenuItem
                            key={tagInfo.value}
                            disabled={isUploading}
                            onSelect={() => {
                                // This manual trigger still works if button is rendered
                                useImperativeHandle.triggerUpload(tagInfo.value)
                            }}
                        >
                            <tagInfo.icon />
                            <span>{tagInfo.label}</span>
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu> */}
        </>
    );
});

UploadDropdown.displayName = "UploadDropdown"; // Add display name for DevTools

export default UploadDropdown;