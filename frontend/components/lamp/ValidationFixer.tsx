/**
 * ValidationFixer component for interactive table replacement.
 */

'use client';

import { useState } from 'react';
import { ValidationFix } from '@/lib/api-client';

interface ValidationIssue {
  type: string;
  table: string;
  message: string;
  suggestions?: string[];
}

interface ValidationFixerProps {
  issues: ValidationIssue[];
  onApplyFixes: (
    fixes: ValidationFix[],
    bulkCatalog?: string,
    bulkSchema?: string,
    excludeTables?: string[]
  ) => void;
}

export function ValidationFixer({ issues, onApplyFixes }: ValidationFixerProps) {
  const [fixes, setFixes] = useState<ValidationFix[]>([]);
  const [bulkCatalog, setBulkCatalog] = useState('');
  const [bulkSchema, setBulkSchema] = useState('');
  const [excludedTables, setExcludedTables] = useState<Set<string>>(new Set());

  const invalidTables = issues
    .filter((i) => i.type === 'table_not_found')
    .map((i) => i.table);

  const handleFixChange = (idx: number, field: string, value: string) => {
    const newFixes = [...fixes];
    const table = invalidTables[idx];
    const [oldCatalog, oldSchema, oldTable] = table.split('.');

    if (!newFixes[idx]) {
      newFixes[idx] = {
        old_catalog: oldCatalog,
        old_schema: oldSchema,
        old_table: oldTable,
        new_catalog: oldCatalog,
        new_schema: oldSchema,
        new_table: oldTable,
      };
    }

    newFixes[idx] = { ...newFixes[idx], [field]: value };
    setFixes(newFixes);
  };

  const handleToggleExclude = (table: string) => {
    const newExcluded = new Set(excludedTables);
    if (newExcluded.has(table)) {
      newExcluded.delete(table);
    } else {
      newExcluded.add(table);
    }
    setExcludedTables(newExcluded);
  };

  const handleApply = () => {
    // Get valid individual fixes
    const validFixes = fixes.filter(
      (f) => f && f.new_catalog && f.new_schema && f.new_table
    );

    onApplyFixes(
      validFixes,
      bulkCatalog || undefined,
      bulkSchema || undefined,
      Array.from(excludedTables)
    );
  };

  return (
    <div className="bg-red-50 p-6 rounded-lg border border-red-200">
      <h3 className="text-xl font-bold text-red-800 mb-4">
        ❌ {invalidTables.length} Invalid Table{invalidTables.length > 1 ? 's' : ''}
      </h3>
      <p className="text-sm text-red-700 mb-4">
        The following tables were not found in Unity Catalog. Please provide the correct
        catalog, schema, and table names.
      </p>

      {/* Bulk operations section */}
      <div className="bg-blue-50 p-4 rounded-lg border border-blue-300 mb-4">
        <h4 className="font-semibold text-blue-900 mb-3">🚀 Apply to All Tables</h4>
        <p className="text-sm text-blue-800 mb-3">
          Enter catalog and schema to apply to ALL tables at once:
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-blue-900 mb-1">
              Catalog (for all)
            </label>
            <input
              type="text"
              placeholder="e.g., my_catalog"
              value={bulkCatalog}
              onChange={(e) => setBulkCatalog(e.target.value)}
              className="w-full border border-blue-300 p-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-blue-900 mb-1">
              Schema (for all)
            </label>
            <input
              type="text"
              placeholder="e.g., my_schema"
              value={bulkSchema}
              onChange={(e) => setBulkSchema(e.target.value)}
              className="w-full border border-blue-300 p-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
        <p className="text-xs text-blue-700 mt-2">
          This will update the catalog and schema for all tables below. Individual fixes will
          override this setting.
        </p>
      </div>

      <div className="space-y-4">
        {invalidTables.map((table, idx) => {
          const [catalog, schema, tableName] = table.split('.');
          const issue = issues.find((i) => i.table === table);

          const isExcluded = excludedTables.has(table);

          return (
            <div
              key={idx}
              className={`bg-white p-4 rounded-lg border ${
                isExcluded ? 'border-gray-300 opacity-60' : 'border-red-200'
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <p className="font-semibold flex-1">
                  Invalid: <code className="bg-gray-100 px-2 py-1 rounded">{table}</code>
                </p>
                <label className="flex items-center cursor-pointer ml-4">
                  <input
                    type="checkbox"
                    checked={isExcluded}
                    onChange={() => handleToggleExclude(table)}
                    className="mr-2 w-4 h-4"
                  />
                  <span className="text-sm text-gray-700">Exclude this table</span>
                </label>
              </div>

              {isExcluded && (
                <div className="bg-yellow-50 border border-yellow-200 p-2 rounded mb-3">
                  <p className="text-xs text-yellow-800">
                    ⚠️ This table will be removed from the configuration
                  </p>
                </div>
              )}

              {!isExcluded && issue?.suggestions && issue.suggestions.length > 0 && (
                <div className="mb-3 text-sm">
                  <p className="text-gray-600">Suggestions:</p>
                  <ul className="list-disc list-inside text-gray-700">
                    {issue.suggestions.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}

              {!isExcluded && (
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">New Catalog</label>
                    <input
                      type="text"
                      placeholder={catalog}
                      className="w-full border border-gray-300 p-2 rounded"
                      onChange={(e) => handleFixChange(idx, 'new_catalog', e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">New Schema</label>
                    <input
                      type="text"
                      placeholder={schema}
                      className="w-full border border-gray-300 p-2 rounded"
                      onChange={(e) => handleFixChange(idx, 'new_schema', e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">New Table</label>
                    <input
                      type="text"
                      placeholder={tableName}
                      className="w-full border border-gray-300 p-2 rounded"
                      onChange={(e) => handleFixChange(idx, 'new_table', e.target.value)}
                    />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <button
        onClick={handleApply}
        disabled={
          !bulkCatalog &&
          !bulkSchema &&
          fixes.filter((f) => f && f.new_catalog).length === 0 &&
          excludedTables.size === 0
        }
        className="mt-4 px-6 py-3 bg-blue-500 text-white rounded-lg disabled:bg-gray-300 disabled:cursor-not-allowed hover:bg-blue-600 transition-colors"
      >
        {bulkCatalog && bulkSchema
          ? `Apply Bulk Updates & Re-validate`
          : excludedTables.size > 0
          ? `Apply Changes (${excludedTables.size} excluded) & Re-validate`
          : 'Apply Fixes & Re-validate'}
      </button>
    </div>
  );
}
