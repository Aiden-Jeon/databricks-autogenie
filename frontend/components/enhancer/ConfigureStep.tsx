/**
 * Step 1: Configure workspace and space settings
 */

'use client';

import { useState, useEffect } from 'react';

interface ConfigureStepProps {
  state: any;
  onUpdate: (updates: any) => void;
  onNext: () => void;
  sessionId: string | null;
}

interface Warehouse {
  id: string;
  name: string;
  state: string;
}

interface GenieSpace {
  id: string;
  name: string;
  description?: string;
}

export function ConfigureStep({ state, onUpdate, onNext, sessionId }: ConfigureStepProps) {
  const [config, setConfig] = useState({
    warehouse_id: state.warehouse_id || '',
    space_id: state.space_id || '',
    llm_endpoint: state.llm_endpoint || 'databricks-gpt-5-2',
    target_score: state.target_score || 0.90,
    max_iterations: state.max_iterations || 3,
    use_clone: state.use_clone !== false,  // Default to true for safety
  });

  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [spaces, setSpaces] = useState<GenieSpace[]>([]);
  const [loadingWarehouses, setLoadingWarehouses] = useState(false);
  const [loadingSpaces, setLoadingSpaces] = useState(false);
  const [error, setError] = useState('');

  // Fetch warehouses and spaces on mount
  useEffect(() => {
    const fetchResources = async () => {
      setError('');

      // Fetch warehouses
      setLoadingWarehouses(true);
      try {
        const whResponse = await fetch('/api/enhancer/workspace/warehouses');
        const whData = await whResponse.json();
        if (whData.error || whData.detail) {
          setError(`Warehouses: ${whData.error || whData.detail}`);
          setWarehouses([]);
        } else {
          setWarehouses(whData.warehouses || []);
        }
      } catch (err) {
        setError(`Failed to fetch warehouses: ${err}`);
        setWarehouses([]);
      } finally {
        setLoadingWarehouses(false);
      }

      // Fetch Genie spaces
      setLoadingSpaces(true);
      try {
        const spaceResponse = await fetch('/api/enhancer/workspace/spaces');
        const spaceData = await spaceResponse.json();
        if (spaceData.error || spaceData.detail) {
          setError(prev => prev ? `${prev} | Spaces: ${spaceData.error || spaceData.detail}` : `Spaces: ${spaceData.error || spaceData.detail}`);
          setSpaces([]);
        } else {
          setSpaces(spaceData.spaces || []);
        }
      } catch (err) {
        setError(prev => prev ? `${prev} | Failed to fetch spaces: ${err}` : `Failed to fetch spaces: ${err}`);
        setSpaces([]);
      } finally {
        setLoadingSpaces(false);
      }
    };

    fetchResources();
  }, []);

  const handleNext = () => {
    onUpdate(config);
    onNext();
  };

  const isValid = config.warehouse_id && config.space_id;

  return (
    <div className="space-y-6 text-gray-900">
      <h2 className="text-2xl font-bold text-gray-900">⚙️ Configure Workspace</h2>

      <div className="p-4 bg-blue-50 border border-blue-200 rounded">
        <p className="text-sm text-blue-700">
          🔐 This app uses your Databricks credentials (OBO - On Behalf Of).
          All operations run with your permissions.
        </p>
      </div>

      <div className="space-y-4">
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium mb-2 text-gray-700">SQL Warehouse</label>
          {loadingWarehouses ? (
            <div className="text-sm text-gray-500 py-2">Loading warehouses...</div>
          ) : warehouses.length > 0 ? (
            <select
              value={config.warehouse_id}
              onChange={(e) => setConfig({ ...config, warehouse_id: e.target.value })}
              className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
            >
              <option value="">Select a warehouse...</option>
              {warehouses.map((wh) => (
                <option key={wh.id} value={wh.id}>
                  {wh.name} ({wh.state})
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={config.warehouse_id}
              onChange={(e) => setConfig({ ...config, warehouse_id: e.target.value })}
              placeholder="Enter warehouse ID manually..."
              className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
            />
          )}
        </div>

        <div>
          <label className="block text-sm font-medium mb-2 text-gray-700">Genie Space</label>
          {loadingSpaces ? (
            <div className="text-sm text-gray-500 py-2">Loading spaces...</div>
          ) : spaces.length > 0 ? (
            <select
              value={config.space_id}
              onChange={(e) => setConfig({ ...config, space_id: e.target.value })}
              className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
            >
              <option value="">Select a space...</option>
              {spaces.map((space) => (
                <option key={space.id} value={space.id}>
                  {space.name} ({space.id})
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={config.space_id}
              onChange={(e) => setConfig({ ...config, space_id: e.target.value })}
              placeholder="Enter space ID manually..."
              className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
            />
          )}
        </div>

        <div>
          <label className="block text-sm font-medium mb-2 text-gray-700">LLM Endpoint</label>
          <select
            value={config.llm_endpoint}
            onChange={(e) => setConfig({ ...config, llm_endpoint: e.target.value })}
            className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
          >
            <option value="databricks-gpt-5-2">databricks-gpt-5-2</option>
            <option value="databricks-gpt-4-turbo">databricks-gpt-4-turbo</option>
          </select>
        </div>

        <div className="border-t pt-4">
          <h3 className="text-lg font-semibold mb-3 text-gray-900">🔄 Iteration Loop Configuration</h3>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2 text-gray-700">
                Target Score ({(config.target_score * 100).toFixed(0)}%)
              </label>
              <input
                type="range"
                min="0.70"
                max="1.00"
                step="0.05"
                value={config.target_score}
                onChange={(e) => setConfig({ ...config, target_score: parseFloat(e.target.value) })}
                className="w-full"
              />
              <p className="text-xs text-gray-600 mt-1">
                Loop continues until this score is reached
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-700">
                Max Iterations
              </label>
              <select
                value={config.max_iterations}
                onChange={(e) => setConfig({ ...config, max_iterations: parseInt(e.target.value) })}
                className="w-full px-4 py-2 border rounded text-gray-900 bg-white"
              >
                <option value="1">1 iteration</option>
                <option value="2">2 iterations</option>
                <option value="3">3 iterations</option>
                <option value="5">5 iterations</option>
                <option value="10">10 iterations</option>
              </select>
              <p className="text-xs text-gray-600 mt-1">
                Maximum number of enhancement iterations
              </p>
            </div>
          </div>
        </div>

        <div className="border-t pt-4">
          <h3 className="text-lg font-semibold mb-3 text-gray-900">🛡️ Safety: Space Cloning</h3>

          <div className="p-4 bg-yellow-50 border border-yellow-200 rounded mb-3">
            <p className="text-sm text-yellow-800 font-medium">⚠️ Recommended: Clone space before testing</p>
            <p className="text-xs text-yellow-700 mt-1">
              Creates dev-working and dev-best copies. Changes are tested on clones, not production.
            </p>
          </div>

          <div className="flex items-center mb-3">
            <input
              type="checkbox"
              id="use_clone"
              checked={config.use_clone}
              onChange={(e) => setConfig({ ...config, use_clone: e.target.checked })}
              className="mr-2"
            />
            <label htmlFor="use_clone" className="text-sm text-gray-700">
              Clone production space for safe testing (recommended)
            </label>
          </div>

          {!config.use_clone && (
            <div className="p-3 bg-red-50 border border-red-200 rounded">
              <p className="text-sm text-red-600">
                ⚠️ Warning: Changes will be applied directly to production space!
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="flex justify-end">
        <button
          onClick={handleNext}
          disabled={!isValid}
          className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:bg-gray-400"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
