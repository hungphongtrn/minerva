export interface SSEEvent {
  id: string;
  event: string;
  data: unknown;
}

export interface CreateRunRequest {
  userId: string;
  prompt: string;
  context?: Record<string, unknown>;
}

export interface Sandbox {
  id: string;
  userId: string;
  workspaceId: string;
  status: 'creating' | 'ready' | 'destroying' | 'error';
  createdAt: Date;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ToolResult {
  id: string;
  output: unknown;
  error?: string;
}

// Run Model Types (from run.ts)
export {
  Run,
  RunState,
  RunMetadata,
  AgentMessage,
  CreateRunInput,
  VALID_STATE_TRANSITIONS,
  isValidStateTransition,
  getValidNextStates,
  isTerminalState,
  isActiveState,
} from './run.js';

// Error Types (from errors.ts)
export {
  RunError,
  RunTimeoutError,
  RunCancelledError,
  InvalidStateTransitionError,
  LeaseAcquisitionError,
  RunNotFoundError,
  isCancellationError,
  isTimeoutError,
} from './errors.js';
