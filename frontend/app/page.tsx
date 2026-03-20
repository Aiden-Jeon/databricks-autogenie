/**
 * AutoGenie main page with tabbed interface.
 *
 * Two tabs:
 * - Lamp: Create new Genie Spaces from requirements
 * - Enhancer: Improve existing Genie Spaces with benchmarks
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { TabNavigation, WorkflowTab } from '@/components/TabNavigation';
import { Stepper } from '@/components/Stepper';
import SessionSidebar, { Session } from '@/components/SessionSidebar';

// Lamp Components
import { ParseStep } from '@/components/lamp/ParseStep';
import { GenerateStep } from '@/components/lamp/GenerateStep';
import { ValidateStep } from '@/components/lamp/ValidateStep';
import { BenchmarkStep } from '@/components/lamp/BenchmarkStep';
import { DeployStep } from '@/components/lamp/DeployStep';

// Enhancer Components
import { ConfigureStep } from '@/components/enhancer/ConfigureStep';
import { ScoreStep } from '@/components/enhancer/ScoreStep';
import { PlanStep } from '@/components/enhancer/PlanStep';
import { ApplyStep } from '@/components/enhancer/ApplyStep';
import { AutoLoopStep } from '@/components/enhancer/AutoLoopStep';

// API base URL
const API_BASE = '';

/** Number of sessions to fetch per page */
const SESSIONS_PAGE_SIZE = 50;

/** Default target score for new sessions */
const DEFAULT_TARGET_SCORE = 0.90;

/** Default max iterations for new sessions */
const DEFAULT_MAX_ITERATIONS = 3;

interface LampWorkflowState {
  parseResult?: {
    output_path: string;
    tables_found?: number;
    files_parsed?: number;
    enrichment_reasoning?: Record<string, string>;
    parsed_file_stats?: { size_bytes: number; line_count: number; char_count: number };
  };
  generateResult?: {
    output_path: string;
    tables_count?: number;
    instructions_count?: number;
    reasoning?: Record<string, string>;
  };
  validateResult?: {
    has_errors: boolean;
    tables_valid?: string[];
    tables_invalid?: number;
    issues?: Array<{ type: string; table: string; message: string; suggestions?: string[] }>;
  };
  benchmarks?: Array<{ question: string; expected_sql: string }>;
  deployResult?: {
    space_id: string;
    space_url: string;
  };
}

interface EnhancerWorkflowState {
  workspace_config?: Record<string, unknown>;
  loop_status?: string;
  initial_score?: number;
  latest_score?: number;
  [key: string]: unknown;
}

