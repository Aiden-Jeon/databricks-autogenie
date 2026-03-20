/**
 * Step 2: Upload benchmarks and start scoring iteration
 */

'use client';

import { useState, useEffect } from 'react';

interface ScoreStepProps {
  state: any;
  onUpdate: (updates: any) => void;
  onNext: () => void;
  onBack: () => void;
  sessionId: string | null;
}

interface ProgressEvent {
  event_type: string;
  timestamp: string;
  [key: string]: any;
}

export function ScoreStep({ state, onUpdate, onNext, onBack, sessionId }: ScoreStepProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [iterationId, setIterationId] = useState<string | null>(state.iterationId || null);
  const [scoreJobId, setScoreJobId] = useState<string | null>(null);
  const [planJobId, setPlanJobId] = useState<string | null>(null);
  const [scoring, setScoring] = useState(false);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  // Check for active jobs when component mounts or session changes
  useEffect(() => {
    const checkActiveJobs = async () => {
      if (!sessionId) return;

      // Check if we're coming from a loop continuation (has new iteration info)
      if (state.autoStartScoring && state.nextIterationId && state.nextScoreJobId) {
        console.log('[ScoreStep] Auto-starting from loop continuation:', {
          iterationId: state.nextIterationId,
          scoreJobId: state.nextScoreJobId
        });

        setIterationId(state.nextIterationId);
        setScoreJobId(state.nextScoreJobId);
        setScoring(true);
        setError('');

        // Clear the auto-start flags
        onUpdate({
          nextIterationId: null,
          nextScoreJobId: null,
          autoStartScoring: false
        });

        // Start polling
        pollScoreJob(state.nextScoreJobId, state.nextIterationId);
        return;
      }

      try {
        // Check for active iterations
        const response = await fetch(`/api/enhancer/sessions/${sessionId}/iterations`);
        const data = await response.json();

        if (data.iterations && data.iterations.length > 0) {
          // Find the most recent iteration
          const latestIteration = data.iterations[0];

          // If there's an in-progress iteration, resume tracking it
          if (latestIteration.status !== 'completed' && latestIteration.status !== 'failed') {
            setIterationId(latestIteration.iteration_id);
            setScoreJobId(latestIteration.score_job_id);
            setScoring(true);
            setError('Resuming active iteration...');

            // Start polling the active job
            if (latestIteration.score_job_id) {
              pollScoreJob(latestIteration.score_job_id, latestIteration.iteration_id);
            }
          }
        }
      } catch (err) {
        console.error('Failed to check active jobs:', err);
      }
    };

    checkActiveJobs();
  }, [sessionId, state.autoStartScoring]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError('');
    }
  };

  const uploadAndScore = async () => {
    if (!file) {
      setError('Please select a benchmark file');
      return;
    }

    if (!sessionId) {
      setError('No session selected. Please create a new session from the sidebar (+ New Session button)');
      return;
    }

    setUploading(true);
    setError('');

    try {
      // Upload benchmarks
      const formData = new FormData();
      formData.append('file', file);

      const uploadResponse = await fetch(`/api/enhancer/sessions/${sessionId}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!uploadResponse.ok) {
        let errorMessage = `Upload failed (${uploadResponse.status} ${uploadResponse.statusText})`;
        try {
          // Try to read as text first (works for both JSON and HTML)
          const responseText = await uploadResponse.text();

          // Try to parse as JSON
          try {
            const errorData = JSON.parse(responseText);
            errorMessage = errorData.detail || errorData.error || errorMessage;
          } catch (e) {
            // Not JSON, show raw text
            if (responseText) {
              errorMessage = `${errorMessage}\n\nServer response:\n${responseText.substring(0, 500)}`;
            }
          }
        } catch (e) {
          // Couldn't read response at all
          errorMessage = `${errorMessage}\n\nCouldn't read server response: ${e}`;
        }
        throw new Error(errorMessage);
      }

      const uploadData = await uploadResponse.json();
      const benchmarks = uploadData.benchmarks;

      onUpdate({ benchmarks });

      // Clone space if enabled (for safety)
      let finalSpaceId = state.space_id;
      if (state.use_clone !== false) {  // Default to true
        try {
          setError('Cloning production space for safe testing...');

          const cloneResponse = await fetch(`/api/enhancer/sessions/${sessionId}/clone-space`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ space_id: state.space_id })
          });

          if (cloneResponse.ok) {
            const cloneData = await cloneResponse.json();
            finalSpaceId = cloneData.dev_working_id;
            setError(`✓ Using dev-working space: ${cloneData.production_name}_dev_working`);

            // Update state with cloned space IDs
            onUpdate({
              production_space_id: cloneData.production_id,
              dev_working_id: cloneData.dev_working_id,
              dev_best_id: cloneData.dev_best_id,
              space_id: finalSpaceId  // Use dev-working for testing
            });
          } else {
            setError('Failed to clone space, using production directly (not recommended)');
          }
        } catch (err) {
          console.error('Clone error:', err);
          setError('Clone failed, using production space');
        }
      }

      // Start iteration (score + plan)
      const iterationResponse = await fetch(`/api/enhancer/sessions/${sessionId}/iterations/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_config: {
            warehouse_id: state.warehouse_id,
            space_id: finalSpaceId,
            llm_endpoint: state.llm_endpoint || 'databricks-gpt-5-2',
          },
          benchmarks,
        }),
      });

      if (!iterationResponse.ok) {
        let errorMessage = `Failed to start iteration (${iterationResponse.status})`;
        try {
          const responseText = await iterationResponse.text();
          try {
            const errorData = JSON.parse(responseText);
            errorMessage = errorData.detail || errorData.error || errorMessage;
          } catch (e) {
            if (responseText) {
              errorMessage = `${errorMessage}\n\n${responseText.substring(0, 500)}`;
            }
          }
        } catch (e) {
          errorMessage = `${errorMessage}\n\nCouldn't read response: ${e}`;
        }
        throw new Error(errorMessage);
      }

      const iterationData = await iterationResponse.json();
      setIterationId(iterationData.iteration_id);
      setScoreJobId(iterationData.score_job_id);
      onUpdate({ iterationId: iterationData.iteration_id });

      setUploading(false);
      setScoring(true);

      // Poll score job for progress
      pollScoreJob(iterationData.score_job_id, iterationData.iteration_id);
    } catch (err: any) {
      setError(err.message || 'Failed to upload or start scoring');
      setUploading(false);
    }
  };

  const pollScoreJob = async (jobId: string, iterId: string) => {
    const interval = setInterval(async () => {
      try {
        // Get job status for progress
        const jobResponse = await fetch(`/api/jobs/${jobId}`);
        const job = await jobResponse.json();

        // DEBUG: Log poll results
        console.log('[ScoreStep] Poll result:', {
          jobId,
          status: job.status,
          hasProgress: !!job.progress,
          hasCurrent: !!job.progress?.current,
          eventCount: job.progress?.events?.length || 0,
          currentEvent: job.progress?.current
        });

        // Update progress
        if (job.progress) {
          const currentEvent = job.progress.current;
          if (currentEvent) {
            console.log('[ScoreStep] Setting progress:', currentEvent);
            setProgress(currentEvent);
          }
          if (job.progress.events) {
            setEvents(job.progress.events);
          }
        }

        if (job.status === 'completed') {
          clearInterval(interval);

          // Get iteration status
          const iterResponse = await fetch(`/api/enhancer/iterations/${iterId}`);
          const iteration = await iterResponse.json();

          setResult({
            score: iteration.score_before,
            iteration,
          });

          onUpdate({
            scoreResult: { score: iteration.score_before },
            iteration,
          });

          // Start planning automatically
          startPlanning(iterId);
        } else if (job.status === 'failed') {
          clearInterval(interval);
          setError('Scoring failed: ' + (job.error || 'Unknown error'));
          setScoring(false);
        }
      } catch (err) {
        console.error('Error polling job:', err);
      }
    }, 1000); // Poll every second for real-time feel
  };

  const startPlanning = async (iterId: string) => {
    try {
      // Get iteration to check score
      const iterResponse = await fetch(`/api/enhancer/iterations/${iterId}`);
      const iteration = await iterResponse.json();

      if (!iteration.score_job_id) return;

      // Get score job to extract failed benchmarks
      const jobResponse = await fetch(`/api/jobs/${iteration.score_job_id}`);
      const job = await jobResponse.json();

      if (!job.result) return;

      const failedBenchmarks = (job.result.results || []).filter((r: any) => !r.passed);

      if (failedBenchmarks.length === 0) {
        // All passed! No planning needed
        setScoring(false);
        alert('All benchmarks passed! No fixes needed.');
        return;
      }

      // Start planning
      const planResponse = await fetch('/api/enhancer/jobs/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          workspace_config: {
            warehouse_id: state.warehouse_id,
            space_id: state.space_id,
            llm_endpoint: state.llm_endpoint || 'databricks-gpt-5-2',
          },
          failed_benchmarks: failedBenchmarks,
          iteration_id: iterId,  // Pass iteration_id for status update
        }),
      });

      const planData = await planResponse.json();
      setPlanJobId(planData.job_id);

      // Poll plan job
      pollPlanJob(planData.job_id, iterId);
    } catch (err) {
      console.error('Failed to start planning:', err);
      setScoring(false);
    }
  };

  const pollPlanJob = async (jobId: string, iterId: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/jobs/${jobId}`);
        const job = await response.json();

        if (job.status === 'completed') {
          clearInterval(interval);

          // Get updated iteration
          const iterResponse = await fetch(`/api/enhancer/iterations/${iterId}`);
          const iteration = await iterResponse.json();

          onUpdate({
            iteration,
            plan: job.result,
          });

          setScoring(false);
        } else if (job.status === 'failed') {
          clearInterval(interval);
          setError('Planning failed: ' + (job.error || 'Unknown error'));
          setScoring(false);
        }
      } catch (err) {
        console.error('Error polling plan job:', err);
      }
    }, 2000);
  };

  const getCurrentPhase = () => {
    if (!progress) return 'Initializing...';

    // Simple progress display - just show the message
    if (progress.message) {
      const icon = progress.phase === 'genie' ? '🤖' :
                   progress.phase === 'sql' ? '🔄' :
                   progress.phase === 'eval' ? '🧠' :
                   progress.phase === 'complete' ? '✅' : '⏳';
      return `${icon} ${progress.message}`;
    }

    return 'Processing...';
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">📊 Score Benchmarks</h2>

      {!scoring && !result && (
        <div>
          <p className="mb-4 text-gray-700">Upload benchmarks to start the enhancement iteration.</p>

          {!sessionId && (
            <div className="p-4 bg-yellow-50 border border-yellow-200 rounded mb-4">
              <p className="text-sm text-yellow-700">
                ⚠️ <strong>No session selected.</strong> Please create a new session using the "+ New Session" button in the sidebar.
              </p>
            </div>
          )}

          {sessionId && (
            <div className="p-3 bg-green-50 border border-green-200 rounded mb-4">
              <p className="text-sm text-green-700">
                ✓ Session active: <code className="text-xs bg-green-100 px-2 py-1 rounded">{sessionId}</code>
              </p>
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm font-medium mb-2 text-gray-700">
              Benchmark File (JSON)
            </label>
            <input
              type="file"
              accept=".json"
              onChange={handleFileChange}
              className="w-full text-gray-900"
            />
            {file && (
              <p className="text-sm text-gray-600 mt-1">Selected: {file.name}</p>
            )}
          </div>

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded mb-4">
              <p className="text-sm text-red-600 whitespace-pre-wrap">{error}</p>
            </div>
          )}

          <div className="flex gap-4">
            <button
              onClick={onBack}
              className="px-6 py-2 border rounded hover:bg-gray-50"
            >
              ← Back
            </button>
            <button
              onClick={uploadAndScore}
              disabled={!file || !sessionId || uploading}
              className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {uploading ? 'Uploading...' : 'Upload & Start Iteration'}
            </button>
          </div>
        </div>
      )}

      {scoring && (
        <div>
          <div className="border rounded-lg p-6 bg-white shadow-sm mb-4">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold">{getCurrentPhase()}</h3>
              {progress && progress.total > 0 && (
                <span className="text-sm text-gray-500">
                  {progress.completed || 0}/{progress.total}
                </span>
              )}
            </div>

            {/* Progress stats for Genie phase */}
            {progress && progress.phase === 'genie' && progress.successful !== undefined && (
              <div className="mb-4 flex gap-4 text-sm">
                <span className="text-green-600">✅ {progress.successful} successful</span>
                <span className="text-red-600">❌ {progress.failed || 0} failed</span>
              </div>
            )}

            {/* Progress bar */}
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div
                className="bg-blue-600 h-3 rounded-full transition-all duration-300"
                style={{
                  width: progress && progress.total ? `${(progress.completed / progress.total) * 100}%` : '0%'
                }}
              ></div>
            </div>

            {/* Final score if complete */}
            {progress && progress.phase === 'complete' && progress.score !== undefined && (
              <div className="mt-4 p-3 bg-blue-50 rounded">
                <span className="font-semibold text-blue-700">
                  Score: {(progress.score * 100).toFixed(0)}% ({progress.passed}/{progress.total} passed)
                </span>
              </div>
            )}

          </div>

          <p className="text-sm text-gray-500">
            {scoreJobId && !planJobId && 'Scoring benchmarks...'}
            {planJobId && 'Generating enhancement plan...'}
          </p>
        </div>
      )}

      {result && !scoring && (
        <div>
          <div className="bg-blue-100 p-6 rounded mb-4">
            <h3 className="text-xl font-bold mb-2">Score: {(result.score * 100).toFixed(1)}%</h3>
            <p>Iteration {result.iteration?.iteration_number || 1} complete</p>
          </div>

          <button
            onClick={onNext}
            className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
          >
            Continue to Plan & Apply →
          </button>
        </div>
      )}
    </div>
  );
}
