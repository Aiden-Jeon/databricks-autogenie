/**
 * API client for AutoGenie backend.
 *
 * Lamp endpoints: /api/lamp/*
 * Enhancer endpoints: /api/enhancer/*
 * Shared endpoints: /api/* (sessions, jobs)
 */

const API_BASE = '';

export interface Session {
  session_id: string;
  name: string;
  workflow_type: 'lamp' | 'enhancer';
  created_at: string;
  updated_at: string;
  job_count: number;
  current_step: number;
}

export interface Job {
  job_id: string;
  type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  result?: any;
  error?: string;
  progress?: any;
  created_at?: string;
  completed_at?: string;
}

export interface FileProgress {
  name: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  cache_hit?: boolean;
  duration_ms?: number;
  pages_total?: number;
  pages_completed?: number;
  current_page?: number;
  extracted?: {
    questions_count: number;
    tables_count: number;
    queries_count: number;
  };
  error?: string;
}

export interface FileContentResponse {
  content: string;
  filename: string;
  size_bytes: number;
  line_count: number;
  char_count: number;
}

export interface ValidationFix {
  old_catalog: string;
  old_schema: string;
  old_table: string;
  new_catalog: string;
  new_schema: string;
  new_table: string;
}

// Lamp API Client
export const lampApi = {
  parse: async (sessionId: string, formData: FormData) => {
    const response = await fetch(`${API_BASE}/api/lamp/parse`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Parse failed');
    }
    return response.json();
  },

  generate: async (sessionId: string, requirementsPath: string, model = 'databricks-gpt-5-2') => {
    const response = await fetch(`${API_BASE}/api/lamp/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        requirements_path: requirementsPath,
        model,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Generate failed');
    }
    return response.json();
  },

  validate: async (sessionId: string, configPath: string) => {
    const response = await fetch(`${API_BASE}/api/lamp/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        config_path: configPath,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Validate failed');
    }
    return response.json();
  },

  fixValidation: async (
    sessionId: string,
    configPath: string,
    fixes: ValidationFix[],
    bulkCatalog?: string,
    bulkSchema?: string,
    excludeTables?: string[]
  ) => {
    const response = await fetch(`${API_BASE}/api/lamp/validate/fix`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        config_path: configPath,
        fixes,
        bulk_catalog: bulkCatalog,
        bulk_schema: bulkSchema,
        exclude_tables: excludeTables,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Fix validation failed');
    }
    return response.json();
  },

  deploy: async (sessionId: string, configPath: string, options: { parentPath?: string; spaceName?: string } = {}) => {
    const response = await fetch(`${API_BASE}/api/lamp/deploy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        config_path: configPath,
        parent_path: options.parentPath,
        space_name: options.spaceName,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Deploy failed');
    }
    return response.json();
  },

  validateBenchmarks: async (sessionId: string, benchmarks: any[]) => {
    const response = await fetch(`${API_BASE}/api/lamp/benchmark/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        benchmarks,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Benchmark validation failed');
    }
    return response.json();
  },

  getFile: async (sessionId: string, filename: string) => {
    const response = await fetch(`${API_BASE}/api/lamp/files/${sessionId}/${filename}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Get file failed');
    }
    return response.json();
  },

  getConfigMetadata: async (configPath: string) => {
    const response = await fetch(`${API_BASE}/api/lamp/config/metadata?config_path=${encodeURIComponent(configPath)}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Get config metadata failed');
    }
    return response.json();
  },

  getDownloadConfigUrl: (sessionId: string) => {
    return `${API_BASE}/api/lamp/files/${sessionId}/genie_config.json`;
  },

  getFileContent: async (sessionId: string, filename: string): Promise<FileContentResponse> => {
    const response = await fetch(`${API_BASE}/api/lamp/files/${sessionId}/${filename}/content`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Get file content failed');
    }
    return response.json();
  },
};

