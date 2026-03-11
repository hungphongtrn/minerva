-- Create enums
CREATE TYPE "RunLifecycleState" AS ENUM (
  'queued',
  'leased',
  'running',
  'completed',
  'failed',
  'cancelled',
  'timed_out'
);

CREATE TYPE "RunAttemptLifecycleState" AS ENUM (
  'leased',
  'running',
  'completed',
  'failed',
  'cancelled',
  'timed_out',
  'interrupted'
);

CREATE TYPE "SessionEntryType" AS ENUM (
  'system',
  'user',
  'assistant',
  'tool_result',
  'custom'
);

-- Create tables
CREATE TABLE "sessions" (
  "id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "subject_id" TEXT NOT NULL,
  "owner_key" TEXT NOT NULL,
  "current_leaf_entry_id" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "sessions_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "session_entries" (
  "id" TEXT NOT NULL,
  "session_id" TEXT NOT NULL,
  "parent_entry_id" TEXT,
  "sequence" INTEGER NOT NULL,
  "entry_type" "SessionEntryType" NOT NULL,
  "message_json" JSONB NOT NULL,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "session_entries_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "runs" (
  "id" TEXT NOT NULL,
  "session_id" TEXT,
  "tenant_id" TEXT NOT NULL,
  "subject_id" TEXT NOT NULL,
  "owner_key" TEXT NOT NULL,
  "state" "RunLifecycleState" NOT NULL,
  "queue_position" INTEGER,
  "lease_token" TEXT,
  "lease_expires_at" TIMESTAMP(3),
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "started_at" TIMESTAMP(3),
  "completed_at" TIMESTAMP(3),
  "timeout_at" TIMESTAMP(3),
  "max_duration_ms" INTEGER NOT NULL,
  "agent_pack_id" TEXT NOT NULL,
  "prompt" TEXT NOT NULL,
  "error" TEXT,
  "final_messages_json" JSONB,
  CONSTRAINT "runs_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "run_attempts" (
  "id" TEXT NOT NULL,
  "run_id" TEXT NOT NULL,
  "attempt_seq" INTEGER NOT NULL,
  "state" "RunAttemptLifecycleState" NOT NULL,
  "lease_token" TEXT,
  "started_at" TIMESTAMP(3),
  "completed_at" TIMESTAMP(3),
  "error" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "run_attempts_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "run_queue_entries" (
  "run_id" TEXT NOT NULL,
  "owner_key" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "subject_id" TEXT NOT NULL,
  "position" INTEGER NOT NULL,
  "enqueued_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "run_queue_entries_pkey" PRIMARY KEY ("run_id")
);

CREATE TABLE "run_cancellations" (
  "id" TEXT NOT NULL,
  "run_id" TEXT NOT NULL,
  "requested_by_tenant_id" TEXT NOT NULL,
  "requested_by_subject_id" TEXT NOT NULL,
  "reason" TEXT,
  "requested_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "run_cancellations_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "owner_leases" (
  "owner_key" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "subject_id" TEXT NOT NULL,
  "run_id" TEXT NOT NULL,
  "token" TEXT NOT NULL,
  "acquired_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "expires_at" TIMESTAMP(3) NOT NULL,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "owner_leases_pkey" PRIMARY KEY ("owner_key")
);

CREATE TABLE "replay_events" (
  "id" TEXT NOT NULL,
  "run_id" TEXT NOT NULL,
  "session_id" TEXT,
  "attempt_id" TEXT,
  "tenant_id" TEXT NOT NULL,
  "subject_id" TEXT NOT NULL,
  "seq" INTEGER NOT NULL,
  "type" TEXT NOT NULL,
  "payload_json" JSONB NOT NULL,
  "is_terminal" BOOLEAN NOT NULL DEFAULT false,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "replay_events_pkey" PRIMARY KEY ("id")
);

-- Create indexes
CREATE UNIQUE INDEX "sessions_current_leaf_entry_id_key" ON "sessions"("current_leaf_entry_id");
CREATE INDEX "sessions_owner_key_created_at_idx" ON "sessions"("owner_key", "created_at");
CREATE UNIQUE INDEX "session_entries_session_id_sequence_key" ON "session_entries"("session_id", "sequence");
CREATE INDEX "session_entries_session_id_parent_entry_id_idx" ON "session_entries"("session_id", "parent_entry_id");
CREATE UNIQUE INDEX "runs_lease_token_key" ON "runs"("lease_token");
CREATE INDEX "runs_owner_key_created_at_idx" ON "runs"("owner_key", "created_at");
CREATE INDEX "runs_state_created_at_idx" ON "runs"("state", "created_at");
CREATE INDEX "runs_session_id_created_at_idx" ON "runs"("session_id", "created_at");
CREATE UNIQUE INDEX "run_attempts_run_id_attempt_seq_key" ON "run_attempts"("run_id", "attempt_seq");
CREATE INDEX "run_attempts_run_id_created_at_idx" ON "run_attempts"("run_id", "created_at");
CREATE INDEX "run_queue_entries_owner_key_position_idx" ON "run_queue_entries"("owner_key", "position");
CREATE INDEX "run_cancellations_run_id_requested_at_idx" ON "run_cancellations"("run_id", "requested_at");
CREATE UNIQUE INDEX "owner_leases_run_id_key" ON "owner_leases"("run_id");
CREATE UNIQUE INDEX "owner_leases_token_key" ON "owner_leases"("token");
CREATE INDEX "owner_leases_expires_at_idx" ON "owner_leases"("expires_at");
CREATE UNIQUE INDEX "replay_events_run_id_seq_key" ON "replay_events"("run_id", "seq");
CREATE INDEX "replay_events_tenant_id_subject_id_run_id_seq_idx" ON "replay_events"("tenant_id", "subject_id", "run_id", "seq");

-- Add foreign keys
ALTER TABLE "sessions"
ADD CONSTRAINT "sessions_current_leaf_entry_id_fkey"
FOREIGN KEY ("current_leaf_entry_id") REFERENCES "session_entries"("id")
ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "session_entries"
ADD CONSTRAINT "session_entries_session_id_fkey"
FOREIGN KEY ("session_id") REFERENCES "sessions"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "session_entries"
ADD CONSTRAINT "session_entries_parent_entry_id_fkey"
FOREIGN KEY ("parent_entry_id") REFERENCES "session_entries"("id")
ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "runs"
ADD CONSTRAINT "runs_session_id_fkey"
FOREIGN KEY ("session_id") REFERENCES "sessions"("id")
ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "run_attempts"
ADD CONSTRAINT "run_attempts_run_id_fkey"
FOREIGN KEY ("run_id") REFERENCES "runs"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "run_queue_entries"
ADD CONSTRAINT "run_queue_entries_run_id_fkey"
FOREIGN KEY ("run_id") REFERENCES "runs"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "run_cancellations"
ADD CONSTRAINT "run_cancellations_run_id_fkey"
FOREIGN KEY ("run_id") REFERENCES "runs"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "owner_leases"
ADD CONSTRAINT "owner_leases_run_id_fkey"
FOREIGN KEY ("run_id") REFERENCES "runs"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "replay_events"
ADD CONSTRAINT "replay_events_run_id_fkey"
FOREIGN KEY ("run_id") REFERENCES "runs"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "replay_events"
ADD CONSTRAINT "replay_events_attempt_id_fkey"
FOREIGN KEY ("attempt_id") REFERENCES "run_attempts"("id")
ON DELETE SET NULL ON UPDATE CASCADE;
