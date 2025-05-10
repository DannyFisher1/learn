// learn/components/layout/JobItem.tsx
'use client';

import React from 'react';
import {
    JobListResponseItem, JobStatus,
    JOB_STATUS_PENDING, JOB_STATUS_RUNNING, JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED, JOB_STATUS_CANCELED
} from '@/lib/api';
import { Button, buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
    Loader2, CheckCircle2, XCircle, Ban, Eye, FileClock, Bot, FlaskConical, FileTextIcon, X as XIcon,
    Trash2 // Icon for permanent delete
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import {
    Tooltip, TooltipContent, TooltipProvider, TooltipTrigger
} from '@/components/ui/tooltip';
import {
    AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
    AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
    AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from 'sonner';

interface JobItemProps {
    job: JobListResponseItem;
    onCancel: (jobId: string) => void;
    onView: (jobId: string) => void;
    onDismiss: (jobId: string) => void;
    onHardDelete: (jobId: string) => Promise<void>; // <-- New prop
}

const taskTypeDisplay: Record<string, { name: string; icon: React.ElementType }> = {
    'deep_research': { name: 'Research', icon: FlaskConical },
    'project_generation': { name: 'Project Gen', icon: Bot },
    'summarize_document_content': { name: 'Summarize', icon: FileTextIcon },
    'unknown': { name: 'Task', icon: FileClock }
};

const JobItem: React.FC<JobItemProps> = ({ job, onCancel, onView, onDismiss, onHardDelete }) => {

    const isPending = job.status === JOB_STATUS_PENDING;
    const isRunning = job.status === JOB_STATUS_RUNNING;
    const isCompleted = job.status === JOB_STATUS_COMPLETED;
    const isFailed = job.status === JOB_STATUS_FAILED;
    const isCanceled = job.status === JOB_STATUS_CANCELED;

    const displayInfo = taskTypeDisplay[job.task_type] || taskTypeDisplay['unknown'];

    const getCleanSummary = (summary: string | null | undefined): string => {
        if (!summary) return `Job ${job.job_id.substring(0, 8)}...`;
        try {
            if (summary.startsWith("{") && summary.includes("'topic':")) {
                const topicMatch = summary.match(/'topic':\s*'([^']*)'/);
                if (topicMatch && topicMatch[1]) return topicMatch[1];
            }
        } catch (e) { /* ignore */ }
        return summary.length > 70 ? summary.substring(0, 67) + "..." : summary;
    };
    const cleanJobSummary = getCleanSummary(job.input_summary);

    const renderStatusIcon = () => { /* ... same as before ... */ 
        if (isPending) return <FileClock className="w-3.5 h-3.5 text-muted-foreground" />;
        if (isRunning) return <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />;
        if (isCompleted) return <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />;
        if (isFailed) return <XCircle className="w-3.5 h-3.5 text-destructive" />;
        if (isCanceled) return <Ban className="w-3.5 h-3.5 text-orange-500" />;
        return <FileClock className="w-3.5 h-3.5 text-muted-foreground" />;
    };
    const getStatusColorClass = () => { /* ... same as before ... */ 
        if (isPending) return "text-muted-foreground";
        if (isRunning) return "text-blue-500";
        if (isCompleted) return "text-green-600";
        if (isFailed) return "text-destructive";
        if (isCanceled) return "text-orange-500 dark:text-orange-400";
        return "text-muted-foreground";
    };
    const formatTimestamp = (ts: number | undefined | null) => { /* ... same as before ... */ 
        if (!ts) return 'N/A';
        try {
            return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (e) { return 'Invalid Date'; }
    };
    
    const handleDismissConfirmed = () => onDismiss(job.job_id);
    const handleCancelClick = (e: React.MouseEvent) => { e.stopPropagation(); onCancel(job.job_id); };
    const handleViewClick = (e: React.MouseEvent) => { e.stopPropagation(); onView(job.job_id); };
    const handleShowErrorDetails = (e: React.MouseEvent) => { 
        e.stopPropagation(); 
        toast.error(job.error_message || "No error details available.", {
            description: `Job ID: ${job.job_id.substring(0,8)}...`,
            duration: 10000,
        });
    };

    // New handler for permanent delete confirmation
    const handleHardDeleteConfirmed = async () => {
        await onHardDelete(job.job_id);
        // The job will be removed from the list by the logic in useJobTracking hook
    };

    return (
        <TooltipProvider>
            <div className={cn(
                "p-2.5 border rounded-lg bg-card text-xs shadow-sm hover:shadow-md transition-all relative group",
                isCompleted && "border-green-500/30 hover:border-green-500/50",
                isFailed && "border-destructive/30 hover:border-destructive/50",
                isCanceled && "border-orange-500/30 hover:border-orange-500/50",
                !isCompleted && !isFailed && !isCanceled && "border-border hover:border-border/70"
            )}>
                {/* Dismiss Button for PENDING or RUNNING jobs */}
                {(isPending || isRunning) && (
                    <AlertDialog>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <AlertDialogTrigger asChild>
                                    <Button
                                        variant="ghost" size="icon" aria-label="Dismiss Task"
                                        className="absolute top-1 right-1 h-6 w-6 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity z-10"
                                    > <XIcon className="w-4 h-4" /> </Button>
                                </AlertDialogTrigger>
                            </TooltipTrigger>
                            <TooltipContent side="top">Dismiss Task</TooltipContent>
                        </Tooltip>
                        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                            <AlertDialogHeader>
                                <AlertDialogTitle>Dismiss Task?</AlertDialogTitle>
                                <AlertDialogDescription>
                                    This removes the task from view but won't cancel it. Are you sure you want to dismiss "{cleanJobSummary}"?
                                </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel>Keep</AlertDialogCancel>
                                <AlertDialogAction onClick={handleDismissConfirmed} className={buttonVariants({ variant: "destructive" })}>
                                    Dismiss
                                </AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>
                )}

                {/* Permanent Delete Button - Appears for terminal states (Completed, Failed, Canceled) on hover */}
                {/* Consider if this should be available for PENDING/RUNNING too, or only terminal states */}
                {(isCompleted || isFailed || isCanceled) && (
                     <AlertDialog>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <AlertDialogTrigger asChild>
                                    <Button
                                        variant="ghost" size="icon" aria-label="Delete Job Permanently"
                                        className="absolute top-1 right-8 h-6 w-6 text-muted-foreground hover:text-red-700 dark:hover:text-red-500 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity z-10"
                                        // Position it next to the dismiss 'X' if both could appear, or adjust as needed
                                    > <Trash2 className="w-4 h-4" /> </Button>
                                </AlertDialogTrigger>
                            </TooltipTrigger>
                            <TooltipContent side="top">Delete Permanently</TooltipContent>
                        </Tooltip>
                        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                            <AlertDialogHeader>
                                <AlertDialogTitle>Delete Job Permanently?</AlertDialogTitle>
                                <AlertDialogDescription>
                                    This action cannot be undone. The job "{cleanJobSummary}" and its results will be permanently removed from the system.
                                </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction onClick={handleHardDeleteConfirmed} className={buttonVariants({ variant: "destructive" })}>
                                    Delete Permanently
                                </AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>
                )}


                <div className="flex items-center justify-between mb-1.5">
                    {/* ... (Badge and Status Icon - same as before) ... */}
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-5 font-normal">
                        <displayInfo.icon className="w-3 h-3 mr-1.5 flex-shrink-0"/>
                        {displayInfo.name}
                    </Badge>
                    <Tooltip>
                        <TooltipTrigger asChild><div className="cursor-default">{renderStatusIcon()}</div></TooltipTrigger>
                        <TooltipContent side="top" align="end"><p>{job.status}</p></TooltipContent>
                    </Tooltip>
                </div>

                <Tooltip>
                    {/* ... (Input Summary - same as before, uses cleanJobSummary) ... */}
                     <TooltipTrigger asChild>
                        <p className="font-medium truncate mb-1 text-foreground/90 text-[13px] cursor-default leading-tight">
                            {cleanJobSummary}
                        </p>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" align="start" className="max-w-[250px]"><p className="text-xs whitespace-pre-wrap break-words">{job.input_summary || job.job_id}</p></TooltipContent>
                </Tooltip>

                <Tooltip>
                    {/* ... (Progress Message - same as before) ... */}
                    <TooltipTrigger asChild>
                        <p className={cn("text-[11px] h-4 truncate cursor-default", getStatusColorClass())}>
                            {job.progress_message || job.status}
                        </p>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" align="start" className="max-w-[250px]">
                        <p className="text-xs whitespace-pre-wrap break-words">{job.progress_message || job.status}</p>
                        <p className="text-[10px] text-muted-foreground mt-1">Created: {formatTimestamp(job.created_at)}</p>
                        <p className="text-[10px] text-muted-foreground">Updated: {formatTimestamp(job.updated_at)}</p>
                    </TooltipContent>
                </Tooltip>

                <div className="flex items-center justify-end gap-1.5 mt-2 -mb-0.5 -mr-0.5">
                    {/* ... (Cancel, View, Details buttons - same as before) ... */}
                    {(isPending || isRunning) && (
                        <Button variant="outline" size="xs" className="text-xs h-7 px-2" onClick={handleCancelClick} title="Cancel Task">
                            Cancel
                        </Button>
                    )}
                    {isCompleted && ( 
                        <Button variant="default" size="xs" className="text-xs h-7 px-2 flex items-center" onClick={handleViewClick} title="View Results">
                            <Eye className="w-3.5 h-3.5 mr-1"/> View
                        </Button>
                    )}
                    {isFailed && (
                        <Button variant="destructive" size="xs" className="text-xs h-7 px-2" onClick={handleShowErrorDetails} title="Show Error Details">
                            Details
                        </Button>
                    )}
                </div>
            </div>
        </TooltipProvider>
    );
}

export default JobItem;