// Enhancer API Client
export const enhancerApi = {
  score: async (sessionId: string, workspaceConfig: any, benchmarks: any[]) => {
    const response = await fetch(`${API_BASE}/api/enhancer/jobs/score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        workspace_config: workspaceConfig,
        benchmarks,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Score failed');
    }
    return response.json();
  },

  plan: async (sessionId: string, workspaceConfig: any, failedBenchmarks: any[], iterationId?: string) => {
    const response = await fetch(`${API_BASE}/api/enhancer/jobs/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        workspace_config: workspaceConfig,
        failed_benchmarks: failedBenchmarks,
        iteration_id: iterationId,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Plan failed');
    }
    return response.json();
  },

  apply: async (sessionId: string, workspaceConfig: any, groupedFixes: any, dryRun = false) => {
    const response = await fetch(`${API_BASE}/api/enhancer/jobs/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        workspace_config: workspaceConfig,
        grouped_fixes: groupedFixes,
        dry_run: dryRun,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Apply failed');
    }
    return response.json();
  },

  startAutoLoop: async (sessionId: string, workspaceConfig: any, benchmarks: any[], targetScore = 0.90, maxIterations = 5) => {
    const response = await fetch(`${API_BASE}/api/enhancer/sessions/${sessionId}/auto-loop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workspace_config: workspaceConfig,
        benchmarks,
        target_score: targetScore,
        max_iterations: maxIterations,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Start auto-loop failed');
    }
    return response.json();
  },

  getWarehouses: async () => {
    const response = await fetch(`${API_BASE}/api/enhancer/workspace/warehouses`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Get warehouses failed');
    }
    return response.json();
  },

  getSpaces: async () => {
    const response = await fetch(`${API_BASE}/api/enhancer/workspace/spaces`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Get spaces failed');
    }
    return response.json();
  },

  uploadBenchmarks: async (sessionId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(`${API_BASE}/api/enhancer/sessions/${sessionId}/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Upload failed');
    }
    return response.json();
  },
};

// Shared API Client
export const sharedApi = {
  getJob: async (jobId: string): Promise<Job> => {
    const response = await fetch(`${API_BASE}/api/jobs/${jobId}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Get job failed');
    }
    return response.json();
  },

  cancelJob: async (jobId: string) => {
    const response = await fetch(`${API_BASE}/api/jobs/${jobId}/cancel`, { method: 'POST' });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Cancel job failed');
    }
    return response.json();
  },

  getSessions: async (workflowType?: string, limit = 50, offset = 0) => {
    let url = `${API_BASE}/api/sessions?limit=${limit}&offset=${offset}`;
    if (workflowType) url += `&workflow_type=${workflowType}`;
    const response = await fetch(url);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Get sessions failed');
    }
    return response.json();
  },

  createSession: async (workflowType: 'lamp' | 'enhancer', name?: string) => {
    const response = await fetch(`${API_BASE}/api/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow_type: workflowType, name }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Create session failed');
    }
    return response.json();
  },

  getSession: async (sessionId: string) => {
    const response = await fetch(`${API_BASE}/api/sessions/${sessionId}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Get session failed');
    }
    return response.json();
  },

  deleteSession: async (sessionId: string) => {
    const response = await fetch(`${API_BASE}/api/sessions/${sessionId}`, { method: 'DELETE' });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Delete session failed');
    }
    return response.json();
  },

  renameSession: async (sessionId: string, name: string) => {
    const response = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Rename session failed');
    }
    return response.json();
  },
};

// Legacy apiClient for backward compatibility with copied components
export const apiClient = {
  parse: lampApi.parse,
  generate: lampApi.generate,
  validate: lampApi.validate,
  fixValidation: lampApi.fixValidation,
  deploy: lampApi.deploy,
  validateBenchmarks: lampApi.validateBenchmarks,
  getFile: lampApi.getFile,
  getConfigMetadata: lampApi.getConfigMetadata,
  getDownloadConfigUrl: lampApi.getDownloadConfigUrl,
  getFileContent: lampApi.getFileContent,
  getJob: sharedApi.getJob,
  cancelJob: sharedApi.cancelJob,
};
