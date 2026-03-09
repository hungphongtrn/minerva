/**
 * Run Model Types
 * 
 * Core types for run orchestration including state definitions,
 * run metadata, and supporting interfaces.
 */

/**
 * Run states following the state machine:
 * QUEUED → LEASED → RUNNING → COMPLETED
 *                       ↓
 *                    FAILED/CANCELLED/TIMED_OUT
 */
export enum RunState {
  QUEUED = 'queued',
  LEASED = 'leased',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
  TIMED_OUT = 'timed_out',
}

/**
 * Agent message structure for final results
 */
export interface AgentMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  toolCalls?: Array<{
    id: string;
    type: string;
    function: {
      name: string;
      arguments: string;
    };
  }>;
  toolCallId?: string;
}

/**
 * Core run entity representing an agent execution
 */
export interface Run {
  /** ULID run identifier */
  id: string;
  
  /** User who owns this run */
  userId: string;
  
  /** Current state in the state machine */
  state: RunState;
  
  /** Position in FIFO queue (null when active) */
  queuePosition?: number;
  
  /** Unique lease token for this run (ULID) */
  leaseToken?: string;
  
  /** Lease expiration time for crash recovery */
  leaseExpiresAt?: Date;
  
  /** When the run was created */
  createdAt: Date;
  
  /** When the run started executing */
  startedAt?: Date;
  
  /** When the run completed/failed/cancelled */
  completedAt?: Date;
  
  /** Scheduled timeout time */
  timeoutAt?: Date;
  
  /** Maximum duration in milliseconds */
  maxDurationMs: number;
  
  /** Agent pack to use for execution */
  agentPackId: string;
  
  /** Initial prompt/message */
  prompt: string;
  
  /** Error message if failed */
  error?: string;
  
  /** Final conversation messages */
  finalMessages?: AgentMessage[];
}

/**
 * Lightweight run metadata for API responses
 */
export interface RunMetadata {
  runId: string;
  state: RunState;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  queuePosition?: number;
  error?: string;
}

/**
 * Input for creating a new run
 */
export interface CreateRunInput {
  userId: string;
  agentPackId: string;
  prompt: string;
  maxDurationMs?: number;
}

/**
 * Valid state transitions in the run state machine
 */
export const VALID_STATE_TRANSITIONS: Record<RunState, RunState[]> = {
  [RunState.QUEUED]: [RunState.LEASED, RunState.CANCELLED],
  [RunState.LEASED]: [RunState.RUNNING, RunState.CANCELLED],
  [RunState.RUNNING]: [RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED, RunState.TIMED_OUT],
  [RunState.COMPLETED]: [],
  [RunState.FAILED]: [],
  [RunState.CANCELLED]: [],
  [RunState.TIMED_OUT]: [],
};

/**
 * Check if a state transition is valid
 */
export function isValidStateTransition(from: RunState, to: RunState): boolean {
  return VALID_STATE_TRANSITIONS[from]?.includes(to) ?? false;
}

/**
 * Get all valid next states from a given state
 */
export function getValidNextStates(state: RunState): RunState[] {
  return VALID_STATE_TRANSITIONS[state] ?? [];
}

/**
 * Check if a run is in a terminal state
 */
export function isTerminalState(state: RunState): boolean {
  return [
    RunState.COMPLETED,
    RunState.FAILED,
    RunState.CANCELLED,
    RunState.TIMED_OUT,
  ].includes(state);
}

/**
 * Check if a run is active (has acquired a lease)
 */
export function isActiveState(state: RunState): boolean {
  return [RunState.LEASED, RunState.RUNNING].includes(state);
}
