import type { WorkspaceStrategy, WorkspaceConfig } from '../sandbox/types.js';

export interface OrchestratorConfig {
  server: {
    port: number;
    host: string;
  };
  gateway: {
    proofHeader: string;
    proofSecret: string;
    tenantIdHeader: string;
    subjectIdHeader: string;
  };
  database: {
    url?: string;
  };
  logging: {
    level: 'debug' | 'info' | 'warn' | 'error';
  };
  daytona: {
    serverUrl: string;
    apiKey: string;
    target: string;
  };
  packs: {
    basePath: string;
    maxSkillSize: number;
    allowedExtensions: string[];
  };
  sandbox: {
    strategy: WorkspaceStrategy;
    workspace: WorkspaceConfig;
    security: {
      maxFileSize: number;
      allowedPaths?: string[];
    };
  };
}
