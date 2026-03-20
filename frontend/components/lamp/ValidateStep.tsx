/**
 * Validate step component for configuration validation.
 */

'use client';

import { useState, useEffect } from 'react';
import { useJobPolling } from '@/lib/hooks/useJobPolling';
import { apiClient, ValidationFix } from '@/lib/api-client';
import { ValidationFixer } from './ValidationFixer';

interface ValidateStepProps {
  sessionId: string;
  configPath: string;
  onComplete: (result: any) => void;
  onPrevious: () => void;
  existingResult?: any;
}

export function ValidateStep({ sessionId, configPath, onComplete, onPrevious, existingResult }: ValidateStepProps) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [showFixer, setShowFixer] = useState(existingResult?.has_errors || false);
  const [validationResult, setValidationResult] = useState<any>(existingResult || null);
  const { job, isPolling, error } = useJobPolling(jobId);
  const [showingExistingResult, setShowingExistingResult] = useState(!!existingResult);

  const handleValidate = async () => {
    try {
      const response = await apiClient.validate(sessionId, configPath);
      setJobId(response.job_id);
    } catch (err) {
      console.error('Validation failed:', err);
    }
  };

  const handleApplyFixes = async (
    fixes: ValidationFix[],
    bulkCatalog?: string,
    bulkSchema?: string,
    excludeTables?: string[]
  ) => {
    try {
      setShowFixer(false);
      setValidationResult(null);
      setShowingExistingResult(false); // Reset to allow new validation result to be processed
      const response = await apiClient.fixValidation(
        sessionId,
        configPath,
        fixes,
        bulkCatalog,
        bulkSchema,
        excludeTables
      );
      setJobId(response.job_id);
    } catch (err) {
      console.error('Fix validation failed:', err);
    }
  };

  useEffect(() => {
    if (job?.status === 'completed' && job.result && !showingExistingResult) {
      setValidationResult(job.result);
      if (job.result.has_errors) {
        setShowFixer(true);
      } else {
        onComplete(job.result);
      }
    }
  }, [job, onComplete, showingExistingResult]);

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Step 3: Validate Configuration</h2>
      <p className="text-gray-600">
        Verify that all tables and columns exist in Unity Catalog.
      </p>

      {/* Show existing result if navigating back */}
      {showingExistingResult && validationResult && !validationResult.has_errors && (
        <div className="space-y-4">
          <div className="bg-green-50 p-6 rounded-lg border border-green-200">
            <h3 className="text-xl font-bold text-green-800 mb-2">✅ Validation Passed!</h3>
            <p className="text-green-700">
              {validationResult.tables_valid?.length || 0} table{(validationResult.tables_valid?.length || 0) !== 1 ? 's' : ''}{' '}
              validated successfully.
            </p>
            {validationResult.tables_valid && validationResult.tables_valid.length > 0 && (
              <div className="mt-3 bg-white p-3 rounded border border-green-300">
                <p className="text-sm font-semibold text-gray-700 mb-2">Validated Tables:</p>
                <ul className="text-sm text-gray-600 space-y-1 max-h-32 overflow-y-auto">
                  {validationResult.tables_valid.map((table: string, idx: number) => (
                    <li key={idx} className="font-mono">• {table}</li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-sm text-gray-600 mt-2">Ready to deploy to Databricks Genie.</p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={onPrevious}
              className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              ← Back to Generate
            </button>
            <button
              onClick={() => setShowingExistingResult(false)}
              className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              Validate Again
            </button>
            <button
              onClick={() => onComplete(validationResult)}
              className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            >
              Continue to Deploy →
            </button>
          </div>
        </div>
      )}

      {/* Show existing result with errors */}
      {showingExistingResult && validationResult && validationResult.has_errors && (
        <div className="space-y-4">
          <div className="bg-orange-50 p-6 rounded-lg border border-orange-200">
            <h3 className="text-xl font-bold text-orange-800 mb-2">⚠️ Previous Validation Had Errors</h3>
            <p className="text-orange-700">
              {validationResult.tables_invalid || 0} table{(validationResult.tables_invalid || 0) > 1 ? 's' : ''} had validation issues.
            </p>
            <p className="text-sm text-gray-600 mt-2">You can fix the issues below or validate again.</p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={onPrevious}
              className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              ← Back to Generate
            </button>
            <button
              onClick={() => setShowingExistingResult(false)}
              className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              Validate Again
            </button>
          </div>
        </div>
      )}

      {!showingExistingResult && !validationResult && !isPolling && (
        <div className="flex gap-3">
          <button
            onClick={onPrevious}
            className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
          >
            ← Previous
          </button>
          <button
            onClick={handleValidate}
            className="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            Validate Configuration
          </button>
        </div>
      )}

      {isPolling && (
        <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
          <p className="font-semibold">Validating configuration...</p>
          <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
            <div className="bg-blue-500 h-2 rounded-full animate-pulse" style={{ width: '60%' }} />
          </div>
          <p className="text-sm text-gray-600 mt-2">Checking Unity Catalog tables and columns</p>
        </div>
      )}

      {error && (
        <div className="bg-red-50 p-4 rounded-lg border border-red-200 text-red-700">
          <p className="font-semibold">Error</p>
          <p>{error}</p>
        </div>
      )}

      {job?.status === 'failed' && (
        <div className="bg-red-50 p-4 rounded-lg border border-red-200 text-red-700">
          <p className="font-semibold">Validation Failed</p>
          <p>{job.error}</p>
        </div>
      )}

      {showFixer && validationResult?.issues && (
        <ValidationFixer issues={validationResult.issues} onApplyFixes={handleApplyFixes} />
      )}

      {validationResult && !validationResult.has_errors && !showingExistingResult && (
        <div className="space-y-4">
          <div className="bg-green-50 p-6 rounded-lg border border-green-200">
            <h3 className="text-xl font-bold text-green-800 mb-2">✅ Validation Passed!</h3>
            <p className="text-green-700">
              {validationResult.tables_valid?.length || 0} table{(validationResult.tables_valid?.length || 0) !== 1 ? 's' : ''}{' '}
              validated successfully.
            </p>
            {validationResult.tables_valid && validationResult.tables_valid.length > 0 && (
              <div className="mt-3 bg-white p-3 rounded border border-green-300">
                <p className="text-sm font-semibold text-gray-700 mb-2">Validated Tables:</p>
                <ul className="text-sm text-gray-600 space-y-1 max-h-32 overflow-y-auto">
                  {validationResult.tables_valid.map((table: string, idx: number) => (
                    <li key={idx} className="font-mono">• {table}</li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-sm text-gray-600 mt-2">Ready to deploy to Databricks Genie.</p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={onPrevious}
              className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              ← Back to Generate
            </button>
            <button
              onClick={() => onComplete(validationResult)}
              className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            >
              Continue to Deploy →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
