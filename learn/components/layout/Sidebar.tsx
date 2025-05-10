// learn/components/layout/Sidebar.tsx
'use client';

import React from 'react';
import { JobListResponseItem } from '@/lib/api';
import JobItem from './JobItem';
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { History, ListTodo, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { HistoryPaginationState } from '@/hooks/useJobTracking';

interface SidebarProps {
    jobsToDisplay: JobListResponseItem[];
    isHistoryView: boolean;
    historyPagination: HistoryPaginationState;
    isLoadingJobs: boolean;
    onCancelJob: (jobId: string) => void;
    onViewResults: (jobId: string) => void;
    onDismissJob: (jobId: string) => void;
    onToggleHistoryView: () => void;
    onLoadMoreHistory: () => void;
    onHardDeleteJob: (jobId: string) => Promise<void>; // <-- New prop for hard delete
}

export default function Sidebar({
    jobsToDisplay,
    isHistoryView,
    historyPagination,
    isLoadingJobs,
    onCancelJob,
    onViewResults,
    onDismissJob,
    onToggleHistoryView,
    onLoadMoreHistory,
    onHardDeleteJob, // <-- Destructure the new prop
}: SidebarProps) {

    const currentViewTitle = isHistoryView ? "Job History" : "Active Tasks";
    const IconComponent = isHistoryView ? History : ListTodo;

    return (
         <div className="flex flex-col h-full">
            <div className="p-3 flex-shrink-0">
                <div className="flex items-center justify-between mb-2">
                    <h2 className="text-sm font-semibold text-muted-foreground flex items-center">
                        <IconComponent className="w-4 h-4 mr-2"/> {currentViewTitle}
                    </h2>
                </div>
                <Separator className="mb-3"/>
            </div>

            {isLoadingJobs && jobsToDisplay.length === 0 && (
                <div className="flex-grow flex items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
            )}

            {!isLoadingJobs && jobsToDisplay.length === 0 && (
                 <div className="flex-grow flex items-center justify-center px-4 text-center">
                    <p className="text-xs text-muted-foreground">
                        {isHistoryView ? "No job history found." : "No active tasks."}
                    </p>
                </div>
            )}

            {jobsToDisplay.length > 0 && (
                <ScrollArea className="flex-grow px-3 pb-1">
                    <div className="space-y-2">
                        {jobsToDisplay.map((job) => (
                            <JobItem
                                key={`${job.job_id}-${job.status}-${job.updated_at}`}
                                job={job}
                                onCancel={onCancelJob}
                                onView={onViewResults}
                                onDismiss={onDismissJob}
                                onHardDelete={onHardDeleteJob} // <-- Pass it down to JobItem
                            />
                        ))}
                    </div>
                    {isHistoryView && historyPagination.hasMore && !historyPagination.isLoading && (
                        <div className="mt-4 flex justify-center">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={onLoadMoreHistory}
                                disabled={historyPagination.isLoading}
                            >
                                {historyPagination.isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                Load More History
                            </Button>
                        </div>
                    )}
                    {isHistoryView && historyPagination.isLoading && jobsToDisplay.length > 0 && (
                         <div className="py-4 flex justify-center">
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        </div>
                    )}
                     <ScrollBar orientation="vertical" />
                </ScrollArea>
            )}
            
            <div className="p-3 border-t dark:border-gray-700 flex-shrink-0 mt-auto">
                <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start text-muted-foreground hover:text-foreground"
                    onClick={onToggleHistoryView}
                >
                    {isHistoryView ? (
                        <><ListTodo className="w-4 h-4 mr-2"/> View Active Tasks</>
                    ) : (
                        <><History className="w-4 h-4 mr-2"/> View Job History</>
                    )}
                </Button>
            </div>
        </div>
    );
}