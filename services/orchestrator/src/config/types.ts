export interface OrchestratorConfig {
  server: {
    port: number;
    host: string;
  };
  logging: {
    level: 'debug' | 'info' | 'warn' | 'error';
  };
  daytona: {
    serverUrl: string;
    apiKey: string;
    target: string;
  };
}