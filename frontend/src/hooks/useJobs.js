import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSources, startIngestionJob, startProcessingJob, getJob, getJobs } from '../api/jobs';

export const useSources = () => {
  return useQuery({
    queryKey: ['sources'],
    queryFn: getSources,
  });
};

export const useStartIngestion = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: startIngestionJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
};

export const useStartProcessing = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: startProcessingJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
};

export const useJob = (jobId, enabled = false) => {
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
    enabled: !!jobId && enabled,
    // FIX: Updated for React Query v5 so it keeps polling every 2 seconds
    refetchInterval: (query) => {
      const jobData = query?.state?.data;
      if (!jobData || jobData.status === 'running') return 2000;
      return false;
    },
  });
};

export const useRecentJobs = () => {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: () => getJobs(10),
  });
};