/**
 * Step 3: Review fixes and apply approved ones
 */

'use client';

import { useState, useEffect } from 'react';

interface PlanStepProps {
  state: any;
  onUpdate: (updates: any) => void;
  onNext: () => void;
  onBack: () => void;
  sessionId: string | null;
}

export function PlanStep({ state, onUpdate, onNext, onBack, sessionId }: PlanStepProps) {
  const [plan, setPlan] = useState<any>(state.plan || null);
  const [iteration, setIteration] = useState<any>(state.iteration || null);
  // Track individual fix selection: Map<category, Set<fixIndex>>
  const [selectedFixes, setSelectedFixes] = useState<Map<string, Set<number>>>(new Map());
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);

  useEffect(() => {
    // Auto-select all fixes by default
    if (plan && plan.grouped_fixes) {
      const selected = new Map<string, Set<number>>();
      Object.entries(plan.grouped_fixes).forEach(([category, fixes]: [string, any]) => {
        const indices = new Set<number>();
        fixes.forEach((_: any, idx: number) => indices.add(idx));
        selected.set(category, indices);
      });
      setSelectedFixes(selected);
      // Expand all categories by default
      setExpandedCategories(new Set(Object.keys(plan.grouped_fixes)));
    }
  }, [plan]);

  const toggleFix = (category: string, index: number) => {
    const newSelected = new Map(selectedFixes);
    const categorySet = new Set(newSelected.get(category) || []);
    if (categorySet.has(index)) {
      categorySet.delete(index);
    } else {
      categorySet.add(index);
    }
    newSelected.set(category, categorySet);
    setSelectedFixes(newSelected);
  };

  const toggleCategory = (category: string) => {
    const newSelected = new Map(selectedFixes);
    const categoryFixes = plan.grouped_fixes[category] || [];
    const currentSelected = newSelected.get(category) || new Set();

    // If all selected, deselect all; otherwise select all
    if (currentSelected.size === categoryFixes.length) {
      newSelected.set(category, new Set());
    } else {
      const allIndices = new Set<number>();
      categoryFixes.forEach((_: any, idx: number) => allIndices.add(idx));
      newSelected.set(category, allIndices);
    }
    setSelectedFixes(newSelected);
  };

  const toggleExpand = (category: string) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(category)) {
      newExpanded.delete(category);
    } else {
      newExpanded.add(category);
    }
    setExpandedCategories(newExpanded);
  };

  const applyFixes = async () => {
    if (!iteration || !plan) return;

    setApplying(true);

    try {
      // Build approved fixes object from selected individual fixes
      const approvedFixes: any = {};
      selectedFixes.forEach((indices, category) => {
        if (indices.size > 0 && plan.grouped_fixes[category]) {
          approvedFixes[category] = plan.grouped_fixes[category].filter(
            (_: any, idx: number) => indices.has(idx)
          );
        }
      });

      // Call approve endpoint
      const response = await fetch(`/api/enhancer/iterations/${iteration.iteration_id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          approved_fixes: approvedFixes,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to approve fixes');
      }

      const data = await response.json();

      // Poll apply job
      pollApplyJob(data.apply_job_id);
    } catch (error) {
      console.error('Failed to apply fixes:', error);
      setApplying(false);
      alert('Failed to apply fixes: ' + error);
    }
  };

  const pollApplyJob = async (jobId: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/jobs/${jobId}`);
        const job = await response.json();

        if (job.status === 'completed') {
          clearInterval(interval);
          setApplied(true);
          setApplying(false);
          onUpdate({ fixesApplied: true });
        } else if (job.status === 'failed') {
          clearInterval(interval);
          setApplying(false);
          alert('Apply failed: ' + (job.error || 'Unknown error'));
        }
      } catch (err) {
        console.error('Error polling apply job:', err);
      }
    }, 2000);
  };

  const getCategoryName = (category: string) => {
    const names: Record<string, string> = {
      'instruction_fix': '📝 Instruction Fixes',
      'join_specs_add': '🔗 Join Spec Additions',
      'join_specs_delete': '🗑️ Join Spec Deletions',
      'sql_snippets_add': '✨ SQL Snippet Additions',
      'sql_snippets_delete': '🗑️ SQL Snippet Deletions',
      'metadata_add': '📊 Metadata Additions',
      'metadata_delete': '🗑️ Metadata Deletions',
      'sample_queries_add': '💡 Sample Query Additions',
      'sample_queries_delete': '🗑️ Sample Query Deletions',
    };
    return names[category] || category;
  };

  if (!plan || !iteration) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold">🔧 Plan & Apply</h2>
        <p className="text-gray-600">No plan available. Please go back and run scoring first.</p>
        <button onClick={onBack} className="px-6 py-2 border rounded hover:bg-gray-50">
          ← Back
        </button>
      </div>
    );
  }

  const totalFixes = plan.total_fixes || 0;
  const selectedCount = Array.from(selectedFixes.values()).reduce(
    (sum, indices) => sum + indices.size, 0
  );

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">🔧 Review & Apply Fixes</h2>

      {!applied && !applying && (
        <div>
          <div className="bg-blue-50 border border-blue-200 rounded p-4 mb-6">
            <h3 className="font-semibold mb-2">Iteration {iteration.iteration_number}</h3>
            <p className="text-sm text-gray-700">
              Current Score: {((iteration.score_before || 0) * 100).toFixed(1)}%
            </p>
            <p className="text-sm text-gray-700">
              Target Score: {((state.target_score || 0.90) * 100).toFixed(0)}%
            </p>
          </div>

          <div className="mb-4">
            <h3 className="text-lg font-semibold mb-2">
              Proposed Fixes ({totalFixes} total)
            </h3>
            <p className="text-sm text-gray-600 mb-4">
              Select categories to apply. Uncheck categories you want to skip.
            </p>
          </div>

          <div className="space-y-4 mb-6">
            {Object.entries(plan.grouped_fixes || {}).map(([category, fixes]: [string, any]) => {
              const categorySelected = selectedFixes.get(category) || new Set();
              const allSelected = categorySelected.size === fixes.length;
              const someSelected = categorySelected.size > 0 && !allSelected;
              const isExpanded = expandedCategories.has(category);

              return (
                <div key={category} className="border rounded-lg bg-white overflow-hidden">
                  {/* Category Header */}
                  <div className="flex items-center justify-between p-4 bg-gray-50 border-b">
                    <div className="flex items-center space-x-3">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        ref={(el) => { if (el) el.indeterminate = someSelected; }}
                        onChange={() => toggleCategory(category)}
                        className="w-5 h-5 cursor-pointer"
                      />
                      <div>
                        <h4 className="font-semibold">{getCategoryName(category)}</h4>
                        <p className="text-sm text-gray-600">
                          {categorySelected.size}/{fixes.length} selected
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => toggleExpand(category)}
                      className="text-gray-500 hover:text-gray-700 px-3 py-1"
                    >
                      {isExpanded ? '▼ Collapse' : '▶ Expand'}
                    </button>
                  </div>

                  {/* Individual Fixes */}
                  {isExpanded && (
                    <div className="divide-y">
                      {fixes.map((fix: any, idx: number) => {
                        const isSelected = categorySelected.has(idx);
                        return (
                          <div key={idx} className={`p-4 ${isSelected ? 'bg-blue-50' : 'bg-white'}`}>
                            <div className="flex items-start space-x-3">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => toggleFix(category, idx)}
                                className="w-4 h-4 mt-1 cursor-pointer"
                              />
                              <div className="flex-1 min-w-0">
                                <div className="font-medium text-sm">
                                  Fix #{idx + 1}: {fix.type || category}
                                </div>
                                {fix.reasoning && (
                                  <p className="text-sm text-gray-600 mt-1">
                                    {fix.reasoning}
                                  </p>
                                )}
                                {fix.content && (
                                  <details className="mt-2">
                                    <summary className="text-xs text-blue-600 cursor-pointer hover:underline">
                                      View content
                                    </summary>
                                    <pre className="text-xs mt-2 bg-gray-100 p-2 rounded overflow-x-auto whitespace-pre-wrap max-h-48">
                                      {typeof fix.content === 'string'
                                        ? fix.content
                                        : JSON.stringify(fix.content, null, 2)}
                                    </pre>
                                  </details>
                                )}
                                {fix.benchmark_ids && fix.benchmark_ids.length > 0 && (
                                  <p className="text-xs text-gray-500 mt-1">
                                    Benchmarks: {fix.benchmark_ids.join(', ')}
                                  </p>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-between p-4 bg-gray-50 rounded">
            <div>
              <p className="font-semibold">
                {selectedCount} of {totalFixes} fixes selected
              </p>
              <p className="text-sm text-gray-600">
                across {Object.keys(plan.grouped_fixes || {}).length} categories
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={onBack}
                className="px-6 py-2 border rounded hover:bg-gray-100"
              >
                ← Back
              </button>
              <button
                onClick={applyFixes}
                disabled={selectedCount === 0}
                className="bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700 disabled:bg-gray-400"
              >
                Apply Selected Fixes ({selectedCount})
              </button>
            </div>
          </div>
        </div>
      )}

      {applying && (
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p>Applying fixes to Genie Space...</p>
          <p className="text-sm text-gray-600 mt-2">This may take a minute</p>
        </div>
      )}

      {applied && (
        <div>
          <div className="bg-green-100 p-6 rounded mb-4">
            <h3 className="text-xl font-bold mb-2">✓ Fixes Applied Successfully</h3>
            <p className="text-gray-700">
              {selectedCount} fix{selectedCount !== 1 ? 'es' : ''} have been applied to your Genie Space.
            </p>
          </div>

          <button
            onClick={onNext}
            className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
          >
            Continue to Validation →
          </button>
        </div>
      )}
    </div>
  );
}
