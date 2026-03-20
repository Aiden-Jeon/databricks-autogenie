/**
 * Step 4: Validate results and control iteration loop
 */

'use client';

import { useState } from 'react';

interface ApplyStepProps {
  state: any;
  onUpdate: (updates: any) => void;
  onBack: () => void;
  onNextIteration: () => void;  // Go back to Score step for next iteration
  sessionId: string | null;
}

export function ApplyStep({ state, onUpdate, onBack, onNextIteration, sessionId }: ApplyStepProps) {
  const [validating, setValidating] = useState(false);
  const [validated, setValidated] = useState(false);
  const [validationResult, setValidationResult] = useState<any>(null);
  const [continuing, setContinuing] = useState(false);
  const [loopComplete, setLoopComplete] = useState(false);
  const [loopReason, setLoopReason] = useState('');
  const [savingToBest, setSavingToBest] = useState(false);
  const [savedToBest, setSavedToBest] = useState(false);
  const [promotingToProd, setPromotingToProd] = useState(false);
  const [promotedToProd, setPromotedToProd] = useState(false);

  const startValidation = async () => {
    if (!state.iteration) return;

    setValidating(true);

    try {
      // Start validation job
      const response = await fetch('/api/enhancer/jobs/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          workspace_config: {
            warehouse_id: state.warehouse_id,
            space_id: state.space_id,
            llm_endpoint: state.llm_endpoint || 'databricks-gpt-5-2',
          },
          benchmarks: state.benchmarks || [],
          initial_score: state.iteration.score_before || 0,
          target_score: state.target_score || 0.90,
        }),
      });

      const data = await response.json();

      // Poll validation job
      pollValidationJob(data.job_id, state.iteration.iteration_id);
    } catch (error) {
      console.error('Failed to start validation:', error);
      setValidating(false);
      alert('Failed to start validation: ' + error);
    }
  };

  const pollValidationJob = async (jobId: string, iterationId: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/jobs/${jobId}`);
        const job = await response.json();

        if (job.status === 'completed') {
          clearInterval(interval);

          // Get updated iteration
          const iterResponse = await fetch(`/api/enhancer/iterations/${iterationId}`);
          const iteration = await iterResponse.json();

          setValidationResult({
            ...job.result,
            iteration,
          });
          setValidated(true);
          setValidating(false);
        } else if (job.status === 'failed') {
          clearInterval(interval);
          setValidating(false);
          alert('Validation failed: ' + (job.error || 'Unknown error'));
        }
      } catch (err) {
        console.error('Error polling validation job:', err);
      }
    }, 2000);
  };

  const continueLoop = async () => {
    if (!state.iteration) return;

    setContinuing(true);

    try {
      const response = await fetch(`/api/enhancer/iterations/${state.iteration.iteration_id}/continue`, {
        method: 'POST',
      });

      const data = await response.json();

      if (!data.continue) {
        // Loop complete
        setLoopComplete(true);
        setLoopReason(data.reason);
        setContinuing(false);
      } else {
        // Starting next iteration - go back to Score step
        // Pass the new iteration and job IDs so ScoreStep can track them
        onUpdate({
          iteration: null,
          score_results: null,
          plan_results: null,
          apply_results: null,
          // Pass new iteration info for ScoreStep to pick up
          nextIterationId: data.next_iteration_id,
          nextScoreJobId: data.score_job_id,
          autoStartScoring: true  // Flag to auto-start tracking
        });
        setContinuing(false);
        onNextIteration();
      }
    } catch (error) {
      console.error('Failed to continue loop:', error);
      setContinuing(false);
      alert('Failed to continue loop: ' + error);
    }
  };

  const saveToBest = async () => {
    if (!sessionId || !state.dev_working_id || !state.dev_best_id) {
      alert('Dev spaces not configured. Cannot save to best.');
      return;
    }

    setSavingToBest(true);
    try {
      const response = await fetch(`/api/enhancer/sessions/${sessionId}/copy-to-best`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          source_space_id: state.dev_working_id,
          target_space_id: state.dev_best_id
        })
      });

      if (response.ok) {
        setSavedToBest(true);
      } else {
        const data = await response.json();
        alert('Failed to save to best: ' + (data.detail || data.error));
      }
    } catch (error) {
      console.error('Failed to save to best:', error);
      alert('Failed to save to best: ' + error);
    } finally {
      setSavingToBest(false);
    }
  };

  const promoteToProduction = async () => {
    if (!sessionId || !state.dev_working_id || !state.production_space_id) {
      alert('Space IDs not configured. Cannot promote to production.');
      return;
    }

    if (!confirm('Are you sure you want to apply these changes to the production Genie Space?')) {
      return;
    }

    setPromotingToProd(true);
    try {
      const response = await fetch(`/api/enhancer/sessions/${sessionId}/promote-to-production`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          source_space_id: state.dev_working_id,
          target_space_id: state.production_space_id
        })
      });

      if (response.ok) {
        setPromotedToProd(true);
      } else {
        const data = await response.json();
        alert('Failed to promote to production: ' + (data.detail || data.error));
      }
    } catch (error) {
      console.error('Failed to promote to production:', error);
      alert('Failed to promote to production: ' + error);
    } finally {
      setPromotingToProd(false);
    }
  };

  const targetReached = validationResult && validationResult.target_reached;
  const currentScore = validationResult?.new_score || state.iteration?.score_before || 0;
  const initialScore = state.iteration?.score_before || 0;
  const targetScore = state.target_score || 0.90;
  const currentIteration = state.iteration?.iteration_number || 1;
  const maxIterations = state.max_iterations || 3;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">✅ Validate & Loop Control</h2>

      {/* Iteration Status */}
      <div className="bg-blue-50 border border-blue-200 rounded p-4">
        <h3 className="font-semibold mb-2">Iteration Progress</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-600">Current Iteration</p>
            <p className="font-bold text-lg">{currentIteration} of {maxIterations}</p>
          </div>
          <div>
            <p className="text-gray-600">Target Score</p>
            <p className="font-bold text-lg">{(targetScore * 100).toFixed(0)}%</p>
          </div>
        </div>
      </div>

      {!validated && !validating && (
        <div>
          <p className="mb-4 text-gray-700">
            Re-score benchmarks to validate the improvements from applied fixes.
          </p>
          <div className="flex gap-4">
            <button
              onClick={onBack}
              className="px-6 py-2 border rounded hover:bg-gray-50"
            >
              ← Back
            </button>
            <button
              onClick={startValidation}
              className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
            >
              Start Validation
            </button>
          </div>
        </div>
      )}

      {validating && (
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p>Validating improvements...</p>
          <p className="text-sm text-gray-600 mt-2">Re-scoring all benchmarks</p>
        </div>
      )}

      {validated && validationResult && (
        <div>
          <div className={`p-6 rounded mb-4 ${targetReached ? 'bg-green-100' : 'bg-yellow-100'}`}>
            <h3 className="text-2xl font-bold mb-4">
              {targetReached ? '🎉 Target Score Reached!' : '📊 Validation Results'}
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-600">Before (Iteration {currentIteration})</p>
                <p className="text-2xl font-bold">{(initialScore * 100).toFixed(1)}%</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">After Fixes</p>
                <p className="text-2xl font-bold text-green-600">
                  {(currentScore * 100).toFixed(1)}%
                </p>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-gray-300">
              <p className="text-sm">
                <strong>Improvement:</strong> {((currentScore - initialScore) * 100).toFixed(1)}%
              </p>
              <p className="text-sm">
                <strong>Target:</strong> {(targetScore * 100).toFixed(1)}%
              </p>
              <p className="text-sm">
                <strong>Status:</strong>{' '}
                {targetReached ? (
                  <span className="text-green-700 font-semibold">Target Reached ✓</span>
                ) : (
                  <span className="text-yellow-700 font-semibold">
                    {((targetScore - currentScore) * 100).toFixed(1)}% away from target
                  </span>
                )}
              </p>
            </div>
          </div>

          {/* Loop Control */}
          {!targetReached && !loopComplete && (
            <div className="bg-blue-50 border border-blue-200 rounded p-4 mb-4">
              <h4 className="font-semibold mb-2">Continue Enhancement Loop?</h4>
              <p className="text-sm text-gray-700 mb-3">
                Target not yet reached. You can run another iteration to continue improving.
              </p>
              <p className="text-sm text-gray-600 mb-4">
                Iterations remaining: {maxIterations - currentIteration}
              </p>

              {continuing ? (
                <div className="text-center py-4">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
                  <p className="text-sm">Starting next iteration...</p>
                </div>
              ) : (
                <div className="flex gap-3">
                  <button
                    onClick={() => setLoopComplete(true)}
                    className="px-6 py-2 border rounded hover:bg-gray-50"
                  >
                    Stop Here
                  </button>
                  <button
                    onClick={continueLoop}
                    disabled={currentIteration >= maxIterations}
                    className="bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700 disabled:bg-gray-400"
                  >
                    Continue to Iteration {currentIteration + 1}
                  </button>
                </div>
              )}
            </div>
          )}

          {(targetReached || loopComplete) && (
            <div className="bg-white border rounded p-4">
              <h4 className="font-semibold mb-2">Enhancement Complete</h4>
              {targetReached && (
                <p className="text-sm text-gray-700 mb-4">
                  🎉 Target score reached after {currentIteration} iteration{currentIteration > 1 ? 's' : ''}!
                </p>
              )}
              {loopComplete && !targetReached && (
                <p className="text-sm text-gray-700 mb-4">
                  {loopReason || 'Enhancement loop stopped.'}
                </p>
              )}

              {/* Deployment Options */}
              {state.dev_best_id && (
                <div className="mb-4 p-3 bg-gray-50 rounded">
                  <h5 className="font-medium mb-2">Deploy Configuration</h5>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={saveToBest}
                      disabled={savingToBest || savedToBest}
                      className={`px-4 py-2 rounded text-sm ${
                        savedToBest
                          ? 'bg-green-100 text-green-700 border border-green-300'
                          : 'bg-yellow-500 text-white hover:bg-yellow-600'
                      } disabled:opacity-50`}
                    >
                      {savingToBest ? 'Saving...' : savedToBest ? '✓ Saved to Best' : '💾 Save to Best Space'}
                    </button>

                    {state.production_space_id && (
                      <button
                        onClick={promoteToProduction}
                        disabled={promotingToProd || promotedToProd}
                        className={`px-4 py-2 rounded text-sm ${
                          promotedToProd
                            ? 'bg-green-100 text-green-700 border border-green-300'
                            : 'bg-red-500 text-white hover:bg-red-600'
                        } disabled:opacity-50`}
                      >
                        {promotingToProd ? 'Promoting...' : promotedToProd ? '✓ Promoted to Production' : '🚀 Promote to Production'}
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    {savedToBest && 'Best space updated. '}
                    {promotedToProd && 'Production space updated!'}
                    {!savedToBest && !promotedToProd && 'Save your improvements to the best space, or promote directly to production.'}
                  </p>
                </div>
              )}

              <button
                onClick={() => window.location.reload()}
                className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
              >
                Start New Enhancement
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
