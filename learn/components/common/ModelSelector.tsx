// components/ModelSelector.tsx
'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button'; // Import shadcn Button
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuLabel,
    DropdownMenuRadioGroup,
    DropdownMenuRadioItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'; // Import shadcn DropdownMenu components
// --- Use Radix Icons --- 
// import { Check, ChevronDown, Loader2, Settings } from 'lucide-react'; // Icons
import { CheckIcon, ChevronDownIcon, ReloadIcon, GearIcon } from '@radix-ui/react-icons';
// -----------------------
import { getCurrentProvider, switchProvider, ProviderStatus, SetProviderPayload } from '@/lib/api';
import { cn } from '@/lib/utils'; // Import your cn utility

type ProviderOption = 'ollama' | 'openai';

export default function ModelSelector() {
    // State specifically for this component
    const [currentProvider, setCurrentProvider] = useState<ProviderOption | null>(null);
    const [isLoadingStatus, setIsLoadingStatus] = useState(true); // Loading initial status
    const [isSwitching, setIsSwitching] = useState(false); // Loading during switch
    const [error, setError] = useState<string | null>(null);

    // Fetch initial provider status
    const fetchStatus = useCallback(async () => {
        setIsLoadingStatus(true);
        setError(null);
        try {
            const status = await getCurrentProvider();
            // Ensure the fetched provider is one of the expected types
            if (status.current_provider === 'ollama' || status.current_provider === 'openai') {
               setCurrentProvider(status.current_provider);
            } else {
               // Handle unexpected provider value from backend (e.g., default or log error)
               console.warn(`Received unexpected provider status: ${status.current_provider}, defaulting display.`);
               setCurrentProvider('ollama'); // Or set to null or show a specific error state
            }
        } catch (err: any) {
            setError('Failed to load status');
            console.error("ModelSelector fetchStatus error:", err);
        } finally {
            setIsLoadingStatus(false);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
    }, [fetchStatus]);

    // Handle the switch when a radio item is selected
    const handleSwitch = async (newProviderValue: string) => {
        // Type assertion needed as onValueChange provides string
        const newProvider = newProviderValue as ProviderOption;

        if ((newProvider === 'ollama' || newProvider === 'openai') && newProvider !== currentProvider) {
            setIsSwitching(true);
            setError(null);
            const payload: SetProviderPayload = { provider: newProvider };
            try {
                const result = await switchProvider(payload);
                // Verify the provider actually switched on the backend if needed,
                // but for UI responsiveness, update the state immediately.
                setCurrentProvider(newProvider);
                console.log("Provider switch result:", result.message);
            } catch (err: any) {
                const errorMsg = err.message || 'An unknown error occurred.';
                setError(`Switch failed: ${errorMsg.substring(0, 100)}`); // Truncate long messages
                console.error("ModelSelector handleSwitch error:", err);
                // Re-fetch status on error to sync with actual backend state
                fetchStatus();
            } finally {
                setIsSwitching(false);
            }
        }
    };

    // Determines the text/label for the dropdown trigger button
    const getTriggerLabel = () => {
        if (isLoadingStatus) return "Status..."; // Indicate initial loading
        if (error && !isSwitching) return "Error"; // Show error only if not switching
        if (currentProvider === 'ollama') return "Ollama";
        if (currentProvider === 'openai') return "OpenAI";
        return "Select Model"; // Fallback/initial state before status known
    };

    return (
        <DropdownMenu>
            {/* Dropdown Trigger: Now an icon button */}
            <DropdownMenuTrigger asChild disabled={isSwitching || isLoadingStatus}>
                <Button
                    variant="ghost"
                    size="icon"
                    className={cn(
                        "h-9 w-9 flex items-center justify-center p-0", // Icon button style
                        (isSwitching || isLoadingStatus) && "cursor-not-allowed opacity-70"
                    )}
                    aria-label="Model settings"
                >
                    {isSwitching ? (
                        // --- Use Radix Icon --- 
                        <ReloadIcon className="h-5 w-5 animate-spin" />
                    ) : (
                        // --- Use Radix Icon --- 
                        <GearIcon className="h-5 w-5" />
                        // -----------------------
                    )}
                </Button>
            </DropdownMenuTrigger>

            {/* Dropdown Content: The menu that appears on click */}
            <DropdownMenuContent className="w-48" align="end"> {/* Align to the right */}
                <DropdownMenuLabel>AI Provider</DropdownMenuLabel>
                <DropdownMenuSeparator />

                {/* Radio Group for selecting the provider */}
                <DropdownMenuRadioGroup
                    value={currentProvider ?? ""} // Controlled component based on state
                    onValueChange={handleSwitch} // Call handler when selection changes
                >
                    {/* Option 1: Ollama */}
                    <DropdownMenuRadioItem value="ollama" disabled={isSwitching}>
                        {/* Check icon is rendered automatically by shadcn */}
                        {/* Radix CheckIcon might not be needed if shadcn handles it */} 
                        Ollama (Local)
                    </DropdownMenuRadioItem>

                    {/* Option 2: OpenAI */}
                    <DropdownMenuRadioItem value="openai" disabled={isSwitching}>
                        OpenAI (Cloud)
                    </DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>

                {/* Display error message if a switch fails */}
                {error && !isSwitching && (
                    <>
                        <DropdownMenuSeparator />
                        <div className="px-2 py-1.5 text-xs text-destructive">
                            {error}
                        </div>
                    </>
                )}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}