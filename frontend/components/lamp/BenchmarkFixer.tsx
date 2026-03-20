/**
 * Interactive benchmark fixer component.
 * Allows users to fix failed benchmark queries inline.
 */

'use client';

import { useState } from 'react';

interface BenchmarkResult {
  index: number;
  question: string;
  sql: string;
  status: 'passed' | 'failed';
  error: string | null;
  row_count: number | null;
  execution_time_ms: number | null;
}

interface BenchmarkFixerProps {
  results: BenchmarkResult[];
  onFixQuery: (index: number, newSql: string) => void;
  onRemoveFailedQueries: () => void;
  onRevalidate: () => void;
}

export function BenchmarkFixer({ results, onFixQuery, onRemoveFailedQueries, onRevalidate }: BenchmarkFixerProps) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editedSql, setEditedSql] = useState<string>('');
  const [expandedErrors, setExpandedErrors] = useState<Set<number>>(new Set());

  const failedResults = results.filter(r => r.status === 'failed');
  const passedResults = results.filter(r => r.status === 'passed');

  const handleStartEdit = (index: number, currentSql: string) => {
    setEditingIndex(index);
    setEditedSql(currentSql);
  };

  const handleSaveEdit = (index: number) => {
    onFixQuery(index, editedSql);
    setEditingIndex(null);
    setEditedSql('');
  };

  const handleCancelEdit = () => {
    setEditingIndex(null);
    setEditedSql('');
  };

  const toggleErrorExpansion = (index: number) => {
    const newExpanded = new Set(expandedErrors);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedErrors(newExpanded);
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-orange-50 p-4 rounded-lg border border-orange-200">
        <h3 className="text-lg font-semibold text-orange-800 mb-2">
          🔧 Fix Benchmark Queries
        </h3>
        <p className="text-sm text-gray-700">
          {failedResults.length} {failedResults.length === 1 ? 'query' : 'queries'} failed validation.
          You can edit the SQL below or remove failed benchmarks.
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-red-50 p-4 rounded-lg border border-red-200">
          <div className="text-2xl font-bold text-red-800">{failedResults.length}</div>
          <div className="text-sm text-red-700">Failed Queries</div>
        </div>
        <div className="bg-green-50 p-4 rounded-lg border border-green-200">
          <div className="text-2xl font-bold text-green-800">{passedResults.length}</div>
          <div className="text-sm text-green-700">Passed Queries</div>
        </div>
      </div>

      {/* Failed Queries */}
      <div className="space-y-3">
        {failedResults.map((result) => (
          <div key={result.index} className="border border-red-300 rounded-lg overflow-hidden bg-white">
            {/* Header */}
            <div className="bg-red-50 p-4 border-b border-red-200">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs bg-red-200 text-red-800 px-2 py-1 rounded font-semibold">
                      FAILED
                    </span>
                    <span className="text-sm font-semibold text-gray-700">
                      Benchmark #{result.index + 1}
                    </span>
                  </div>
                  <p className="text-sm text-gray-800 font-medium">{result.question}</p>
                </div>

                {/* Action Buttons */}
                <div className="flex gap-2">
                  {editingIndex === result.index ? (
                    <>
                      <button
                        onClick={() => handleSaveEdit(result.index)}
                        className="px-3 py-1 bg-green-500 text-white text-sm rounded hover:bg-green-600"
                      >
                        Save
                      </button>
                      <button
                        onClick={handleCancelEdit}
                        className="px-3 py-1 bg-gray-500 text-white text-sm rounded hover:bg-gray-600"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => handleStartEdit(result.index, result.sql)}
                      className="px-3 py-1 bg-blue-500 text-white text-sm rounded hover:bg-blue-600"
                    >
                      Edit SQL
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Error Message */}
            <div className="p-4 bg-red-50 border-b border-red-200">
              <button
                onClick={() => toggleErrorExpansion(result.index)}
                className="w-full text-left flex justify-between items-center"
              >
                <span className="text-sm font-semibold text-red-800">Error:</span>
                <svg
                  className={`w-4 h-4 text-red-600 transform transition-transform ${
                    expandedErrors.has(result.index) ? 'rotate-180' : ''
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedErrors.has(result.index) && (
                <pre className="mt-2 text-xs text-red-700 whitespace-pre-wrap bg-white p-3 rounded border border-red-200">
                  {result.error}
                </pre>
              )}
            </div>

            {/* SQL Editor */}
            <div className="p-4 bg-gray-50">
              {editingIndex === result.index ? (
                <textarea
                  value={editedSql}
                  onChange={(e) => setEditedSql(e.target.value)}
                  className="w-full p-3 border border-gray-300 rounded font-mono text-sm h-48"
                  placeholder="Enter corrected SQL..."
                />
              ) : (
                <pre className="text-xs font-mono bg-gray-100 p-3 rounded border border-gray-200 overflow-x-auto">
                  <code className="text-gray-800">{result.sql}</code>
                </pre>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3 pt-4 border-t border-gray-200">
        <button
          onClick={onRevalidate}
          className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors font-semibold"
        >
          Re-validate All Queries
        </button>
        <button
          onClick={onRemoveFailedQueries}
          className="px-6 py-3 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
        >
          Remove {failedResults.length} Failed {failedResults.length === 1 ? 'Query' : 'Queries'}
        </button>
      </div>
    </div>
  );
}
