/**
 * Deploy step component for Genie space deployment.
 */

'use client';

import { useState, useEffect } from 'react';
import { useJobPolling } from '@/lib/hooks/useJobPolling';
import { apiClient } from '@/lib/api-client';

interface DeployStepProps {
  sessionId: string;
  configPath: string;
  onComplete: (result: any) => void;
  onPrevious: () => void;
  existingResult?: any;
}

export function DeployStep({ sessionId, configPath, onComplete, onPrevious, existingResult }: DeployStepProps) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [parentPath, setParentPath] = useState('');
  const [spaceName, setSpaceName] = useState('');
  const [originalSpaceName, setOriginalSpaceName] = useState('');
  const [loadingMetadata, setLoadingMetadata] = useState(true);
  const { job, isPolling, error } = useJobPolling(jobId);
  const [showingExistingResult, setShowingExistingResult] = useState(!!existingResult);

  // Load space name from config
  useEffect(() => {
    const loadMetadata = async () => {
      try {
        setLoadingMetadata(true);
        const metadata = await apiClient.getConfigMetadata(configPath);
        setOriginalSpaceName(metadata.space_name);
        setSpaceName(metadata.space_name);
      } catch (err) {
        console.error('Failed to load config metadata:', err);
      } finally {
        setLoadingMetadata(false);
      }
    };

    if (configPath && !showingExistingResult) {
      loadMetadata();
    }
  }, [configPath, showingExistingResult]);

  const handleDeploy = async () => {
    try {
      // Sanitize space name (remove forward slashes)
      const sanitizedSpaceName = spaceName.replace(/\//g, ' and ');

      const response = await apiClient.deploy(
        sessionId,
        configPath,
        { parentPath: parentPath || undefined, spaceName: sanitizedSpaceName || undefined }
      );
      setJobId(response.job_id);
    } catch (err) {
      console.error('Deploy failed:', err);
    }
  };

  useEffect(() => {
    if (job?.status === 'completed' && !showingExistingResult) {
      onComplete(job.result);
    }
  }, [job, onComplete, showingExistingResult]);

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Step 4: Deploy Genie Space</h2>
      <p className="text-gray-600">
        Deploy your validated configuration to Databricks Genie.
      </p>

      {/* Show existing result if navigating back */}
      {showingExistingResult && existingResult && (
        <div className="space-y-4">
          <div className="bg-green-50 p-6 rounded-lg border border-green-200">
            <h3 className="text-xl font-bold text-green-800 mb-2">✅ Deployment Complete!</h3>
            <p className="text-gray-700 mb-3">
              <span className="font-semibold">Space ID:</span>{' '}
              <code className="bg-gray-100 px-2 py-1 rounded">{existingResult.space_id}</code>
            </p>
            <a
              href={existingResult.space_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              Open Genie Space →
            </a>
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
              Deploy Again
            </button>
            <button
              onClick={() => onComplete(existingResult)}
              className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            >
              Continue to Complete →
            </button>
          </div>
        </div>
      )}

      {!showingExistingResult && (
        <>
          <div className="space-y-2">
            <label className="block text-sm font-medium">
              Genie Space Name:
            </label>
            {loadingMetadata ? (
              <div className="w-full p-2 border border-gray-200 rounded-lg bg-gray-50">
                <p className="text-gray-500">Loading...</p>
              </div>
            ) : (
              <>
                <input
                  type="text"
                  value={spaceName}
                  onChange={(e) => setSpaceName(e.target.value)}
                  disabled={isPolling}
                  className="w-full p-2 border border-gray-300 rounded-lg"
                  placeholder="Enter space name"
                />
                {spaceName !== originalSpaceName && (
                  <p className="text-xs text-blue-600">
                    ✏️ Modified from original: &quot;{originalSpaceName}&quot;
                  </p>
                )}
                {spaceName.includes('/') && (
                  <p className="text-xs text-amber-600">
                    ⚠️ Forward slashes (/) will be replaced with &quot; and &quot; to prevent deployment errors
                  </p>
                )}
                <p className="text-xs text-gray-500">
                  This will be the display name of your Genie space
                </p>
              </>
            )}
          </div>

          <div className="space-y-2">
        <label className="block text-sm font-medium">
          Parent Path (Optional):
        </label>
        <input
          type="text"
          placeholder="/Workspace/Shared/Genie Spaces"
          value={parentPath}
          onChange={(e) => setParentPath(e.target.value)}
          disabled={isPolling}
          className="w-full p-2 border border-gray-300 rounded-lg"
        />
        <p className="text-xs text-gray-500">
          Leave empty to deploy to your user workspace
        </p>
      </div>

      <div className="flex gap-3">
        <button
          onClick={onPrevious}
          disabled={isPolling}
          className="px-6 py-3 bg-gray-500 text-white rounded-lg disabled:bg-gray-300 disabled:cursor-not-allowed hover:bg-gray-600 transition-colors"
        >
          ← Previous
        </button>
        <button
          onClick={handleDeploy}
          disabled={isPolling}
          className="px-6 py-3 bg-blue-500 text-white rounded-lg disabled:bg-gray-300 disabled:cursor-not-allowed hover:bg-blue-600 transition-colors"
        >
          {isPolling ? 'Deploying...' : 'Deploy Genie Space'}
        </button>
      </div>

      {isPolling && (
        <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
          <p className="font-semibold">Deploying to Databricks Genie...</p>
          <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
            <div className="bg-blue-500 h-2 rounded-full animate-pulse" style={{ width: '85%' }} />
          </div>
          <p className="text-sm text-gray-600 mt-2">Creating space via API</p>
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
          <p className="font-semibold">Deployment Failed</p>
          <p>{job.error}</p>
        </div>
      )}
        </>
      )}
    </div>
  );
}
