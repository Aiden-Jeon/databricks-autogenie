/**
 * Parsed Markdown Preview Component - Shows parsed requirements document
 */

'use client';

import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { apiClient, FileContentResponse } from '@/lib/api-client';

interface ParsedMarkdownPreviewProps {
  sessionId: string;
  fileStats?: {
    size_bytes: number;
    line_count: number;
    char_count: number;
  };
  defaultExpanded?: boolean;
}

type ViewMode = 'preview' | 'full' | 'rendered';

export function ParsedMarkdownPreview({
  sessionId,
  fileStats,
  defaultExpanded = false,
}: ParsedMarkdownPreviewProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [viewMode, setViewMode] = useState<ViewMode>('preview');
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileData, setFileData] = useState<FileContentResponse | null>(null);

  // Fetch content when expanded
  useEffect(() => {
    if (isExpanded && !content && !loading && !error) {
      fetchContent();
    }
  }, [isExpanded]);

  const fetchContent = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getFileContent(sessionId, 'parsed_requirements.md');
      setContent(data.content);
      setFileData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load file');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (!content) return;
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'parsed_requirements.md';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Format file size
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Get content to display based on view mode
  const getDisplayContent = () => {
    if (!content) return '';
    if (viewMode === 'preview') {
      const lines = content.split('\n');
      return lines.slice(0, 50).join('\n') + (lines.length > 50 ? '\n\n... (showing first 50 lines)' : '');
    }
    return content;
  };

  // Use provided fileStats if available, otherwise use fetched data
  const displayStats = fileStats || (fileData ? {
    size_bytes: fileData.size_bytes,
    line_count: fileData.line_count,
    char_count: fileData.char_count
  } : null);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden shadow-sm">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 bg-gradient-to-r from-green-50 to-blue-50
                   hover:from-green-100 hover:to-blue-100 transition-colors
                   flex items-center justify-between"
      >
        <div className="flex items-center gap-2">
          <span className="text-xl">📄</span>
          <span className="font-semibold text-gray-800">Parsed Requirements Document</span>
          {displayStats && (
            <span className="text-xs text-gray-500">
              ({displayStats.line_count.toLocaleString()} lines, {formatSize(displayStats.size_bytes)})
            </span>
          )}
        </div>
        <span className="text-gray-500 text-sm">
          {isExpanded ? '▲ Collapse' : '▼ Expand'}
        </span>
      </button>

      {isExpanded && (
        <div className="bg-white">
          {/* View mode controls */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-gray-50">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-600 font-medium">View:</span>
              <div className="flex gap-1">
                <button
                  onClick={() => setViewMode('preview')}
                  className={`px-3 py-1 text-xs rounded transition-colors ${
                    viewMode === 'preview'
                      ? 'bg-blue-500 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-100 border border-gray-300'
                  }`}
                >
                  Preview (50 lines)
                </button>
                <button
                  onClick={() => setViewMode('full')}
                  className={`px-3 py-1 text-xs rounded transition-colors ${
                    viewMode === 'full'
                      ? 'bg-blue-500 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-100 border border-gray-300'
                  }`}
                >
                  Full
                </button>
                <button
                  onClick={() => setViewMode('rendered')}
                  className={`px-3 py-1 text-xs rounded transition-colors ${
                    viewMode === 'rendered'
                      ? 'bg-blue-500 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-100 border border-gray-300'
                  }`}
                >
                  Rendered
                </button>
              </div>
            </div>
            <button
              onClick={handleDownload}
              disabled={!content}
              className="px-3 py-1 text-xs bg-green-500 text-white rounded hover:bg-green-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              ⬇ Download
            </button>
          </div>

          {/* Content area */}
          <div className="p-4">
            {loading && (
              <div className="text-center py-8 text-gray-500">
                <div className="animate-spin text-2xl mb-2">⏳</div>
                <p className="text-sm">Loading content...</p>
              </div>
            )}

            {error && (
              <div className="bg-red-50 p-4 rounded border border-red-200 text-red-700">
                <p className="font-semibold">Error</p>
                <p className="text-sm">{error}</p>
              </div>
            )}

            {content && !loading && (
              <div className="max-h-96 overflow-y-auto">
                {viewMode === 'rendered' ? (
                  <div className="prose prose-sm max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {getDisplayContent()}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono bg-gray-50 p-4 rounded border border-gray-200">
                    {getDisplayContent()}
                  </pre>
                )}
              </div>
            )}
          </div>

          {/* Stats footer */}
          {displayStats && content && (
            <div className="px-4 py-2 border-t border-gray-200 bg-gray-50 text-xs text-gray-600 flex gap-4">
              <span>{displayStats.line_count.toLocaleString()} lines</span>
              <span>{displayStats.char_count.toLocaleString()} characters</span>
              <span>{formatSize(displayStats.size_bytes)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
