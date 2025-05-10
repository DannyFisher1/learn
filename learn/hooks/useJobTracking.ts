// learn/hooks/useJobTracking.ts
import { useState, useCallback, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import {
    JobListResponseItem, JobStatus,
    getActiveJobs, getJobStatus, cancelJob, startJob, getJobHistory,
    hardDeleteJobAPI, // Assuming this will be added to lib/api.ts
    JOB_STATUS_PENDING, JOB_STATUS_RUNNING, JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED, JOB_STATUS_CANCELED
} from '@/lib/api';

const JOB_POLLING_INTERVAL = 5000;
const INITIAL_ACTIVE_HISTORY_LOAD_COUNT = 5;
const HISTORY_PAGE_LIMIT = 10;

interface UseJobTrackingProps {
    onJobRequiresView: (jobId: string) => void;
}

export interface HistoryPaginationState {
    offset: number;
    limit: number;
    total: number;
    isLoading: boolean;
    hasMore: boolean;
}

export function useJobTracking({ onJobRequiresView }: UseJobTrackingProps) {
    const [trackedJobs, setTrackedJobs] = useState<JobListResponseItem[]>([]);
    const [jobHistory, setJobHistory] = useState<JobListResponseItem[]>([]);
    const [isHistoryViewActive, setIsHistoryViewActive] = useState(false);
    const [historyPagination, setHistoryPagination] = useState<HistoryPaginationState>({
        offset: 0,
        limit: HISTORY_PAGE_LIMIT,
        total: 0,
        isLoading: false,
        hasMore: false,
    });
    const [isInitialLoadComplete, setIsInitialLoadComplete] = useState(false);
    const [isLoadingJobsList, setIsLoadingJobsList] = useState(true);

    const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

    const internalFetchTrackedJobs = useCallback(async (isManualRefresh = false) => {
        if (isManualRefresh) {
            toast.info("Refreshing active tasks...");
            setIsLoadingJobsList(true);
        } else if (!isInitialLoadComplete) {
            setIsLoadingJobsList(true);
        }
        try {
            const activeJobsResponse = await getActiveJobs();
            const backendActiveJobs = activeJobsResponse.jobs || [];
            let initialHistoricalJobsForActiveView: JobListResponseItem[] = [];
            if (!isInitialLoadComplete || isManualRefresh) {
                const historyResponse = await getJobHistory(INITIAL_ACTIVE_HISTORY_LOAD_COUNT, 0);
                initialHistoricalJobsForActiveView = historyResponse.jobs || [];
            }
            setTrackedJobs(prevTracked => {
                const newJobsMap = new Map<string, JobListResponseItem>();
                backendActiveJobs.forEach(job => newJobsMap.set(job.job_id, job));
                initialHistoricalJobsForActiveView.forEach(job => {
                    if (!newJobsMap.has(job.job_id)) newJobsMap.set(job.job_id, job);
                });
                if(isInitialLoadComplete || isManualRefresh){
                    prevTracked.forEach(prevJob => {
                        if (!newJobsMap.has(prevJob.job_id) &&
                            [JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELED].includes(prevJob.status)) {
                            newJobsMap.set(prevJob.job_id, prevJob);
                        }
                    });
                }
                const finalTrackedJobsList = Array.from(newJobsMap.values())
                    .sort((a, b) => b.created_at - a.created_at);
                const prevSorted = [...prevTracked].sort((a,b) => b.created_at - a.created_at);
                if (JSON.stringify(finalTrackedJobsList) === JSON.stringify(prevSorted) && prevTracked.length === finalTrackedJobsList.length && isInitialLoadComplete) {
                    return prevTracked;
                }
                return finalTrackedJobsList;
            });
        } catch (error: any) {
            console.error("Failed to fetch tracked jobs:", error);
            toast.error(`Failed to fetch active tasks: ${error.message || 'Unknown error'}`);
        } finally {
            if (!isInitialLoadComplete) setIsInitialLoadComplete(true);
            setIsLoadingJobsList(false);
        }
    }, [isInitialLoadComplete]);

    const internalPollJobStatuses = useCallback(async () => {
        setTrackedJobs(prevJobs => {
            const jobsToPoll = prevJobs.filter(j => [JOB_STATUS_PENDING, JOB_STATUS_RUNNING].includes(j.status));
            if (jobsToPoll.length === 0) return prevJobs;
            Promise.all(jobsToPoll.map(job => getJobStatus(job.job_id).catch(err => {
                console.error(`Polling failed for job ${job.job_id}:`, err);
                return { ...job, status: JOB_STATUS_FAILED as JobStatus, error_message: "Status polling failed", progress_message: "Polling Failed" };
            }))).then(updatedJobStatuses => {
                setTrackedJobs(currentTrackedJobs => {
                    let anyChange = false;
                    const newTrackedJobsArray = currentTrackedJobs.map(trackedJob => {
                        const updatedData = updatedJobStatuses.find(ujd => ujd?.job_id === trackedJob.job_id);
                        if (updatedData && (
                            trackedJob.status !== updatedData.status || 
                            trackedJob.progress_message !== updatedData.progress_message || 
                            trackedJob.error_message !== updatedData.error_message ||
                            trackedJob.updated_at !== updatedData.updated_at
                        )) {
                            anyChange = true;
                            const updatedItem: JobListResponseItem = { ...trackedJob, ...updatedData, status: updatedData.status as JobStatus };
                            if ([JOB_STATUS_RUNNING, JOB_STATUS_PENDING].includes(trackedJob.status) &&
                                [JOB_STATUS_COMPLETED, JOB_STATUS_FAILED].includes(updatedItem.status)) {
                                const summaryForToast = updatedItem.input_summary || updatedItem.job_id.substring(0,8)+"...";
                                const toastMethod = updatedItem.status === JOB_STATUS_COMPLETED ? toast.success : toast.error;
                                toastMethod(updatedItem.status === JOB_STATUS_COMPLETED ? "Job Completed" : "Job Failed", {
                                    description: `Task '${summaryForToast}' finished.`,
                                    action: { label: "View", onClick: () => onJobRequiresView(updatedItem.job_id) },
                                });
                            }
                            return updatedItem;
                        }
                        return trackedJob;
                    });
                    return anyChange ? newTrackedJobsArray.sort((a, b) => b.created_at - a.created_at) : currentTrackedJobs;
                });
            });
            return prevJobs;
        });
    }, [onJobRequiresView]);

    const cancelJobHandler = useCallback(async (jobId: string) => {
        toast.info(`Requesting cancellation for job ${jobId.substring(0,8)}...`);
        try {
            const cancelResponse = await cancelJob(jobId);
            if (["CANCEL_REQUESTED", "CANCELED"].includes(cancelResponse.status.toUpperCase())) {
                toast.success(`Cancellation requested for job ${jobId.substring(0,8)}.`);
                const newStatus = JOB_STATUS_CANCELED as JobStatus;
                const updateFn = (j: JobListResponseItem) => j.job_id === jobId ? { ...j, status: newStatus, progress_message: "Cancellation requested..." } : j;
                setTrackedJobs(prev => prev.map(updateFn).sort((a, b) => b.created_at - a.created_at));
                setJobHistory(prev => prev.map(updateFn).sort((a, b) => b.created_at - a.created_at));
            } else {
                toast.error(`Failed to cancel job ${jobId.substring(0,8)}: ${cancelResponse.message || 'Unknown reason'}`);
            }
        } catch (error: any) {
            console.error(`Failed to cancel job ${jobId}:`, error);
            toast.error(`Failed to cancel job ${jobId.substring(0,8)}: ${error.message || 'Unknown error'}`);
        }
    }, []); // setTrackedJobs and setJobHistory are stable

    const dismissJobHandler = useCallback((jobId: string) => {
        if (isHistoryViewActive) {
            setJobHistory(prev => prev.filter(j => j.job_id !== jobId));
        } else {
            setTrackedJobs(prev => prev.filter(j => j.job_id !== jobId));
        }
        toast.info(`Job ${jobId.substring(0,8)}... dismissed from view.`);
    }, [isHistoryViewActive]); // setTrackedJobs and setJobHistory are stable

    const startJobHandler = useCallback(async (taskType: string, params: any) => {
        const taskName = taskType.replace(/_/g, ' ');
        toast.info(`Starting ${taskName}...`);
        try {
            const startedJobData = await startJob(taskType, params);
            let summary = `Parameters: ${JSON.stringify(params).substring(0, 50)}...`;
            if (taskType === 'deep_research' && params.topic) {
                summary = params.topic;
            }
            const newJobItem: JobListResponseItem = {
                job_id: startedJobData.job_id, task_type: taskType, status: JOB_STATUS_PENDING as JobStatus,
                created_at: Date.now() / 1000, updated_at: Date.now() / 1000,
                input_summary: summary, progress_message: "Job queued..."
            };
            setTrackedJobs(prev => [newJobItem, ...prev].sort((a,b) => b.created_at - a.created_at));
            if (isHistoryViewActive) setIsHistoryViewActive(false); // Switch to active view when a new job starts
            toast.success(`${taskName} job started (ID: ${startedJobData.job_id.substring(0, 8)}...)`);
        } catch (error: any) {
            console.error(`Failed to start job ${taskType}:`, error);
            toast.error(`Failed to start ${taskName} job: ${error.message || 'Unknown error'}`);
        }
    }, [isHistoryViewActive]); // setIsHistoryViewActive is stable

    const fetchJobHistoryPage = useCallback(async (offset: number, limit: number) => {
        setHistoryPagination(prev => ({ ...prev, isLoading: true }));
        try {
            const response = await getJobHistory(limit, offset);
            const newJobs: JobListResponseItem[] = response.jobs.map(job => ({...job, status: job.status as JobStatus}));
            setJobHistory(prev => 
                (offset === 0 ? newJobs : [...prev, ...newJobs])
                .sort((a,b) => b.created_at - a.created_at) // Ensure history is always sorted
            );
            setHistoryPagination(prev => ({
                ...prev,
                offset: offset,
                limit: limit,
                total: response.total,
                isLoading: false,
                hasMore: (offset + newJobs.length) < response.total,
            }));
        } catch (error: any) {
            console.error("Failed to fetch job history page:", error);
            toast.error(`Failed to load job history: ${error.message || 'Unknown error'}`);
            setHistoryPagination(prev => ({ ...prev, isLoading: false }));
        }
    }, []); // setJobHistory, setHistoryPagination are stable

    const toggleHistoryViewHandler = useCallback(() => {
        const newHistoryState = !isHistoryViewActive;
        setIsHistoryViewActive(newHistoryState);
        if (newHistoryState) {
            setJobHistory([]); 
            setHistoryPagination(prev => ({...prev, offset: 0, total:0, hasMore: false, isLoading: true}));
            fetchJobHistoryPage(0, HISTORY_PAGE_LIMIT);
        } else {
            internalFetchTrackedJobs(false); 
        }
    }, [isHistoryViewActive, fetchJobHistoryPage, internalFetchTrackedJobs]); // Stable dependencies

    const loadMoreHistoryHandler = useCallback(() => {
        if (historyPagination.hasMore && !historyPagination.isLoading) {
            const newOffset = historyPagination.offset + historyPagination.limit;
            fetchJobHistoryPage(newOffset, historyPagination.limit);
        }
    }, [historyPagination, fetchJobHistoryPage]);
    
    const refreshListHandler = useCallback(() => {
        if (isHistoryViewActive) {
            setJobHistory([]); 
            setHistoryPagination(prev => ({...prev, offset: 0, total:0, hasMore: false, isLoading: true}));
            fetchJobHistoryPage(0, HISTORY_PAGE_LIMIT);
            toast.info("Refreshing job history...");
        } else {
            internalFetchTrackedJobs(true);
        }
    }, [isHistoryViewActive, fetchJobHistoryPage, internalFetchTrackedJobs]);

    const hardDeleteJobHandler = useCallback(async (jobId: string) => {
        try {
            await hardDeleteJobAPI(jobId); // This now refers to the one imported from lib/api.ts
            toast.success(`Job ${jobId.substring(0,8)}... permanently deleted.`);
            
            // Correctly use the state setters defined within this hook
            setTrackedJobs((prev: JobListResponseItem[]) => prev.filter((j: JobListResponseItem) => j.job_id !== jobId));
            setJobHistory((prev: JobListResponseItem[]) => prev.filter((j: JobListResponseItem) => j.job_id !== jobId));

        } catch (error: any) {
            console.error(`Failed to permanently delete job ${jobId}:`, error);
            toast.error(`Failed to delete job: ${error.message || 'Unknown error'}`);
        }
    }, []); // setTrackedJobs, setJobHistory are stable setters


    useEffect(() => {
        internalFetchTrackedJobs(false); 
        pollingIntervalRef.current = setInterval(internalPollJobStatuses, JOB_POLLING_INTERVAL);
        return () => {
            if (pollingIntervalRef.current) {
                clearInterval(pollingIntervalRef.current);
            }
        };
    }, [internalFetchTrackedJobs, internalPollJobStatuses]); 

    return {
        trackedJobs,
        jobHistory,
        isHistoryViewActive,
        historyPagination,
        isLoadingJobsList,
        
        cancelJobHandler,
        dismissJobHandler,
        startJobHandler,
        toggleHistoryViewHandler,
        loadMoreHistoryHandler,
        refreshListHandler,
        hardDeleteJobHandler,
    };
}