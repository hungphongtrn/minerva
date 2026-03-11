export interface SSEEvent {
  id: string;
  event: string;
  data: unknown;
}

// SSE Types (from sse/)
export {
  SSEEventEnvelope,
  SSEEventType,
  SSEEventCategory,
  SSEPayload,
  RunQueuedPayload,
  RunStartedPayload,
  RunCompletedPayload,
  RunFailedPayload,
  RunCancelledPayload,
  RunTimedOutPayload,
  StreamConnectedPayload,
  AgentStartPayload,
  AgentEndPayload,
  TurnStartPayload,
  TurnEndPayload,
  MessageStartPayload,
  MessageUpdatePayload,
  MessageEndPayload,
  ToolExecutionStartPayload,
  ToolExecutionUpdatePayload,
  ToolExecutionEndPayload,
} from '../sse/types.js';

export interface CreateRunRequest {
  prompt: string;
  context?: Record<string, unknown>;
}

export type { OwnerPrincipal } from './owner.js';

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

// Pack Types
export type {
  AgentPack,
  AgentIdentity,
  Skill,
  PackMetadata,
  PackValidationResult,
  PackValidationErrorItem,
  PackValidationWarningItem,
  SystemPrompt,
  PromptSection,
  PackLoaderConfig,
  AssemblyRules,
} from '../packs/types.js';

// Pack Errors
export {
  PackError,
  PackValidationError,
  PackNotFoundError,
  MissingRequiredFileError,
  SkillLoadError,
} from '../packs/errors.js';

// Pack Validator
export {
  PackValidator,
  type IPackValidator,
  validatePack,
  validatePackSync,
  packValidator,
} from '../packs/validator.js';

// Pack Loader
export {
  PackLoader,
  type IPackLoader,
  loadPack,
  loadSkills,
  parseAgentIdentity,
  packLoader,
  DEFAULT_LOADER_CONFIG,
} from '../packs/loader.js';

// Pack Assembler
export {
  SystemPromptAssembler,
  type ISystemPromptAssembler,
  assembleSystemPrompt,
  systemPromptAssembler,
  DEFAULT_ASSEMBLY_RULES,
} from '../packs/assembler.js';

// Sandbox Types
export {
  WorkspaceStrategy,
  type Workspace as SandboxWorkspace,
  type WorkspaceConfig,
  type ExecutionOptions,
  type ExecutionChunk,
  type ExecutionResult,
  type FileReadOptions,
  type FileWriteOptions,
  type NetworkCheckResult,
} from '../sandbox/types.js';
