/**
 * Parse step component for file upload and parsing.
 */

'use client';

import { useState } from 'react';
import { useJobPolling } from '@/lib/hooks/useJobPolling';
import { apiClient } from '@/lib/api-client';
import { FileProgressList } from './FileProgressList';
import { ReasoningDisplay } from './ReasoningDisplay';
import { ParsedMarkdownPreview } from './ParsedMarkdownPreview';

interface ParseStepProps {
  sessionId: string;
  onComplete: (result: any) => void;
  existingResult?: any;
}

export function ParseStep({ sessionId, onComplete, existingResult }: ParseStepProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [useLLM, setUseLLM] = useState(true);
  const { job, isPolling, error: pollingError } = useJobPolling(jobId);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [showingExistingResult, setShowingExistingResult] = useState(!!existingResult);

  const handleUpload = async () => {
    if (files.length === 0) return;

    try {
      setUploadError(null);
      const formData = new FormData();
      formData.append('session_id', sessionId);
      formData.append('use_llm', String(useLLM));
      files.forEach((f) => formData.append('files', f));

      const response = await apiClient.parse(sessionId, formData);
      setJobId(response.job_id);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Step 1: Upload & Extract Requirements</h2>
      <p className="text-gray-600">
        Upload and extract requirements from PDF or Markdown files.
      </p>

      {/* Show existing result if navigating back */}
      {showingExistingResult && existingResult && (
        <div className="mt-4 space-y-4">
          <div className="bg-green-50 p-4 rounded-lg border border-green-200">
            <p className="font-semibold text-green-800">✓ Extraction Complete!</p>
            <p className="text-sm text-gray-600 mt-1">
              Extracted {existingResult?.tables_found || 0} tables from {existingResult?.files_parsed || 0} files
            </p>
          </div>

          {existingResult?.enrichment_reasoning && (
            <ReasoningDisplay
              reasoning={existingResult.enrichment_reasoning}
              defaultExpanded={false}
            />
          )}

          <ParsedMarkdownPreview
            sessionId={sessionId}
            fileStats={existingResult?.parsed_file_stats}
            defaultExpanded={false}
          />

          <div className="flex gap-3">
            <button
              onClick={() => setShowingExistingResult(false)}
              className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              Upload New Files
            </button>
            <button
              onClick={() => onComplete(existingResult)}
              className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            >
              Continue to Generate Step →
            </button>
          </div>
        </div>
      )}

      {!showingExistingResult && (
        <>
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors">
        <input
          type="file"
          multiple
          accept=".pdf,.md"
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
          className="w-full"
          disabled={isPolling}
        />
        <p className="text-sm text-gray-600 mt-2">
          {files.length > 0
            ? `${files.length} file${files.length > 1 ? 's' : ''} selected`
            : 'Select PDF or Markdown files'}
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="use-llm"
          checked={useLLM}
          onChange={(e) => setUseLLM(e.target.checked)}
          disabled={isPolling}
        />
        <label htmlFor="use-llm" className="text-sm">
          Use LLM enrichment (recommended for better extraction)
        </label>
      </div>

      <button
        onClick={handleUpload}
        disabled={files.length === 0 || isPolling}
        className="px-6 py-3 bg-blue-500 text-white rounded-lg disabled:bg-gray-300 disabled:cursor-not-allowed hover:bg-blue-600 transition-colors"
      >
        {isPolling ? 'Extracting...' : 'Upload & Extract'}
      </button>

      {isPolling && job?.progress && (
        <div className="space-y-4">
          <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
            <div className="flex justify-between mb-3">
              <p className="font-semibold">
                Extracting from {job.progress.total_files} files...
              </p>
              <p className="text-sm text-gray-600">
                {job.progress.completed_files}/{job.progress.total_files} completed
              </p>
            </div>

            {job.progress.current_file && (
              <p className="text-sm text-gray-600 mb-3">
                Current: <span className="font-medium">{job.progress.current_file}</span>
              </p>
            )}

            <FileProgressList
              files={job.progress.files}
              currentFile={job.progress.current_file}
            />
          </div>

          {/* Show enrichment progress when all files are parsed */}
          {job.progress.completed_files === job.progress.total_files && (
            <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
              <div className="flex items-center gap-3 mb-3">
                <div className="animate-spin text-2xl">🧠</div>
                <p className="font-semibold text-purple-800">
                  Enriching with GPT-5-2...
                </p>
              </div>
              <p className="text-sm text-gray-600 mb-3">
                Combining and enhancing extracted data from all files
              </p>

              {/* Show real-time enrichment progress if available */}
              {job.progress.enrichment_progress && job.progress.enrichment_progress.length > 0 ? (
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {job.progress.enrichment_progress.map((progress, idx) => (
                    <div
                      key={idx}
                      className={`flex items-start gap-2 text-xs p-2 rounded ${
                        progress.stage.includes('complete')
                          ? 'bg-green-100 text-green-700'
                          : progress.stage.includes('start')
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      <div className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${
                        progress.stage.includes('complete')
                          ? 'bg-green-500'
                          : 'bg-blue-500 animate-pulse'
                      }`}></div>
                      <span className="flex-1">{progress.details}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-1 text-xs text-gray-500">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></div>
                    <span>Enriching table descriptions</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></div>
                    <span>Enhancing SQL query descriptions</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></div>
                    <span>Generating business scenarios</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></div>
                    <span>Creating document summary</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Fallback for jobs without progress */}
      {isPolling && !job?.progress && (
        <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
          <p className="font-semibold">Extracting from {files.length} files...</p>
          <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
            <div className="bg-blue-500 h-2 rounded-full animate-pulse" style={{ width: '50%' }} />
          </div>
          <p className="text-sm text-gray-600 mt-2">This may take a few minutes</p>
        </div>
      )}

      {(uploadError || pollingError) && (
        <div className="bg-red-50 p-4 rounded-lg border border-red-200 text-red-700">
          <p className="font-semibold">Error</p>
          <p>{uploadError || pollingError}</p>
        </div>
      )}

      {job?.status === 'failed' && (
        <div className="bg-red-50 p-4 rounded-lg border border-red-200 text-red-700">
          <p className="font-semibold">Extraction Failed</p>
          <p>{job.error}</p>
        </div>
      )}

      {/* Show results when job completes */}
      {job?.status === 'completed' && (
        <div className="mt-4 space-y-4">
          <div className="bg-green-50 p-4 rounded-lg border border-green-200">
            <p className="font-semibold text-green-800">✓ Extraction Complete!</p>
            <p className="text-sm text-gray-600 mt-1">
              Extracted {job.result?.tables_found || 0} tables from {job.result?.files_parsed || 0} files
            </p>
          </div>

          {/* Show enrichment reasoning if available */}
          {job.result?.enrichment_reasoning && (
            <ReasoningDisplay
              reasoning={job.result.enrichment_reasoning}
              defaultExpanded={true}
            />
          )}

          {/* Show parsed markdown preview */}
          <ParsedMarkdownPreview
            sessionId={sessionId}
            fileStats={job.result?.parsed_file_stats}
            defaultExpanded={false}
          />

          <button
            onClick={() => onComplete(job.result)}
            className="w-full px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            Continue to Generate Step →
          </button>
        </div>
      )}
        </>
      )}
    </div>
  );
}