export default function Home() {
  // Tab state
  const [activeTab, setActiveTab] = useState<WorkflowTab>('lamp');
  const [enhancerMode, setEnhancerMode] = useState<'manual' | 'auto'>('manual');

  // Lamp workflow state
  const [lampStep, setLampStep] = useState(1);
  const [lampState, setLampState] = useState<LampWorkflowState>({});

  // Enhancer workflow state
  const [enhancerStep, setEnhancerStep] = useState(1);
  const [enhancerState, setEnhancerState] = useState<EnhancerWorkflowState>({});

  // Session management
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [restoringSession, setRestoringSession] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const lampSteps = ['Upload & Extract', 'Generate', 'Validate', 'Benchmark', 'Deploy', 'Complete'];
  const enhancerSteps = ['Configure', 'Score', 'Plan & Apply', 'Validate'];

  // Load sessions
  const loadSessions = useCallback(async (offset = 0) => {
    setSessionsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/sessions?limit=${SESSIONS_PAGE_SIZE}&offset=${offset}`);
      const data = await response.json();

      if (offset === 0) {
        setSessions(data.sessions);
      } else {
        setSessions(prev => [...prev, ...data.sessions]);
      }
      setHasMore(data.sessions.length === SESSIONS_PAGE_SIZE);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Create session
  const createSession = async () => {
    setCreateError(null);
    try {
      const response = await fetch(`${API_BASE}/api/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow_type: activeTab,
          target_score: DEFAULT_TARGET_SCORE,
          max_iterations: DEFAULT_MAX_ITERATIONS
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create session');
      }

      const session = await response.json();
      setCurrentSessionId(session.session_id);

      // Reset workflow state
      if (activeTab === 'lamp') {
        setLampStep(1);
        setLampState({});
      } else {
        setEnhancerStep(1);
        setEnhancerState({});
      }

      // Reload sessions list
      await loadSessions();

      return session;
    } catch (error) {
      console.error('Failed to create session:', error);
      setCreateError(error instanceof Error ? error.message : 'Failed to create session');
      throw error;
    }
  };

  // Switch session
  const switchSession = async (sessionId: string) => {
    setRestoringSession(true);
    try {
      const response = await fetch(`${API_BASE}/api/sessions/${sessionId}`);
      const session = await response.json();

      setCurrentSessionId(sessionId);

      // Determine workflow type and restore state
      const workflowType = session.workflow_type || 'lamp';
      setActiveTab(workflowType);

      if (workflowType === 'lamp') {
        // Restore lamp workflow state from jobs
        const state: LampWorkflowState = {};
        let maxStep = 1;

        for (const job of session.jobs || []) {
          if (job.status === 'completed' && job.result) {
            if (job.type === 'parse') {
              state.parseResult = job.result;
              maxStep = Math.max(maxStep, 2);
            } else if (job.type === 'generate') {
              state.generateResult = job.result;
              maxStep = Math.max(maxStep, 3);
            } else if (job.type === 'validate') {
              state.validateResult = job.result;
              maxStep = Math.max(maxStep, 4);
            } else if (job.type === 'benchmark_validate') {
              state.benchmarks = job.result;
              maxStep = Math.max(maxStep, 5);
            } else if (job.type === 'deploy') {
              state.deployResult = job.result;
              maxStep = Math.max(maxStep, 6);
            }
          }
        }

        setLampState(state);
        setLampStep(maxStep);
      } else {
        // Restore enhancer workflow state
        const state: EnhancerWorkflowState = {
          workspace_config: session.workspace_config || {},
          loop_status: session.loop_status,
          initial_score: session.initial_score,
          latest_score: session.latest_score,
        };

        setEnhancerState(state);
        setEnhancerStep(session.current_step || 1);
      }
    } catch (error) {
      console.error('Failed to switch session:', error);
      // Reset to step 1 on error
      if (activeTab === 'lamp') {
        setLampStep(1);
        setLampState({});
      } else {
        setEnhancerStep(1);
        setEnhancerState({});
      }
    } finally {
      setRestoringSession(false);
    }
  };

  // Rename session
  const renameSession = async (sessionId: string, newName: string) => {
    try {
      await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName })
      });
      await loadSessions();
    } catch (error) {
      console.error('Failed to rename session:', error);
    }
  };

  // Delete session
  const deleteSession = async (sessionId: string) => {
    if (!confirm('Are you sure you want to delete this session?')) return;

    try {
      await fetch(`${API_BASE}/api/sessions/${sessionId}`, { method: 'DELETE' });

      if (currentSessionId === sessionId) {
        setCurrentSessionId(null);
        setLampStep(1);
        setLampState({});
        setEnhancerStep(1);
        setEnhancerState({});
      }

      await loadSessions();
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  // Load more sessions
  const loadMoreSessions = async () => {
    await loadSessions(sessions.length);
  };

  // Handle tab change
  const handleTabChange = (tab: WorkflowTab) => {
    setActiveTab(tab);
    // When switching tabs, clear current session if it doesn't match the new tab
    const currentSession = sessions.find(s => s.session_id === currentSessionId);
    if (currentSession && currentSession.workflow_type !== tab) {
      setCurrentSessionId(null);
    }
  };

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Session Sidebar */}
      <SessionSidebar
        currentSessionId={currentSessionId}
        sessions={sessions}
        activeTab={activeTab}
        hasMore={hasMore}
        loading={sessionsLoading}
        onSessionSwitch={switchSession}
        onSessionCreate={createSession}
        onSessionRename={renameSession}
        onSessionDelete={deleteSession}
        onLoadMore={loadMoreSessions}
      />

      {/* Main Content */}
      <div className="flex-1 overflow-auto bg-gradient-to-br from-gray-50 to-gray-100">
        {/* Loading Overlay */}
        {restoringSession && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white p-6 rounded-lg shadow-xl">
              <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4" />
              <p className="text-gray-700">Restoring session...</p>
            </div>
          </div>
        )}

        <div className="container mx-auto p-8 max-w-6xl">
          {/* Header */}
          <header className="mb-6">
            <h1 className="text-4xl font-bold text-gray-900 mb-2">
              AutoGenie
            </h1>
            <p className="text-gray-600">
              Create and enhance Databricks Genie Spaces
            </p>
            {currentSessionId && (
              <p className="text-sm text-gray-500 mt-1" suppressHydrationWarning>
                Session: {currentSessionId}
              </p>
            )}
          </header>

          {/* Tab Navigation */}
          <TabNavigation activeTab={activeTab} onTabChange={handleTabChange} />

          {/* Lamp Tab Content */}
          {activeTab === 'lamp' && (
            <>
              <Stepper currentStep={lampStep} steps={lampSteps} />

              <div className="bg-white rounded-lg shadow-lg p-8 mt-8">
                {/* Empty State */}
                {!currentSessionId && (
                  <div className="text-center py-12">
                    <div className="bg-blue-50 p-8 rounded-lg border border-blue-200 inline-block">
                      <h2 className="text-3xl font-bold text-blue-900 mb-4">
                        🪔 Create a New Genie Space
                      </h2>
                      <p className="text-gray-700 mb-6 max-w-md">
                        Upload your requirements and let AI generate a complete Genie Space configuration.
                      </p>

                      {createError && (
                        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
                          <p className="text-red-800 text-sm">
                            <span className="font-semibold">Error:</span> {createError}
                          </p>
                        </div>
                      )}

                      <button
                        onClick={createSession}
                        className="px-8 py-4 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors text-lg font-medium"
                      >
                        Create New Session
                      </button>
                    </div>
                  </div>
                )}

                {/* Lamp Workflow Steps */}
                {lampStep === 1 && currentSessionId && (
                  <ParseStep
                    sessionId={currentSessionId}
                    onComplete={(result) => {
                      setLampState((s) => ({ ...s, parseResult: result }));
                      setLampStep(2);
                    }}
                    existingResult={lampState.parseResult}
                  />
                )}

                {lampStep === 2 && currentSessionId && (
                  <GenerateStep
                    sessionId={currentSessionId}
                    requirementsPath={lampState.parseResult?.output_path}
                    onComplete={(result) => {
                      setLampState((s) => ({ ...s, generateResult: result }));
                      setLampStep(3);
                    }}
                    onPrevious={() => setLampStep(1)}
                    existingResult={lampState.generateResult}
                  />
                )}

                {lampStep === 3 && currentSessionId && (
                  <ValidateStep
                    sessionId={currentSessionId}
                    configPath={lampState.generateResult?.output_path}
                    onComplete={(result) => {
                      setLampState((s) => ({ ...s, validateResult: result }));
                      setLampStep(4);
                    }}
                    onPrevious={() => setLampStep(2)}
                    existingResult={lampState.validateResult}
                  />
                )}

                {lampStep === 4 && currentSessionId && (
                  <BenchmarkStep
                    sessionId={currentSessionId}
                    onComplete={(benchmarks) => {
                      setLampState((s) => ({ ...s, benchmarks }));
                      setLampStep(5);
                    }}
                    onPrevious={() => setLampStep(3)}
                    existingResult={lampState.benchmarks}
                  />
                )}

                {lampStep === 5 && currentSessionId && (
                  <DeployStep
                    sessionId={currentSessionId}
                    configPath={lampState.generateResult?.output_path}
                    onComplete={(result) => {
                      setLampState((s) => ({ ...s, deployResult: result }));
                      setLampStep(6);
                    }}
                    onPrevious={() => setLampStep(4)}
                    existingResult={lampState.deployResult}
                  />
                )}

                {lampStep === 6 && (
                  <div className="text-center">
                    <div className="bg-green-50 p-8 rounded-lg border border-green-200">
                      <h2 className="text-3xl font-bold text-green-800 mb-4">
                        Complete!
                      </h2>
                      <div className="space-y-3">
                        <p className="text-gray-700">
                          <span className="font-semibold">Space ID:</span>{' '}
                          <code className="bg-gray-100 px-2 py-1 rounded">
                            {lampState.deployResult?.space_id}
                          </code>
                        </p>
                        <a
                          href={lampState.deployResult?.space_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-block px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                        >
                          Open Genie Space
                        </a>
                      </div>
                    </div>

                    <div className="mt-6 flex gap-3 justify-center">
                      <button
                        onClick={() => setLampStep(5)}
                        className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
                      >
                        Back to Deploy
                      </button>
                      <button
                        onClick={createSession}
                        className="px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
                      >
                        Start New Workflow
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* Enhancer Tab Content */}
          {activeTab === 'enhancer' && (
            <>
              {/* Mode Toggle */}
              <div className="mb-6 flex items-center justify-center gap-2 p-1 bg-gray-200 rounded-lg w-fit mx-auto">
                <button
                  onClick={() => { setEnhancerMode('manual'); setEnhancerStep(1); }}
                  className={`px-6 py-2 rounded-md font-medium transition-all ${
                    enhancerMode === 'manual'
                      ? 'bg-white text-purple-600 shadow'
                      : 'text-gray-600 hover:text-gray-800'
                  }`}
                >
                  Manual Mode
                </button>
                <button
                  onClick={() => { setEnhancerMode('auto'); setEnhancerStep(1); }}
                  className={`px-6 py-2 rounded-md font-medium transition-all ${
                    enhancerMode === 'auto'
                      ? 'bg-white text-purple-600 shadow'
                      : 'text-gray-600 hover:text-gray-800'
                  }`}
                >
                  Auto-Loop Mode
                </button>
              </div>

              {enhancerMode === 'manual' && (
                <>
                  <Stepper currentStep={enhancerStep} steps={enhancerSteps} />

                  <div className="bg-white rounded-lg shadow-lg p-6 mt-8">
                    {/* Empty State */}
                    {!currentSessionId && (
                      <div className="text-center py-12">
                        <div className="bg-purple-50 p-8 rounded-lg border border-purple-200 inline-block">
                          <h2 className="text-3xl font-bold text-purple-900 mb-4">
                            Enhance an Existing Space
                          </h2>
                          <p className="text-gray-700 mb-6 max-w-md">
                            Improve your Genie Space with benchmark-driven optimization.
                          </p>

                          {createError && (
                            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
                              <p className="text-red-800 text-sm">
                                <span className="font-semibold">Error:</span> {createError}
                              </p>
                            </div>
                          )}

                          <button
                            onClick={createSession}
                            className="px-8 py-4 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors text-lg font-medium"
                          >
                            Create Enhancement Session
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Enhancer Manual Workflow Steps */}
                    {currentSessionId && enhancerStep === 1 && (
                      <ConfigureStep
                        state={enhancerState}
                        onUpdate={(updates) => setEnhancerState((s) => ({ ...s, ...updates }))}
                        onNext={() => setEnhancerStep(2)}
                        sessionId={currentSessionId}
                      />
                    )}

                    {currentSessionId && enhancerStep === 2 && (
                      <ScoreStep
                        state={enhancerState}
                        onUpdate={(updates) => setEnhancerState((s) => ({ ...s, ...updates }))}
                        onNext={() => setEnhancerStep(3)}
                        onBack={() => setEnhancerStep(1)}
                        sessionId={currentSessionId}
                      />
                    )}

                    {currentSessionId && enhancerStep === 3 && (
                      <PlanStep
                        state={enhancerState}
                        onUpdate={(updates) => setEnhancerState((s) => ({ ...s, ...updates }))}
                        onNext={() => setEnhancerStep(4)}
                        onBack={() => setEnhancerStep(2)}
                        sessionId={currentSessionId}
                      />
                    )}

                    {currentSessionId && enhancerStep === 4 && (
                      <ApplyStep
                        state={enhancerState}
                        onUpdate={(updates) => setEnhancerState((s) => ({ ...s, ...updates }))}
                        onBack={() => setEnhancerStep(3)}
                        onNextIteration={() => setEnhancerStep(2)}
                        sessionId={currentSessionId}
                      />
                    )}
                  </div>
                </>
              )}

              {enhancerMode === 'auto' && (
                <div className="bg-white rounded-lg shadow-lg p-6">
                  {!currentSessionId ? (
                    <div className="text-center py-12">
                      <div className="bg-purple-50 p-8 rounded-lg border border-purple-200 inline-block">
                        <h2 className="text-3xl font-bold text-purple-900 mb-4">
                          Auto-Loop Enhancement
                        </h2>
                        <p className="text-gray-700 mb-6 max-w-md">
                          Automatically iterate through Score → Plan → Apply until your target score is reached.
                        </p>

                        {createError && (
                          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
                            <p className="text-red-800 text-sm">
                              <span className="font-semibold">Error:</span> {createError}
                            </p>
                          </div>
                        )}

                        <button
                          onClick={createSession}
                          className="px-8 py-4 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors text-lg font-medium"
                        >
                          Start Auto-Loop Session
                        </button>
                      </div>
                    </div>
                  ) : (
                    <AutoLoopStep
                      state={enhancerState}
                      onUpdate={(updates) => setEnhancerState((s) => ({ ...s, ...updates }))}
                      onBack={() => setEnhancerMode('manual')}
                      sessionId={currentSessionId}
                    />
                  )}
                </div>
              )}
            </>
          )}

          <footer className="mt-8 text-center text-sm text-gray-500">
            <p>Powered by Databricks Foundation Models</p>
          </footer>
        </div>
      </div>
    </div>
  );
}
