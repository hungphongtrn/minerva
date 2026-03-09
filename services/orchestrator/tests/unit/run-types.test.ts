/**
 * Run Types and State Machine Tests
 */

import { describe, it, expect } from 'vitest';
import {
  RunState,
  VALID_STATE_TRANSITIONS,
  isValidStateTransition,
  getValidNextStates,
  isTerminalState,
  isActiveState,
} from '../../src/types/run.js';

describe('RunState', () => {
  it('should have all required states', () => {
    expect(RunState.QUEUED).toBe('queued');
    expect(RunState.LEASED).toBe('leased');
    expect(RunState.RUNNING).toBe('running');
    expect(RunState.COMPLETED).toBe('completed');
    expect(RunState.FAILED).toBe('failed');
    expect(RunState.CANCELLED).toBe('cancelled');
    expect(RunState.TIMED_OUT).toBe('timed_out');
  });
});

describe('isValidStateTransition', () => {
  it('should allow QUEUED -> LEASED', () => {
    expect(isValidStateTransition(RunState.QUEUED, RunState.LEASED)).toBe(true);
  });

  it('should allow QUEUED -> CANCELLED', () => {
    expect(isValidStateTransition(RunState.QUEUED, RunState.CANCELLED)).toBe(true);
  });

  it('should allow LEASED -> RUNNING', () => {
    expect(isValidStateTransition(RunState.LEASED, RunState.RUNNING)).toBe(true);
  });

  it('should allow LEASED -> CANCELLED', () => {
    expect(isValidStateTransition(RunState.LEASED, RunState.CANCELLED)).toBe(true);
  });

  it('should allow RUNNING -> COMPLETED', () => {
    expect(isValidStateTransition(RunState.RUNNING, RunState.COMPLETED)).toBe(true);
  });

  it('should allow RUNNING -> FAILED', () => {
    expect(isValidStateTransition(RunState.RUNNING, RunState.FAILED)).toBe(true);
  });

  it('should allow RUNNING -> CANCELLED', () => {
    expect(isValidStateTransition(RunState.RUNNING, RunState.CANCELLED)).toBe(true);
  });

  it('should allow RUNNING -> TIMED_OUT', () => {
    expect(isValidStateTransition(RunState.RUNNING, RunState.TIMED_OUT)).toBe(true);
  });

  it('should not allow transitions from terminal states', () => {
    expect(isValidStateTransition(RunState.COMPLETED, RunState.RUNNING)).toBe(false);
    expect(isValidStateTransition(RunState.FAILED, RunState.RUNNING)).toBe(false);
    expect(isValidStateTransition(RunState.CANCELLED, RunState.RUNNING)).toBe(false);
    expect(isValidStateTransition(RunState.TIMED_OUT, RunState.RUNNING)).toBe(false);
  });

  it('should not allow invalid transitions', () => {
    expect(isValidStateTransition(RunState.QUEUED, RunState.RUNNING)).toBe(false);
    expect(isValidStateTransition(RunState.QUEUED, RunState.COMPLETED)).toBe(false);
    expect(isValidStateTransition(RunState.RUNNING, RunState.LEASED)).toBe(false);
    expect(isValidStateTransition(RunState.LEASED, RunState.QUEUED)).toBe(false);
  });
});

describe('getValidNextStates', () => {
  it('should return correct next states for QUEUED', () => {
    expect(getValidNextStates(RunState.QUEUED)).toEqual([
      RunState.LEASED,
      RunState.CANCELLED,
    ]);
  });

  it('should return correct next states for RUNNING', () => {
    expect(getValidNextStates(RunState.RUNNING)).toEqual([
      RunState.COMPLETED,
      RunState.FAILED,
      RunState.CANCELLED,
      RunState.TIMED_OUT,
    ]);
  });

  it('should return empty array for terminal states', () => {
    expect(getValidNextStates(RunState.COMPLETED)).toEqual([]);
    expect(getValidNextStates(RunState.FAILED)).toEqual([]);
    expect(getValidNextStates(RunState.CANCELLED)).toEqual([]);
    expect(getValidNextStates(RunState.TIMED_OUT)).toEqual([]);
  });
});

describe('isTerminalState', () => {
  it('should return true for terminal states', () => {
    expect(isTerminalState(RunState.COMPLETED)).toBe(true);
    expect(isTerminalState(RunState.FAILED)).toBe(true);
    expect(isTerminalState(RunState.CANCELLED)).toBe(true);
    expect(isTerminalState(RunState.TIMED_OUT)).toBe(true);
  });

  it('should return false for non-terminal states', () => {
    expect(isTerminalState(RunState.QUEUED)).toBe(false);
    expect(isTerminalState(RunState.LEASED)).toBe(false);
    expect(isTerminalState(RunState.RUNNING)).toBe(false);
  });
});

describe('isActiveState', () => {
  it('should return true for active states', () => {
    expect(isActiveState(RunState.LEASED)).toBe(true);
    expect(isActiveState(RunState.RUNNING)).toBe(true);
  });

  it('should return false for non-active states', () => {
    expect(isActiveState(RunState.QUEUED)).toBe(false);
    expect(isActiveState(RunState.COMPLETED)).toBe(false);
    expect(isActiveState(RunState.FAILED)).toBe(false);
    expect(isActiveState(RunState.CANCELLED)).toBe(false);
    expect(isActiveState(RunState.TIMED_OUT)).toBe(false);
  });
});
