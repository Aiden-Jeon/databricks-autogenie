/**
 * Reasoning Display Component - Shows GPT reasoning for config generation
 */

'use client';

import { useState } from 'react';

interface ReasoningDisplayProps {
  reasoning: Record<string, string>;
  defaultExpanded?: boolean;
}

export function ReasoningDisplay({
  reasoning,
  defaultExpanded = false,
}: ReasoningDisplayProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  if (!reasoning || Object.keys(reasoning).length === 0) {
    return null;
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden shadow-sm">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 bg-gradient-to-r from-purple-50 to-blue-50
                   hover:from-purple-100 hover:to-blue-100 transition-colors
                   flex items-center justify-between"
      >
        <div className="flex items-center gap-2">
          <span className="text-xl">🧠</span>
          <span className="font-semibold text-gray-800">GPT Reasoning</span>
          <span className="text-xs text-gray-500">
            ({Object.keys(reasoning).length} sections)
          </span>
        </div>
        <span className="text-gray-500 text-sm">
          {isExpanded ? '▲ Collapse' : '▼ Expand'}
        </span>
      </button>

      {isExpanded && (
        <div className="p-4 space-y-4 bg-white">
          {Object.entries(reasoning).map(([key, value]) => (
            <div
              key={key}
              className="border-l-4 border-blue-400 pl-4 py-2"
            >
              <h4 className="font-semibold text-sm text-gray-700 uppercase mb-2 tracking-wide">
                {key.replace(/_/g, ' ')}
              </h4>
              <div className="prose prose-sm max-w-none text-gray-600">
                {/* Render as plain text with line breaks */}
                <p className="whitespace-pre-wrap">{value}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
