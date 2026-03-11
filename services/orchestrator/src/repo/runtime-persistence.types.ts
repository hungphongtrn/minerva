import type { OwnerPrincipal } from '../types/owner.js';
import type { RunState } from '../types/run.js';
import type { SSEEventType } from '../sse/types.js';

export type SessionEntryKind = 'system' | 'user' | 'assistant' | 'tool_result' | 'custom';

export type RunAttemptState =
  | 'leased'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'timed_out'
  | 'interrupted';

export interface PersistedSession {
  id: string;
  owner: OwnerPrincipal;
  ownerKey: string;
  currentLeafEntryId?: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface PersistedSessionEntry {
  id: string;
  sessionId: string;
  parentEntryId?: string | null;
  sequence: number;
  entryType: SessionEntryKind;
  message: unknown;
  createdAt: Date;
}

export interface PersistedRun {
  id: string;
  sessionId?: string | null;
  owner: OwnerPrincipal;
  ownerKey: string;
  state: RunState;
  queuePosition?: number | null;
  leaseToken?: string | null;
  leaseExpiresAt?: Date | null;
  createdAt: Date;
  startedAt?: Date | null;
  completedAt?: Date | null;
  timeoutAt?: Date | null;
  maxDurationMs: number;
  agentPackId: string;
  prompt: string;
  error?: string | null;
  finalMessages?: unknown[] | null;
}

export interface PersistedRunAttempt {
  id: string;
  runId: string;
  attemptSeq: number;
  state: RunAttemptState;
  leaseToken?: string | null;
  startedAt?: Date | null;
  completedAt?: Date | null;
  error?: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface PersistedQueueEntry {
  runId: string;
  owner: OwnerPrincipal;
  ownerKey: string;
  position: number;
  enqueuedAt: Date;
}

export interface PersistedRunCancellation {
  id: string;
  runId: string;
  requestedBy: OwnerPrincipal;
  reason?: string | null;
  requestedAt: Date;
}

export interface PersistedOwnerLease {
  owner: OwnerPrincipal;
  ownerKey: string;
  runId: string;
  token: string;
  acquiredAt: Date;
  expiresAt: Date;
}

export interface PersistedReplayEvent<TPayload = unknown> {
  id: string;
  runId: string;
  sessionId?: string | null;
  attemptId?: string | null;
  owner: OwnerPrincipal;
  seq: number;
  type: SSEEventType;
  payload: TPayload;
  isTerminal: boolean;
  createdAt: Date;
}

export interface SessionStore {
  createSession(session: PersistedSession): Promise<void>;
  getSession(sessionId: string): Promise<PersistedSession | null>;
  listSessionsByOwner(ownerKey: string): Promise<PersistedSession[]>;
  appendEntry(entry: PersistedSessionEntry): Promise<void>;
  listEntries(sessionId: string): Promise<PersistedSessionEntry[]>;
  updateLeaf(sessionId: string, entryId: string | null): Promise<void>;
}

export interface RunStore {
  createRun(run: PersistedRun): Promise<void>;
  getRun(runId: string): Promise<PersistedRun | null>;
  listRunsByOwner(ownerKey: string): Promise<PersistedRun[]>;
  updateRun(runId: string, updates: Partial<PersistedRun>): Promise<void>;
}

export interface AttemptStore {
  createAttempt(attempt: PersistedRunAttempt): Promise<void>;
  listAttempts(runId: string): Promise<PersistedRunAttempt[]>;
  updateAttempt(attemptId: string, updates: Partial<PersistedRunAttempt>): Promise<void>;
}

export interface QueueStore {
  enqueue(entry: PersistedQueueEntry): Promise<void>;
  remove(runId: string): Promise<void>;
  listQueuedRuns(ownerKey: string): Promise<PersistedQueueEntry[]>;
  getEntry(runId: string): Promise<PersistedQueueEntry | null>;
}

export interface CancellationStore {
  recordCancellation(cancellation: PersistedRunCancellation): Promise<void>;
  listCancellations(runId: string): Promise<PersistedRunCancellation[]>;
}

export interface LeaseStore {
  upsertLease(lease: PersistedOwnerLease): Promise<void>;
  getLeaseByOwner(ownerKey: string): Promise<PersistedOwnerLease | null>;
  getLeaseByToken(token: string): Promise<PersistedOwnerLease | null>;
  releaseLease(token: string): Promise<void>;
}

export interface ReplayEventStore {
  appendEvent(event: PersistedReplayEvent): Promise<void>;
  listEventsAfter(runId: string, seqExclusive: number): Promise<PersistedReplayEvent[]>;
  deleteEventsForRun(runId: string): Promise<void>;
}
