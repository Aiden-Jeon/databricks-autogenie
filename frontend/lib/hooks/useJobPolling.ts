/**
 * Hook for polling job status.
 */

import { useState, useEffect, useCallback } from 'react';
import { sharedApi, Job } from '../api-client';

interface UseJobPollingResult {
  job: Job | null;
  isPolling: boolean;
  error: string | null;
  stopPolling: () => void;
}

export function useJobPolling(
  jobId: string | null,
  pollInterval = 1000
): UseJobPollingResult {
  const [job, setJob] = useState<Job | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shouldStop, setShouldStop] = useState(false);

  const stopPolling = useCallback(() => {
    setShouldStop(true);
  }, []);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setIsPolling(false);
      return;
    }

    setShouldStop(false);
    setError(null);

    const poll = async () => {
      try {
        const jobData = await sharedApi.getJob(jobId);
        setJob(jobData);

        // Stop polling if job is complete
        if (jobData.status === 'completed' || jobData.status === 'failed' || jobData.status === 'cancelled') {
          setIsPolling(false);
          return true; // Stop polling
        }
        return false; // Continue polling
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch job status');
        setIsPolling(false);
        return true; // Stop polling on error
      }
    };

    setIsPolling(true);

    // Initial poll
    poll().then((done) => {
      if (done) return;

      // Set up interval for subsequent polls
      const interval = setInterval(async () => {
        if (shouldStop) {
          clearInterval(interval);
          setIsPolling(false);
          return;
        }

        const done = await poll();
        if (done) {
          clearInterval(interval);
        }
      }, pollInterval);

      return () => {
        clearInterval(interval);
      };
    });
  }, [jobId, pollInterval, shouldStop]);

  return { job, isPolling, error, stopPolling };
}
