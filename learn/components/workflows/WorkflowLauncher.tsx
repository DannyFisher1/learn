// components/workflows/WorkflowLauncher.tsx
'use client';

import React, { useState } from 'react';
import { zodResolver } from "@hookform/resolvers/zod";
import { Resolver, useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger, // Keep trigger separate or pass as prop
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea"; // For potentially longer inputs
import { StartDeepResearchPayload } from '@/lib/api'; // Import payload type
import { Play, Bot } from 'lucide-react'; // Icons

// --- Define Zod Schema for Deep Research Form ---
const deepResearchFormSchema = z.object({
  topic: z.string().min(5, { message: "Research topic must be at least 5 characters." }).max(200),
  depth: z.number().min(1).max(5).default(2),
  // Add max_sources_per_query, max_total_sources later if desired
});

type DeepResearchFormValues = z.infer<typeof deepResearchFormSchema>;

// --- Define available workflows ---
// Expand this later with more workflow types
type WorkflowType = 'deep_research' | 'project_generation' | 'summarize_document'; // Add more task_types here

interface WorkflowOption {
    type: WorkflowType;
    name: string;
    description: string;
    icon: React.ElementType;
}

const availableWorkflows: WorkflowOption[] = [
    { type: 'deep_research', name: 'Deep Research', description: 'Perform in-depth web research on a topic.', icon: Play },
    { type: 'project_generation', name: 'Generate Project', description: 'Generate code for a software project.', icon: Bot }, // Assuming this exists
    // Add more workflows here...
];

// --- Component Props ---
interface WorkflowLauncherProps {
    onStartJob: (taskType: string, params: any) => Promise<void>; // Function to call API
    children: React.ReactNode; // To wrap the trigger button passed from parent
}

export default function WorkflowLauncher({ onStartJob, children }: WorkflowLauncherProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowOption | null>(null);

    // --- Deep Research Form ---
    const researchForm = useForm<DeepResearchFormValues>({
        resolver: zodResolver(deepResearchFormSchema) as Resolver<DeepResearchFormValues>,
        defaultValues: {
            topic: "",
            depth: 2,
        },
    });

    async function onResearchSubmit(values: DeepResearchFormValues) {
        console.log("Submitting Deep Research:", values);
        // Type assertion for safety, ensure payload matches API expectation
        const payload: StartDeepResearchPayload = {
            topic: values.topic,
            depth: values.depth,
        };
        await onStartJob('deep_research', payload);
        setIsOpen(false); // Close dialog on success
        setSelectedWorkflow(null); // Reset selection
        researchForm.reset(); // Reset form
    }

    // --- Add forms and handlers for other workflows here ---
    // e.g., project generation form, document summarization form

    const renderWorkflowForm = () => {
        if (!selectedWorkflow) return null;

        switch (selectedWorkflow.type) {
            case 'deep_research':
                return (
                    <Form {...researchForm}>
                        <form onSubmit={researchForm.handleSubmit(onResearchSubmit)} className="space-y-4 pt-2">
                            <FormField
                                control={researchForm.control}
                                name="topic"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Research Topic</FormLabel>
                                        <FormControl>
                                            <Input placeholder="e.g., Advancements in mRNA vaccines since 2023" {...field} />
                                        </FormControl>
                                        <FormDescription> The main subject for the deep research. </FormDescription>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                             <FormField
                                control={researchForm.control}
                                name="depth"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Research Depth (1-5)</FormLabel>
                                         <FormControl>
                                            {/* Pass Slider value explicitly and handle change */}
                                            <div className='flex items-center gap-4 pt-2'>
                                                <Slider
                                                     min={1} max={5} step={1}
                                                     defaultValue={[field.value]} // Use defaultValue for initial render
                                                     onValueChange={(value) => field.onChange(value[0])} // Update form state on change
                                                     className="w-[80%]"
                                                 />
                                                 <span className='text-sm font-medium w-[10%] text-right'>{field.value}</span>
                                            </div>
                                         </FormControl>
                                        <FormDescription> How many rounds of query refinement (higher is deeper but slower). </FormDescription>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                            <DialogFooter>
                                <Button type="button" variant="ghost" onClick={() => setSelectedWorkflow(null)}>Back</Button>
                                <Button type="submit" disabled={researchForm.formState.isSubmitting}>
                                     {researchForm.formState.isSubmitting ? "Starting..." : "Start Research"}
                                 </Button>
                            </DialogFooter>
                        </form>
                    </Form>
                );
            // Add cases for other workflows...
            // case 'project_generation': return <ProjectGenForm ... />;
            default:
                return <p className="text-sm text-muted-foreground">Workflow form not implemented yet.</p>;
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={setIsOpen}>
            <DialogTrigger asChild>
                {/* The trigger button (e.g., "+ New Task") is passed as children */}
                {children}
            </DialogTrigger>
            <DialogContent className="sm:max-w-[450px]">
                {!selectedWorkflow ? (
                    <>
                        <DialogHeader>
                            <DialogTitle>Start New Workflow</DialogTitle>
                            <DialogDescription> Choose a task for the AI to perform. </DialogDescription>
                        </DialogHeader>
                        <div className="grid gap-3 py-4">
                            {availableWorkflows.map(wf => (
                                <Button
                                    key={wf.type}
                                    variant="outline"
                                    className="justify-start h-auto py-3"
                                    onClick={() => setSelectedWorkflow(wf)}
                                >
                                    <wf.icon className="w-5 h-5 mr-3 text-primary/80"/>
                                    <div className="text-left">
                                         <p className="font-medium text-sm">{wf.name}</p>
                                         <p className="text-xs text-muted-foreground">{wf.description}</p>
                                    </div>
                                </Button>
                            ))}
                        </div>
                        <DialogFooter>
                            <Button type="button" variant="ghost" onClick={() => setIsOpen(false)}>Cancel</Button>
                        </DialogFooter>
                    </>
                ) : (
                    <>
                        <DialogHeader>
                             <DialogTitle className="flex items-center gap-2">
                                 <selectedWorkflow.icon className="w-5 h-5 text-primary/80"/>
                                 {selectedWorkflow.name}
                             </DialogTitle>
                             <DialogDescription> {selectedWorkflow.description} Provide the required details below. </DialogDescription>
                        </DialogHeader>
                         {renderWorkflowForm()}
                    </>
                )}
            </DialogContent>
        </Dialog>
    );
}