/**
 * Tab navigation component for switching between Lamp and Enhancer modes.
 */

'use client';

export type WorkflowTab = 'lamp' | 'enhancer';

interface TabNavigationProps {
  activeTab: WorkflowTab;
  onTabChange: (tab: WorkflowTab) => void;
}

export function TabNavigation({ activeTab, onTabChange }: TabNavigationProps) {
  return (
    <div className="flex items-center justify-center gap-2 p-1 bg-gray-200 rounded-lg w-fit mx-auto mb-6">
      <button
        onClick={() => onTabChange('lamp')}
        className={`px-6 py-2.5 rounded-md font-medium transition-all flex items-center gap-2 ${
          activeTab === 'lamp'
            ? 'bg-white text-blue-600 shadow-sm'
            : 'text-gray-600 hover:text-gray-800 hover:bg-gray-100'
        }`}
      >
        <span className="text-lg">🪔</span>
        <span>Create New</span>
      </button>
      <button
        onClick={() => onTabChange('enhancer')}
        className={`px-6 py-2.5 rounded-md font-medium transition-all flex items-center gap-2 ${
          activeTab === 'enhancer'
            ? 'bg-white text-purple-600 shadow-sm'
            : 'text-gray-600 hover:text-gray-800 hover:bg-gray-100'
        }`}
      >
        <span className="text-lg">✨</span>
        <span>Enhance Existing</span>
      </button>
    </div>
  );
}
