/**
 * Run Error Types
 * 
 * Specific error classes for run-related failures.
 */

/**
 * Base class for run-related errors
 */
export class RunError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RunError';
  }
}

/**
 * Error thrown when a run exceeds its maximum duration
 */
export class RunTimeoutError extends RunError {
  readonly runId: string;
  readonly maxDurationMs: number;
  
  constructor(runId: string, maxDurationMs: number) {
    super(`Run ${runId} timed out after ${maxDurationMs}ms`);
    this.name = 'RunTimeoutError';
    this.runId = runId;
    this.maxDurationMs = maxDurationMs;
  }
}

/**
 * Error thrown when a run is cancelled
 */
export class RunCancelledError extends RunError {
  readonly runId: string;
  readonly reason: string;
  
  constructor(runId: string, reason: string = 'cancelled') {
    super(`Run ${runId} was cancelled: ${reason}`);
    this.name = 'RunCancelledError';
    this.runId = runId;
    this.reason = reason;
  }
}

/**
 * Error thrown when attempting an invalid state transition
 */
export class InvalidStateTransitionError extends RunError {
  readonly runId: string;
  readonly fromState: string;
  readonly toState: string;
  
  constructor(runId: string, fromState: string, toState: string) {
    super(`Invalid state transition for run ${runId}: ${fromState} -> ${toState}`);
    this.name = 'InvalidStateTransitionError';
    this.runId = runId;
    this.fromState = fromState;
    this.toState = toState;
  }
}

/**
 * Error thrown when a lease cannot be acquired
 */
export class LeaseAcquisitionError extends RunError {
  readonly userId: string;
  readonly runId: string;
  
  constructor(userId: string, runId: string) {
    super(`Could not acquire lease for user ${userId}, run ${runId}`);
    this.name = 'LeaseAcquisitionError';
    this.userId = userId;
    this.runId = runId;
  }
}

/**
 * Error thrown when a run is not found
 */
export class RunNotFoundError extends RunError {
  readonly runId: string;
  
  constructor(runId: string) {
    super(`Run not found: ${runId}`);
    this.name = 'RunNotFoundError';
    this.runId = runId;
  }
}

/**
 * Check if an error is a run cancellation error
 */
export function isCancellationError(error: unknown): error is RunCancelledError {
  return error instanceof RunCancelledError ||
    (error instanceof Error && 
     (error.name === 'RunCancelledError' || 
      error.message?.includes('cancelled') ||
      error.message?.includes('aborted')));
}

/**
 * Check if an error is a timeout error
 */
export function isTimeoutError(error: unknown): error is RunTimeoutError {
  return error instanceof RunTimeoutError ||
    (error instanceof Error && 
     (error.name === 'RunTimeoutError' || 
      error.message?.includes('timeout') ||
      error.message?.includes('timed out')));
}
