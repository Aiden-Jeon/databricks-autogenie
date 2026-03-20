/**
 * Benchmark step component for managing benchmark questions.
 */

'use client';

import { useState, useEffect } from 'react';
import { useJobPolling } from '@/lib/hooks/useJobPolling';
import { apiClient } from '@/lib/api-client';
import { BenchmarkFixer } from './BenchmarkFixer';

interface Benchmark {
  question: string;         // Required (Korean question)
  expected_sql: string;     // Required
  id?: string;              // Optional
  korean_question?: string; // Optional (for backward compatibility)
  source_file?: string;     // Optional
  question_number?: number; // Optional
}

interface BenchmarkStepProps {
  sessionId: string;
  onComplete: (benchmarks: Benchmark[]) => void;
  onPrevious: () => void;
  existingResult?: Benchmark[];
}

export function BenchmarkStep({ sessionId, onComplete, onPrevious, existingResult }: BenchmarkStepProps) {
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>(existingResult || []);
  const [showingExistingResult, setShowingExistingResult] = useState(!!existingResult);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [expandedSql, setExpandedSql] = useState<Set<number>>(new Set());
  const [validationErrors, setValidationErrors] = useState<Map<number, string[]>>(new Map());
  const [jobId, setJobId] = useState<string | null>(null);
  const [sqlValidationResults, setSqlValidationResults] = useState<any>(null);
  const [showSqlFixer, setShowSqlFixer] = useState(false);
  const { job, isPolling, error: jobError } = useJobPolling(jobId);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const data = JSON.parse(text);

      // Accept both formats: plain array [...] or wrapped {benchmarks: [...]}
      let parsed: Benchmark[] | null = null;
      if (Array.isArray(data)) {
        parsed = data;
      } else if (data.benchmarks && Array.isArray(data.benchmarks)) {
        parsed = data.benchmarks;
      }

      if (parsed && parsed.length > 0) {
        setBenchmarks(parsed);
        setShowingExistingResult(false);
      } else {
        alert('Invalid benchmark file format. Expected a JSON array of benchmarks.');
      }
    } catch (error) {
      alert('Failed to parse JSON file: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  };

  const addNewBenchmark = () => {
    setBenchmarks([...benchmarks, { question: '', expected_sql: '' }]);
    setEditingIndex(benchmarks.length);
  };

  const updateBenchmark = (index: number, field: keyof Benchmark, value: string) => {
    const updated = [...benchmarks];
    updated[index] = { ...updated[index], [field]: value };
    setBenchmarks(updated);
  };

  const deleteBenchmark = (index: number) => {
    setBenchmarks(benchmarks.filter((_, i) => i !== index));
    if (editingIndex === index) setEditingIndex(null);
  };

  const duplicateBenchmark = (index: number) => {
    const duplicate = { ...benchmarks[index], id: undefined };
    setBenchmarks([...benchmarks, duplicate]);
  };

  const toggleSqlExpansion = (index: number) => {
    const newExpanded = new Set(expandedSql);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedSql(newExpanded);
  };

  const getSqlPreview = (sql: string, isExpanded: boolean) => {
    if (!sql) return '';
    const lines = sql.trim().split('\n');
    if (isExpanded || lines.length <= 3) {
      return sql;
    }
    const preview = lines.slice(0, 3).join('\n');
    const remaining = lines.length - 3;
    return `${preview}\n... ${remaining} more lines`;
  };

  const validateBenchmarks = (): boolean => {
    const errors = new Map<number, string[]>();
    let hasErrors = false;

    benchmarks.forEach((benchmark, index) => {
      const benchmarkErrors: string[] = [];

      if (!benchmark.question || benchmark.question.trim() === '') {
        benchmarkErrors.push('Question is required');
        hasErrors = true;
      }

      if (!benchmark.expected_sql || benchmark.expected_sql.trim() === '') {
        benchmarkErrors.push('Expected SQL is required');
        hasErrors = true;
      }

      if (benchmarkErrors.length > 0) {
        errors.set(index, benchmarkErrors);
      }
    });

    console.log('Validation errors:', errors, 'hasErrors:', hasErrors);
    setValidationErrors(errors);
    return !hasErrors;
  };

  const handleContinue = () => {
    if (benchmarks.length > 0 && !validateBenchmarks()) {
      return; // Don't continue if validation fails
    }
    onComplete(benchmarks);
  };

  const handleSkipValidation = () => {
    setValidationErrors(new Map()); // Clear validation errors
    onComplete(benchmarks);
  };

  const handleValidateSql = async () => {
    if (benchmarks.length === 0) {
      alert('No benchmarks to validate');
      return;
    }

    try {
      setSqlValidationResults(null);
      const response = await apiClient.validateBenchmarks(sessionId, benchmarks);
      setJobId(response.job_id);
    } catch (err) {
      console.error('Failed to start benchmark validation:', err);
      alert('Failed to start benchmark validation: ' + (err instanceof Error ? err.message : 'Unknown error'));
    }
  };

  // Update SQL validation results when job completes
  useEffect(() => {
    if (job?.status === 'completed' && job.result) {
      setSqlValidationResults(job.result);
      // Show fixer if there are errors
      if (job.result.has_errors) {
        setShowSqlFixer(true);
      }
    }
  }, [job]);

  const handleFixQuery = (index: number, newSql: string) => {
    // Update the benchmark with the fixed SQL
    const updated = [...benchmarks];
    updated[index] = { ...updated[index], expected_sql: newSql };
    setBenchmarks(updated);
  };

  const handleRemoveFailedQueries = () => {
    if (!sqlValidationResults) return;

    const failedIndices = new Set(
      sqlValidationResults.results
        .filter((r: any) => r.status === 'failed')
        .map((r: any) => r.index)
    );

    const filtered = benchmarks.filter((_, idx) => !failedIndices.has(idx));
    setBenchmarks(filtered);
    setSqlValidationResults(null);
    setShowSqlFixer(false);
  };

  const handleRevalidate = () => {
    setSqlValidationResults(null);
    setShowSqlFixer(false);
    handleValidateSql();
  };

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Step 4: Benchmark Questions</h2>
      <p className="text-gray-600">
        Upload benchmark questions to test your Genie space (optional).
      </p>

      {/* Show existing result if navigating back with benchmarks */}
      {showingExistingResult && existingResult && existingResult.length > 0 && (
        <div className="space-y-4">
          <div className="bg-green-50 p-4 rounded-lg border border-green-200">
            <p className="font-semibold text-green-800">✓ Benchmarks Loaded</p>
            <p className="text-sm text-gray-600 mt-1">
              {existingResult.length} benchmark question{existingResult.length > 1 ? 's' : ''} ready
            </p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={onPrevious}
              className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              ← Back to Validate
            </button>
            <button
              onClick={() => setShowingExistingResult(false)}
              className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              Edit Benchmarks
            </button>
            <button
              onClick={handleContinue}
              className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            >
              Continue to Deploy →
            </button>
          </div>
        </div>
      )}

      {/* Show existing result if navigating back WITHOUT benchmarks (skipped) */}
      {showingExistingResult && existingResult && existingResult.length === 0 && (
        <div className="space-y-4">
          <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
            <p className="font-semibold text-gray-700">No Benchmarks</p>
            <p className="text-sm text-gray-600 mt-1">
              You skipped benchmarks in the previous step.
            </p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={onPrevious}
              className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              ← Back to Validate
            </button>
            <button
              onClick={() => setShowingExistingResult(false)}
              className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              Add Benchmarks
            </button>
            <button
              onClick={handleContinue}
              className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            >
              Continue to Deploy →
            </button>
          </div>
        </div>
      )}

      {!showingExistingResult && (
        <>
          {/* File upload */}
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-6">
            <label className="block text-sm font-medium mb-2">Upload Benchmark JSON File:</label>
            <input
              type="file"
              accept=".json"
              onChange={handleFileUpload}
              className="w-full"
            />
            <p className="text-xs text-gray-500 mt-2">
              JSON array of benchmarks. Required fields: <code className="bg-gray-100 px-1">question</code>, <code className="bg-gray-100 px-1">expected_sql</code>
              <br />
              Optional: <code className="bg-gray-100 px-1">category</code>, <code className="bg-gray-100 px-1">description</code>
            </p>
          </div>

          {/* Benchmarks table */}
          {benchmarks.length > 0 && (
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <h3 className="text-lg font-semibold">
                  Benchmarks ({benchmarks.length})
                </h3>
                <div className="flex gap-2">
                  <button
                    onClick={handleValidateSql}
                    disabled={isPolling}
                    className="px-4 py-2 bg-purple-500 text-white rounded hover:bg-purple-600 text-sm disabled:bg-gray-400 disabled:cursor-not-allowed"
                  >
                    {isPolling ? 'Validating...' : 'Validate SQL'}
                  </button>
                  <button
                    onClick={addNewBenchmark}
                    className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 text-sm"
                  >
                    + Add Benchmark
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                {benchmarks.map((benchmark, index) => {
                  const errors = validationErrors.get(index);
                  const hasErrors = errors && errors.length > 0;

                  return (
                  <div
                    key={index}
                    className={`border rounded-lg overflow-hidden ${
                      hasErrors ? 'border-red-500 bg-red-50' : 'border-gray-300'
                    }`}
                  >
                    <div className="grid grid-cols-2 gap-0">
                      {/* Question column */}
                      <div className="p-4 border-r border-gray-300 bg-gray-50">
                        <div className="flex justify-between items-start mb-2">
                          <h4 className="text-sm font-semibold text-gray-700">Question</h4>
                          <div className="flex gap-2">
                            <button
                              onClick={() => duplicateBenchmark(index)}
                              className="text-gray-500 hover:text-gray-700"
                              title="Duplicate"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                              </svg>
                            </button>
                            <button
                              onClick={() => deleteBenchmark(index)}
                              className="text-red-500 hover:text-red-700"
                              title="Delete"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>
                        </div>
                        {editingIndex === index ? (
                          <textarea
                            value={benchmark.question}
                            onChange={(e) => updateBenchmark(index, 'question', e.target.value)}
                            className="w-full p-2 border border-gray-300 rounded text-sm min-h-[100px]"
                            placeholder="Enter question... (Required)"
                          />
                        ) : (
                          <p
                            className="text-sm cursor-pointer hover:bg-gray-100 p-2 rounded"
                            onClick={() => setEditingIndex(index)}
                          >
                            {benchmark.question || benchmark.korean_question || <span className="text-gray-400">Click to edit...</span>}
                          </p>
                        )}
                      </div>

                      {/* SQL column */}
                      <div className="p-4 bg-white">
                        <div className="flex justify-between items-start mb-2">
                          <h4 className="text-sm font-semibold text-gray-700">Ground truth SQL answer</h4>
                          <button
                            onClick={() => setEditingIndex(editingIndex === index ? null : index)}
                            className="text-gray-500 hover:text-gray-700"
                            title="Edit"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                          </button>
                        </div>
                        {editingIndex === index ? (
                          <textarea
                            value={benchmark.expected_sql}
                            onChange={(e) => updateBenchmark(index, 'expected_sql', e.target.value)}
                            className="w-full p-2 border border-gray-300 rounded text-sm font-mono min-h-[100px]"
                            placeholder="Enter SQL..."
                          />
                        ) : (
                          <div>
                            <pre
                              className="text-xs font-mono bg-gray-50 p-2 rounded overflow-x-auto cursor-pointer hover:bg-gray-100"
                              onClick={() => toggleSqlExpansion(index)}
                            >
                              <code className="text-blue-600">
                                {getSqlPreview(benchmark.expected_sql, expandedSql.has(index))}
                              </code>
                            </pre>
                            {benchmark.expected_sql && benchmark.expected_sql.split('\n').length > 3 && (
                              <button
                                onClick={() => toggleSqlExpansion(index)}
                                className="text-xs text-blue-500 hover:text-blue-700 mt-1"
                              >
                                {expandedSql.has(index) ? 'Show less' : 'Show more'}
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Validation errors */}
                    {hasErrors && (
                      <div className="px-4 py-3 bg-red-100 border-t border-red-300">
                        <p className="text-sm font-semibold text-red-800 mb-1">Validation Errors:</p>
                        <ul className="text-xs text-red-700 list-disc list-inside">
                          {errors!.map((error, i) => (
                            <li key={i}>{error}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* SQL Validation Progress */}
          {isPolling && (
            <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
              <p className="font-semibold">Validating benchmark SQL queries...</p>
              <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                <div className="bg-blue-500 h-2 rounded-full animate-pulse" style={{ width: '60%' }} />
              </div>
              <p className="text-sm text-gray-600 mt-2">Executing queries against Unity Catalog</p>
            </div>
          )}

          {/* SQL Validation Error */}
          {jobError && (
            <div className="bg-red-50 p-4 rounded-lg border border-red-200 text-red-700">
              <p className="font-semibold">Validation Error</p>
              <p>{jobError}</p>
            </div>
          )}

          {/* SQL Validation Results */}
          {sqlValidationResults && (
            <div className="space-y-3">
              {/* Success Banner */}
              {!sqlValidationResults.has_errors && (
                <div className="bg-green-50 p-6 rounded-lg border-2 border-green-300 shadow-lg">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="text-4xl">✅</div>
                    <div>
                      <h3 className="text-2xl font-bold text-green-800">All Benchmark Queries Passed!</h3>
                      <p className="text-green-700 text-lg">
                        {sqlValidationResults.total_benchmarks} {sqlValidationResults.total_benchmarks === 1 ? 'query' : 'queries'} executed successfully
                      </p>
                    </div>
                  </div>
                  <p className="text-sm text-gray-600">
                    All SQL queries are valid and ready to be used as benchmarks.
                  </p>
                </div>
              )}

              {/* Failure Banner */}
              {sqlValidationResults.has_errors && (
                <div className="bg-red-50 p-6 rounded-lg border-2 border-red-300 shadow-lg">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="text-4xl">⚠️</div>
                    <div>
                      <h3 className="text-2xl font-bold text-red-800">Validation Failed</h3>
                      <p className="text-red-700 text-lg">
                        {sqlValidationResults.failed} of {sqlValidationResults.total_benchmarks} {sqlValidationResults.total_benchmarks === 1 ? 'query' : 'queries'} failed
                      </p>
                    </div>
                  </div>
                  <p className="text-sm text-gray-600">
                    Fix the errors below or exclude failing benchmarks to continue.
                  </p>
                </div>
              )}

              {/* Show failed queries */}
              {sqlValidationResults.results?.filter((r: any) => r.status === 'failed').map((result: any) => (
                <div key={result.index} className="bg-red-50 p-4 rounded-lg border border-red-300">
                  <div className="flex justify-between items-start mb-2">
                    <h4 className="font-semibold text-red-800">
                      Benchmark #{result.index + 1}: {result.question}
                    </h4>
                    <span className="text-xs bg-red-200 text-red-800 px-2 py-1 rounded">FAILED</span>
                  </div>
                  <div className="text-sm text-red-700 mb-2">
                    <strong>Error:</strong> {result.error}
                  </div>
                  <details className="text-xs">
                    <summary className="cursor-pointer text-red-600 hover:text-red-800">Show SQL</summary>
                    <pre className="mt-2 bg-white p-2 rounded border border-red-200 overflow-x-auto">
                      <code>{result.sql}</code>
                    </pre>
                  </details>
                </div>
              ))}

              {/* Show passed queries summary */}
              {sqlValidationResults.passed > 0 && !showSqlFixer && (
                <details className="bg-green-50 p-4 rounded-lg border border-green-200">
                  <summary className="cursor-pointer font-semibold text-green-800">
                    ✓ {sqlValidationResults.passed} Passed Queries
                  </summary>
                  <div className="mt-3 space-y-2">
                    {sqlValidationResults.results?.filter((r: any) => r.status === 'passed').map((result: any) => (
                      <div key={result.index} className="text-sm">
                        <span className="font-medium">#{result.index + 1}:</span> {result.question}
                        <span className="text-gray-600 ml-2">
                          ({result.row_count} rows, {result.execution_time_ms}ms)
                        </span>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}

          {/* Benchmark Fixer */}
          {showSqlFixer && sqlValidationResults?.results && (
            <BenchmarkFixer
              results={sqlValidationResults.results}
              onFixQuery={handleFixQuery}
              onRemoveFailedQueries={handleRemoveFailedQueries}
              onRevalidate={handleRevalidate}
            />
          )}

          {/* Action buttons */}
          <div className="space-y-3 pt-4">
            {/* Show validation error summary if there are errors */}
            {validationErrors.size > 0 && (
              <div className="bg-red-50 p-4 rounded-lg border border-red-200">
                <p className="text-sm font-semibold text-red-800 mb-2">
                  ⚠️ {validationErrors.size} benchmark{validationErrors.size > 1 ? 's have' : ' has'} validation errors
                </p>
                <p className="text-xs text-red-700">
                  Fix the errors and try again, or skip validation to continue anyway.
                </p>
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={onPrevious}
                className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
              >
                ← Previous
              </button>
              {benchmarks.length === 0 ? (
                <button
                  onClick={() => onComplete([])}
                  className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                >
                  Skip Benchmarks & Continue to Deploy →
                </button>
              ) : validationErrors.size > 0 ? (
                <>
                  <button
                    onClick={handleContinue}
                    className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                  >
                    Fix Errors & Validate Again
                  </button>
                  <button
                    onClick={handleSkipValidation}
                    className="flex-1 px-6 py-3 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 transition-colors"
                  >
                    Skip Validation & Continue Anyway →
                  </button>
                </>
              ) : sqlValidationResults && !sqlValidationResults.has_errors ? (
                <button
                  onClick={handleContinue}
                  className="flex-1 px-6 py-3 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors font-semibold"
                >
                  ✓ All Queries Validated - Continue to Deploy →
                </button>
              ) : sqlValidationResults && sqlValidationResults.has_errors ? (
                <>
                  <button
                    onClick={handleValidateSql}
                    disabled={isPolling}
                    className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:bg-gray-400"
                  >
                    Re-validate After Fixes
                  </button>
                  <button
                    onClick={handleSkipValidation}
                    className="flex-1 px-6 py-3 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 transition-colors"
                  >
                    Continue Despite Errors →
                  </button>
                </>
              ) : (
                <button
                  onClick={handleContinue}
                  className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                >
                  Save {benchmarks.length} Benchmark{benchmarks.length > 1 ? 's' : ''} & Continue →
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
