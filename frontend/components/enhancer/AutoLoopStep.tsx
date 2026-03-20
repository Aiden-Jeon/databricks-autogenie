/**
 * Auto-Loop Mode: Automatic enhancement loop with progress monitoring
 */

'use client';

import { useState, useEffect } from 'react';

interface AutoLoopStepProps {
  state: any;
  onUpdate: (updates: any) => void;
  onBack: () => void;
  sessionId: string | null;
}

interface LoopProgress {
  iteration: number;
  max_iterations: number;
  phase: string;
  current_score: number;
  target_score: number;
  message: string;
  // Phase-specific
  completed?: number;
  total?: number;
  successful?: number;
  failed?: number;
}

interface IterationResult {
  iteration: number;
  score_before?: number;
  fixes_applied?: number;
  status: string;
}

interface Warehouse {
  id: string;
  name: string;
  state: string;
}

interface GenieSpace {
  id: string;
  name: string;
  description?: string;
}

export function AutoLoopStep({ state, onUpdate, onBack, sessionId }: AutoLoopStepProps) {
  const [file, setFile] = useState<File | null>(null);
  const [targetScore, setTargetScore] = useState(90);
  const [maxIterations, setMaxIterations] = useState(5);

  // Configuration state
  const [warehouseId, setWarehouseId] = useState(state.warehouse_id || '');
  const [spaceId, setSpaceId] = useState(state.space_id || '');
  const [llmEndpoint, setLlmEndpoint] = useState(state.llm_endpoint || 'databricks-gpt-5-2');

  // Resource lists
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [spaces, setSpaces] = useState<GenieSpace[]>([]);
  const [loadingWarehouses, setLoadingWarehouses] = useState(false);
  const [loadingSpaces, setLoadingSpaces] = useState(false);

  const [running, setRunning] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<LoopProgress | null>(null);
  const [iterations, setIterations] = useState<IterationResult[]>([]);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  // Fetch warehouses and spaces on mount
  useEffect(() => {
    const fetchResources = async () => {
      // Fetch warehouses
      setLoadingWarehouses(true);
      try {
        const whResponse = await fetch('/api/enhancer/workspace/warehouses');
        const whData = await whResponse.json();
        if (!whData.error) {
          setWarehouses(whData.warehouses || []);
        }
      } catch (err) {
        console.error('Failed to fetch warehouses:', err);
      } finally {
        setLoadingWarehouses(false);
      }

      // Fetch Genie spaces
      setLoadingSpaces(true);
      try {
        const spaceResponse = await fetch('/api/enhancer/workspace/spaces');
        const spaceData = await spaceResponse.json();
        if (!spaceData.error) {
          setSpaces(spaceData.spaces || []);
        }
      } catch (err) {
        console.error('Failed to fetch spaces:', err);
      } finally {
        setLoadingSpaces(false);
      }
    };

    fetchResources();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError('');
    }
  };

  const startAutoLoop = async () => {
    if (!file || !sessionId || !warehouseId || !spaceId) return;

    setRunning(true);
    setError('');
    setIterations([]);
    setResult(null);

    // Update parent state with selected values
    onUpdate({
      warehouse_id: warehouseId,
      space_id: spaceId,
      llm_endpoint: llmEndpoint
    });

    try {
      // Upload benchmarks
      const formData = new FormData();
      formData.append('file', file);

      const uploadResponse = await fetch(`/api/enhancer/sessions/${sessionId}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!uploadResponse.ok) {
        throw new Error(`Upload failed: ${uploadResponse.status}`);
      }

      const uploadData = await uploadResponse.json();
      const benchmarks = uploadData.benchmarks;

      // Clone space for safety
      let finalSpaceId = spaceId;
      if (state.use_clone !== false) {
        try {
          const cloneResponse = await fetch(`/api/enhancer/sessions/${sessionId}/clone-space`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ space_id: spaceId })
          });

          if (cloneResponse.ok) {
            const cloneData = await cloneResponse.json();
            finalSpaceId = cloneData.dev_working_id;
            onUpdate({
              production_space_id: cloneData.production_id,
              dev_working_id: cloneData.dev_working_id,
              space_id: finalSpaceId
            });
          }
        } catch (err) {
          console.error('Clone error:', err);
        }
      }

      // Start auto-loop
      const response = await fetch(`/api/enhancer/sessions/${sessionId}/auto-loop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_config: {
            warehouse_id: warehouseId,
            space_id: finalSpaceId,
            llm_endpoint: llmEndpoint,
          },
          benchmarks,
          target_score: targetScore / 100,
          max_iterations: maxIterations,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to start auto-loop: ${response.status}`);
      }

      const data = await response.json();
      setJobId(data.job_id);

      // Poll for progress
      pollProgress(data.job_id);
    } catch (err: any) {
      setError(err.message || 'Failed to start auto-loop');
      setRunning(false);
    }
  };

  const pollProgress = async (jobId: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/jobs/${jobId}`);
        const job = await response.json();

        // Update progress
        if (job.progress?.current) {
          const prog = job.progress.current;
          setProgress(prog);

          // Track iteration results
          if (prog.phase === 'auto_loop' && prog.iteration) {
            setIterations(prev => {
              const existing = prev.find(i => i.iteration === prog.iteration);
              if (!existing) {
                return [...prev, {
                  iteration: prog.iteration,
                  score_before: prog.current_score,
                  status: 'running'
                }];
              }
              return prev.map(i =>
                i.iteration === prog.iteration
                  ? { ...i, score_before: prog.current_score }
                  : i
              );
            });
          }
        }

        if (job.status === 'completed') {
          clearInterval(interval);
          setRunning(false);
          setResult(job.result);

          // Update iterations from result
          if (job.result?.iterations) {
            setIterations(job.result.iterations);
          }

          onUpdate({ autoLoopResult: job.result });
        } else if (job.status === 'failed') {
          clearInterval(interval);
          setRunning(false);
          setError('Auto-loop failed: ' + (job.error || 'Unknown error'));
        }
      } catch (err) {
        console.error('Error polling:', err);
      }
    }, 1500);
  };

  const stopJob = async () => {
    if (!jobId) return;

    try {
      await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      setRunning(false);
      setError('Auto-loop stopped by user');
    } catch (err) {
      console.error('Failed to stop job:', err);
    }
  };

  const getPhaseIcon = (phase: string) => {
    switch (phase) {
      case 'genie': return '🤖';
      case 'sql': return '🔄';
      case 'eval': return '🧠';
      case 'auto_loop': return '🔁';
      default: return '⏳';
    }
  };

  const getPhaseLabel = (phase: string) => {
    switch (phase) {
      case 'genie': return 'Querying Genie';
      case 'sql': return 'Executing SQL';
      case 'eval': return 'Evaluating Results';
      case 'auto_loop': return 'Processing';
      default: return 'Working';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">🔄 Auto-Loop Mode</h2>
        <button
          onClick={onBack}
          className="text-gray-600 hover:text-gray-800"
        >
          ← Back to Manual Mode
        </button>
      </div>

      <p className="text-gray-600">
        Automatically run Score → Plan → Apply cycles until target score is reached.
        All proposed fixes will be applied automatically.
      </p>

      {!running && !result && (
        <div className="space-y-6">
          {/* Workspace Configuration */}
          <div className="p-4 border rounded-lg space-y-4">
            <h3 className="font-semibold text-gray-900">Workspace Configuration</h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700">SQL Warehouse</label>
                {loadingWarehouses ? (
                  <div className="text-sm text-gray-500 py-2">Loading warehouses...</div>
                ) : warehouses.length > 0 ? (
                  <select
                    value={warehouseId}
                    onChange={(e) => setWarehouseId(e.target.value)}
                    className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
                  >
                    <option value="">Select a warehouse...</option>
                    {warehouses.map((wh) => (
                      <option key={wh.id} value={wh.id}>
                        {wh.name} ({wh.state})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={warehouseId}
                    onChange={(e) => setWarehouseId(e.target.value)}
                    placeholder="Enter warehouse ID manually..."
                    className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
                  />
                )}
              </div>

              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700">Genie Space</label>
                {loadingSpaces ? (
                  <div className="text-sm text-gray-500 py-2">Loading spaces...</div>
                ) : spaces.length > 0 ? (
                  <select
                    value={spaceId}
                    onChange={(e) => setSpaceId(e.target.value)}
                    className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
                  >
                    <option value="">Select a space...</option>
                    {spaces.map((space) => (
                      <option key={space.id} value={space.id}>
                        {space.name} ({space.id})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={spaceId}
                    onChange={(e) => setSpaceId(e.target.value)}
                    placeholder="Enter space ID manually..."
                    className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
                  />
                )}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-700">LLM Endpoint</label>
              <select
                value={llmEndpoint}
                onChange={(e) => setLlmEndpoint(e.target.value)}
                className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
              >
                <option value="databricks-gpt-5-2">databricks-gpt-5-2</option>
                <option value="databricks-gpt-4-turbo">databricks-gpt-4-turbo</option>
              </select>
            </div>
          </div>

          {/* Benchmark and Loop Configuration */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="p-4 border rounded-lg">
              <label className="block text-sm font-medium mb-2">Benchmark File (JSON)</label>
              <input
                type="file"
                accept=".json"
                onChange={handleFileChange}
                className="w-full text-gray-900"
              />
              {file && <p className="text-sm text-green-600 mt-1">✓ {file.name}</p>}
            </div>

            <div className="p-4 border rounded-lg space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Target Score</label>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min="50"
                    max="100"
                    value={targetScore}
                    onChange={(e) => setTargetScore(Number(e.target.value))}
                    className="flex-1"
                  />
                  <span className="font-bold text-lg w-16 text-right">{targetScore}%</span>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Max Iterations</label>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min="1"
                    max="10"
                    value={maxIterations}
                    onChange={(e) => setMaxIterations(Number(e.target.value))}
                    className="flex-1"
                  />
                  <span className="font-bold text-lg w-16 text-right">{maxIterations}</span>
                </div>
              </div>
            </div>
          </div>

          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded text-red-700">
              {error}
            </div>
          )}

          <button
            onClick={startAutoLoop}
            disabled={!file || !sessionId || !warehouseId || !spaceId}
            className="w-full bg-purple-600 text-white py-3 px-6 rounded-lg text-lg font-semibold hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            🚀 Start Auto-Loop
          </button>

          {(!warehouseId || !spaceId) && (
            <p className="text-sm text-amber-600 text-center">
              Please select both SQL Warehouse and Genie Space to start
            </p>
          )}
        </div>
      )}

      {running && (
        <div className="space-y-6">
          {/* Main Progress Card */}
          <div className="p-6 border-2 border-purple-300 rounded-lg bg-purple-50">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-xl font-bold text-purple-800">
                  Iteration {progress?.iteration || 1} of {progress?.max_iterations || maxIterations}
                </h3>
                <p className="text-purple-600">
                  {progress?.message || 'Starting...'}
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm text-gray-600">Current Score</p>
                <p className="text-3xl font-bold text-purple-700">
                  {progress?.current_score !== undefined
                    ? `${(progress.current_score * 100).toFixed(1)}%`
                    : '--'}
                </p>
              </div>
            </div>

            {/* Phase Progress */}
            {progress && progress.phase !== 'auto_loop' && progress.total && (
              <div className="mt-4">
                <div className="flex justify-between text-sm mb-1">
                  <span>{getPhaseIcon(progress.phase)} {getPhaseLabel(progress.phase)}</span>
                  <span>{progress.completed || 0}/{progress.total}</span>
                </div>
                <div className="w-full bg-purple-200 rounded-full h-2">
                  <div
                    className="bg-purple-600 h-2 rounded-full transition-all"
                    style={{ width: `${((progress.completed || 0) / progress.total) * 100}%` }}
                  />
                </div>
                {progress.successful !== undefined && (
                  <div className="flex gap-4 mt-2 text-sm">
                    <span className="text-green-600">✓ {progress.successful} success</span>
                    <span className="text-red-600">✗ {progress.failed || 0} failed</span>
                  </div>
                )}
              </div>
            )}

            {/* Iteration Progress Bar */}
            <div className="mt-6">
              <div className="flex justify-between text-sm mb-1">
                <span>Overall Progress</span>
                <span>Target: {targetScore}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-3">
                <div
                  className="bg-gradient-to-r from-purple-500 to-purple-700 h-3 rounded-full transition-all"
                  style={{ width: `${((progress?.iteration || 1) / maxIterations) * 100}%` }}
                />
              </div>
            </div>
          </div>

          {/* Iteration History */}
          {iterations.length > 0 && (
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 font-semibold border-b">
                Iteration History
              </div>
              <div className="divide-y">
                {iterations.map((iter, idx) => (
                  <div key={idx} className="px-4 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className={`w-8 h-8 rounded-full flex items-center justify-center text-white ${
                        iter.status === 'completed' ? 'bg-green-500' :
                        iter.status === 'running' ? 'bg-purple-500 animate-pulse' :
                        'bg-gray-400'
                      }`}>
                        {iter.iteration}
                      </span>
                      <div>
                        <p className="font-medium">Iteration {iter.iteration}</p>
                        <p className="text-sm text-gray-600">
                          {iter.fixes_applied !== undefined
                            ? `${iter.fixes_applied} fixes applied`
                            : iter.status === 'running' ? 'In progress...' : 'Pending'}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      {iter.score_before !== undefined && (
                        <p className="font-bold">
                          {(iter.score_before * 100).toFixed(1)}%
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Stop Button */}
          <button
            onClick={stopJob}
            className="w-full bg-red-600 text-white py-3 px-6 rounded-lg font-semibold hover:bg-red-700"
          >
            ⏹️ Stop Auto-Loop
          </button>
        </div>
      )}

      {result && (
        <div className="space-y-6">
          {/* Result Summary */}
          <div className={`p-6 rounded-lg ${
            result.target_reached ? 'bg-green-100 border-2 border-green-400' : 'bg-yellow-100 border-2 border-yellow-400'
          }`}>
            <h3 className="text-2xl font-bold mb-4">
              {result.target_reached ? '🎉 Target Reached!' : '⚠️ Loop Completed'}
            </h3>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white/50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Initial Score</p>
                <p className="text-2xl font-bold">{((result.initial_score || 0) * 100).toFixed(1)}%</p>
              </div>
              <div className="bg-white/50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Final Score</p>
                <p className="text-2xl font-bold">{((result.final_score || 0) * 100).toFixed(1)}%</p>
              </div>
              <div className="bg-white/50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Improvement</p>
                <p className="text-2xl font-bold text-green-600">
                  +{((result.improvement || 0) * 100).toFixed(1)}%
                </p>
              </div>
              <div className="bg-white/50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Iterations</p>
                <p className="text-2xl font-bold">{result.iterations_completed || 0}</p>
              </div>
            </div>
          </div>

          {/* Iteration Details */}
          {result.iterations && result.iterations.length > 0 && (
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 font-semibold border-b">
                Iteration Details
              </div>
              <div className="divide-y">
                {result.iterations.map((iter: any, idx: number) => (
                  <div key={idx} className="px-4 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className={`w-8 h-8 rounded-full flex items-center justify-center text-white ${
                        iter.status === 'target_reached' ? 'bg-green-500' :
                        iter.status === 'completed' ? 'bg-blue-500' :
                        'bg-gray-400'
                      }`}>
                        {iter.iteration}
                      </span>
                      <div>
                        <p className="font-medium">Iteration {iter.iteration}</p>
                        <p className="text-sm text-gray-600">
                          {iter.status === 'target_reached' ? '🎯 Target reached' :
                           iter.fixes_applied ? `${iter.fixes_applied} fixes applied` :
                           iter.status}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      {iter.score_before !== undefined && (
                        <p className="font-bold">{(iter.score_before * 100).toFixed(1)}%</p>
                      )}
                      {iter.score !== undefined && (
                        <p className="font-bold">{(iter.score * 100).toFixed(1)}%</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <button
            onClick={() => {
              setResult(null);
              setIterations([]);
              setProgress(null);
              setFile(null);
            }}
            className="w-full bg-purple-600 text-white py-3 px-6 rounded-lg font-semibold hover:bg-purple-700"
          >
            Run Another Auto-Loop
          </button>
        </div>
      )}
    </div>
  );
}
