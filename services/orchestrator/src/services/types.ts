import type { CreateRunRequest, Run, Sandbox, ToolCall, ToolResult } from '../types/index.js';

export interface IRunService {
  createRun(request: CreateRunRequest): Promise<Run>;
  cancelRun(runId: string): Promise<void>;
  getRun(runId: string): Promise<Run | null>;
}

export interface ISandboxService {
  createSandbox(userId: string): Promise<Sandbox>;
  executeTool(sandboxId: string, tool: ToolCall): Promise<ToolResult>;
  destroySandbox(sandboxId: string): Promise<void>;
}
