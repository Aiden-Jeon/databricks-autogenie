/**
 * File Progress List Component - Displays per-file parsing progress
 */

import { FileProgress } from '@/lib/api-client';

interface FileProgressListProps {
  files: FileProgress[];
  currentFile?: string;
}

export function FileProgressList({ files, currentFile }: FileProgressListProps) {
  return (
    <div className="space-y-3">
      {files.map((file) => (
        <div
          key={file.name}
          className={`border rounded-lg p-4 transition-all ${
            file.name === currentFile
              ? 'border-blue-400 bg-blue-50'
              : file.status === 'completed'
              ? 'border-green-300 bg-green-50'
              : file.status === 'failed'
              ? 'border-red-300 bg-red-50'
              : 'border-gray-200 bg-white'
          }`}
        >
          {/* File header with status */}
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              {/* Status icon */}
              {file.status === 'completed' && (
                <span className="text-green-600 text-lg">✓</span>
              )}
              {file.status === 'processing' && (
                <span className="text-blue-600 text-lg animate-spin">⟳</span>
              )}
              {file.status === 'queued' && (
                <span className="text-gray-400 text-lg">⏳</span>
              )}
              {file.status === 'failed' && (
                <span className="text-red-600 text-lg">✗</span>
              )}

              <span className="font-medium text-sm">{file.name}</span>

              {/* Cache badge */}
              {file.cache_hit && (
                <span className="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded-full font-medium">
                  Cached
                </span>
              )}
            </div>

            {/* Duration */}
            {file.duration_ms && (
              <span className="text-sm text-gray-500">
                {(file.duration_ms / 1000).toFixed(1)}s
              </span>
            )}
          </div>

          {/* Progress bar for active processing */}
          {file.status === 'processing' && (
            <div className="mt-2">
              {file.pages_total ? (
                <>
                  <div className="flex justify-between text-xs text-gray-600 mb-1">
                    <span>
                      Page {file.pages_completed || 0}/{file.pages_total}
                    </span>
                    <span>
                      {Math.round(
                        ((file.pages_completed || 0) / file.pages_total) * 100
                      )}
                      %
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                    <div
                      className="h-2 rounded-full transition-all duration-300 bg-blue-500"
                      style={{
                        width: `${
                          ((file.pages_completed || 0) / file.pages_total) * 100
                        }%`,
                      }}
                    />
                  </div>
                </>
              ) : (
                <div className="text-xs text-gray-500">
                  Processing...
                </div>
              )}
            </div>
          )}

          {/* Show completed progress bar */}
          {file.status === 'completed' && file.pages_total && (
            <div className="mt-2">
              <div className="flex justify-between text-xs text-gray-600 mb-1">
                <span>Completed: {file.pages_total} pages</span>
                <span>100%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                <div className="h-2 rounded-full bg-green-500" style={{ width: '100%' }} />
              </div>
            </div>
          )}

          {/* Show extracted data summary */}
          {file.status === 'completed' && file.extracted && (
            <div className="mt-2 flex gap-3 text-xs">
              {file.extracted.questions_count > 0 && (
                <span className="text-blue-600">
                  📋 {file.extracted.questions_count} question{file.extracted.questions_count !== 1 ? 's' : ''}
                </span>
              )}
              {file.extracted.tables_count > 0 && (
                <span className="text-purple-600">
                  🗂️ {file.extracted.tables_count} table{file.extracted.tables_count !== 1 ? 's' : ''}
                </span>
              )}
              {file.extracted.queries_count > 0 && (
                <span className="text-green-600">
                  💾 {file.extracted.queries_count} quer{file.extracted.queries_count !== 1 ? 'ies' : 'y'}
                </span>
              )}
            </div>
          )}

          {/* Error message */}
          {file.error && (
            <p className="text-sm text-red-600 mt-2">
              Error: {file.error}
            </p>
          )}

          {/* Processing indicator */}
          {file.status === 'processing' && file.current_page != null && (
            <p className="text-xs text-gray-500 mt-1">
              Processing page {file.current_page}...
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
