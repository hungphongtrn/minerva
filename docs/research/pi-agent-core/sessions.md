# Pi Coding Agent: Session Architecture

**Source**: [pi-mono/packages/coding-agent/docs/session.md](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/session.md)  
**Repository**: badlogic/pi-mono

## Overview

Pi coding agent uses a tree-based session persistence model stored as JSONL files. Sessions support non-linear conversation flows through branching, context compaction, and extension state management.

---

## Session File Format

### Storage Format: JSONL

Sessions are stored as **JSON Lines** (JSONL) files where each line is a JSON object with a `type` field.

**Key characteristics**:
- Tree structure via `id`/`parentId` fields
- Enables in-place branching without creating new files
- Linear entries are replaced by parent-child relationships

### File Location

```
~/.pi/agent/sessions/--<path>--/<timestamp>_<uuid>.jsonl
```

Where `<path>` is the working directory with `/` replaced by `-`.

### Session Version

Sessions are auto-migrated on load to the current version:

| Version | Description |
|---------|-------------|
| v1 | Linear entry sequence (legacy) |
| v2 | Tree structure with `id`/`parentId` linking |
| v3 | Renamed `hookMessage` role to `custom` (extensions unification) |

---

## Message Types

### Content Blocks

All messages contain arrays of typed content blocks:

```typescript
// Text content
interface TextContent {
  type: "text";
  text: string;
}

// Image content (base64 encoded)
interface ImageContent {
  type: "image";
  data: string;      // base64 encoded
  mimeType: string;  // e.g., "image/jpeg", "image/png"
}

// LLM thinking/reasoning content
interface ThinkingContent {
  type: "thinking";
  thinking: string;
}

// Tool invocations
interface ToolCall {
  type: "toolCall";
  id: string;
  name: string;
  arguments: Record<string, any>;
}
```

### Base Message Types (from pi-ai package)

```typescript
interface UserMessage {
  role: "user";
  content: string | (TextContent | ImageContent)[];
  timestamp: number;  // Unix ms
}

interface AssistantMessage {
  role: "assistant";
  content: (TextContent | ThinkingContent | ToolCall)[];
  api: string;
  provider: string;
  model: string;
  usage: Usage;
  stopReason: "stop" | "length" | "toolUse" | "error" | "aborted";
  errorMessage?: string;
  timestamp: number;
}

interface ToolResultMessage {
  role: "toolResult";
  toolCallId: string;
  toolName: string;
  content: (TextContent | ImageContent)[];
  details?: any;      // Tool-specific metadata
  isError: boolean;
  timestamp: number;
}

interface Usage {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  cost: {
    input: number;
    output: number;
    cacheRead: number;
    cacheWrite: number;
    total: number;
  };
}
```

### Extended Message Types (from pi-coding-agent package)

```typescript
interface BashExecutionMessage {
  role: "bashExecution";
  command: string;
  output: string;
  exitCode: number | undefined;
  cancelled: boolean;
  truncated: boolean;
  fullOutputPath?: string;
  excludeFromContext?: boolean;  // true for !! prefix commands
  timestamp: number;
}

interface CustomMessage {
  role: "custom";
  customType: string;            // Extension identifier
  content: string | (TextContent | ImageContent)[];
  display: boolean;              // Show in TUI
  details?: any;                 // Extension-specific metadata
  timestamp: number;
}

interface BranchSummaryMessage {
  role: "branchSummary";
  summary: string;
  fromId: string;                // Entry we branched from
  timestamp: number;
}

interface CompactionSummaryMessage {
  role: "compactionSummary";
  summary: string;
  tokensBefore: number;
  timestamp: number;
}
```

### AgentMessage Union Type

```typescript
type AgentMessage =
  | UserMessage
  | AssistantMessage
  | ToolResultMessage
  | BashExecutionMessage
  | CustomMessage
  | BranchSummaryMessage
  | CompactionSummaryMessage;
```

---

## Entry Types

All entries (except `SessionHeader`) extend `SessionEntryBase`:

```typescript
interface SessionEntryBase {
  type: string;
  id: string;           // 8-char hex ID
  parentId: string | null;  // Parent entry ID (null for first entry)
  timestamp: string;    // ISO timestamp
}
```

### Entry Type Definitions

#### SessionHeader

First line of the file. Metadata only, not part of the tree.

```json
{"type":"session","version":3,"id":"uuid","timestamp":"2024-12-03T14:00:00.000Z","cwd":"/path/to/project"}
```

For forked sessions:
```json
{"type":"session","version":3,"id":"uuid","timestamp":"2024-12-03T14:00:00.000Z","cwd":"/path/to/project","parentSession":"/path/to/original/session.jsonl"}
```

#### SessionMessageEntry

A message in the conversation:

```json
{"type":"message","id":"a1b2c3d4","parentId":"prev1234","timestamp":"2024-12-03T14:00:01.000Z","message":{"role":"user","content":"Hello"}}
{"type":"message","id":"b2c3d4e5","parentId":"a1b2c3d4","timestamp":"2024-12-03T14:00:02.000Z","message":{"role":"assistant","content":[{"type":"text","text":"Hi!"}],"provider":"anthropic","model":"claude-sonnet-4-5","usage":{...},"stopReason":"stop"}}
{"type":"message","id":"c3d4e5f6","parentId":"b2c3d4e5","timestamp":"2024-12-03T14:00:03.000Z","message":{"role":"toolResult","toolCallId":"call_123","toolName":"bash","content":[{"type":"text","text":"output"}],"isError":false}}
```

#### ModelChangeEntry

Emitted when the user switches models mid-session:

```json
{"type":"model_change","id":"d4e5f6g7","parentId":"c3d4e5f6","timestamp":"2024-12-03T14:05:00.000Z","provider":"openai","modelId":"gpt-4o"}
```

#### ThinkingLevelChangeEntry

Emitted when the user changes the thinking/reasoning level:

```json
{"type":"thinking_level_change","id":"e5f6g7h8","parentId":"d4e5f6g7","timestamp":"2024-12-03T14:06:00.000Z","thinkingLevel":"high"}
```

#### CompactionEntry

Created when context is compacted:

```json
{"type":"compaction","id":"f6g7h8i9","parentId":"e5f6g7h8","timestamp":"2024-12-03T14:10:00.000Z","summary":"User discussed X, Y, Z...","firstKeptEntryId":"c3d4e5f6","tokensBefore":50000}
```

**Optional fields**:
- `details`: Implementation-specific data (e.g., `{ readFiles: string[], modifiedFiles: string[] }`)
- `fromHook`: `true` if generated by an extension

#### BranchSummaryEntry

Created when switching branches via `/tree` with LLM-generated summary:

```json
{"type":"branch_summary","id":"g7h8i9j0","parentId":"a1b2c3d4","timestamp":"2024-12-03T14:15:00.000Z","fromId":"f6g7h8i9","summary":"Branch explored approach A..."}
```

**Optional fields**:
- `details`: File tracking data
- `fromHook`: `true` if generated by extension

#### CustomEntry

Extension state persistence (does NOT participate in LLM context):

```json
{"type":"custom","id":"h8i9j0k1","parentId":"g7h8i9j0","timestamp":"2024-12-03T14:20:00.000Z","customType":"my-extension","data":{"count":42}}
```

Use `customType` to identify your extension's entries on reload.

#### CustomMessageEntry

Extension-injected messages that DO participate in LLM context:

```json
{"type":"custom_message","id":"i9j0k1l2","parentId":"h8i9j0k1","timestamp":"2024-12-03T14:25:00.000Z","customType":"my-extension","content":"Injected context...","display":true}
```

**Fields**:
- `content`: String or `(TextContent | ImageContent)[]`
- `display`: `true` = show in TUI with distinct styling
- `details`: Optional extension-specific metadata

#### LabelEntry

User-defined bookmark/marker on an entry:

```json
{"type":"label","id":"j0k1l2m3","parentId":"i9j0k1l2","timestamp":"2024-12-03T14:30:00.000Z","targetId":"a1b2c3d4","label":"checkpoint-1"}
```

Set `label` to `undefined` to clear a label.

#### SessionInfoEntry

Session metadata (e.g., user-defined display name):

```json
{"type":"session_info","id":"k1l2m3n4","parentId":"j0k1l2m3","timestamp":"2024-12-03T14:35:00.000Z","name":"Refactor auth module"}
```

---

## Tree Structure

Sessions form a tree where:

- First entry has `parentId: null`
- Each subsequent entry points to its parent via `parentId`
- Branching creates new children from an earlier entry
- The "leaf" is the current position in the tree

```
[user msg] ─── [assistant] ─── [user msg] ─── [assistant] ─┬─ [user msg] ← current leaf
                                                            │
                                                            └─ [branch_summary] ─── [user msg] ← alternate branch
```

### Context Building

`buildSessionContext()` walks from the current leaf to the root:

1. Collects all entries on the path
2. Extracts current model and thinking level settings
3. If a `CompactionEntry` is on the path:
   - Emits the summary first
   - Then messages from `firstKeptEntryId` to compaction
   - Then messages after compaction
4. Converts `BranchSummaryEntry` and `CustomMessageEntry` to appropriate message formats

---

## SessionManager API

### Static Creation Methods

| Method | Description |
|--------|-------------|
| `SessionManager.create(cwd, sessionDir?)` | New session |
| `SessionManager.open(path, sessionDir?)` | Open existing session file |
| `SessionManager.continueRecent(cwd, sessionDir?)` | Continue most recent or create new |
| `SessionManager.inMemory(cwd?)` | No file persistence |
| `SessionManager.forkFrom(sourcePath, targetCwd, sessionDir?)` | Fork session from another project |

### Static Listing Methods

| Method | Description |
|--------|-------------|
| `SessionManager.list(cwd, sessionDir?, onProgress?)` | List sessions for a directory |
| `SessionManager.listAll(onProgress?)` | List all sessions across all projects |

### Instance Methods - Session Management

| Method | Description |
|--------|-------------|
| `newSession(options?)` | Start new session (options: `{ parentSession?: string }`) |
| `setSessionFile(path)` | Switch to different session file |
| `createBranchedSession(leafId)` | Extract branch to new session file |

### Instance Methods - Appending

All return entry ID:

| Method | Description |
|--------|-------------|
| `appendMessage(message)` | Add message |
| `appendThinkingLevelChange(level)` | Record thinking change |
| `appendModelChange(provider, modelId)` | Record model change |
| `appendCompaction(summary, firstKeptEntryId, tokensBefore, details?, fromHook?)` | Add compaction |
| `appendCustomEntry(customType, data?)` | Extension state (not in context) |
| `appendSessionInfo(name)` | Set session display name |
| `appendCustomMessageEntry(customType, content, display, details?)` | Extension message (in context) |
| `appendLabelChange(targetId, label)` | Set/clear label |

### Instance Methods - Tree Navigation

| Method | Description |
|--------|-------------|
| `getLeafId()` | Current position |
| `getLeafEntry()` | Get current leaf entry |
| `getEntry(id)` | Get entry by ID |
| `getBranch(fromId?)` | Walk from entry to root |
| `getTree()` | Get full tree structure |
| `getChildren(parentId)` | Get direct children |
| `getLabel(id)` | Get label for entry |
| `branch(entryId)` | Move leaf to earlier entry |
| `resetLeaf()` | Reset leaf to null |
| `branchWithSummary(entryId, summary, details?, fromHook?)` | Branch with context summary |

### Instance Methods - Context & Info

| Method | Description |
|--------|-------------|
| `buildSessionContext()` | Get messages, thinkingLevel, and model for LLM |
| `getEntries()` | All entries (excluding header) |
| `getHeader()` | Session header metadata |
| `getSessionName()` | Get display name from latest session_info entry |
| `getCwd()` | Working directory |
| `getSessionDir()` | Session storage directory |
| `getSessionId()` | Session UUID |
| `getSessionFile()` | Session file path (undefined for in-memory) |
| `isPersisted()` | Whether session is saved to disk |

---

## Source Files

- [`packages/coding-agent/src/core/session-manager.ts`](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/src/core/session-manager.ts) - Session entry types and SessionManager
- [`packages/coding-agent/src/core/messages.ts`](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/src/core/messages.ts) - Extended message types (BashExecutionMessage, CustomMessage, etc.)
- [`packages/ai/src/types.ts`](https://github.com/badlogic/pi-mono/blob/main/packages/ai/src/types.ts) - Base message types (UserMessage, AssistantMessage, ToolResultMessage)
- [`packages/agent/src/types.ts`](https://github.com/badlogic/pi-mono/blob/main/packages/agent/src/types.ts) - AgentMessage union type

For TypeScript definitions in your project, inspect `node_modules/@mariozechner/pi-coding-agent/dist/` and `node_modules/@mariozechner/pi-ai/dist/`.

---

## Session Management

### Deleting Sessions

Sessions can be removed by deleting their `.jsonl` files under `~/.pi/agent/sessions/`.

Pi also supports deleting sessions interactively from `/resume`:
1. Select a session
2. Press `Ctrl+D`
3. Confirm deletion

When available, pi uses the `trash` CLI to avoid permanent deletion.

---

## Parsing Example

```typescript
import { readFileSync } from "fs";

const lines = readFileSync("session.jsonl", "utf8").trim().split("\n");

for (const line of lines) {
  const entry = JSON.parse(line);

  switch (entry.type) {
    case "session":
      console.log(`Session v${entry.version ?? 1}: ${entry.id}`);
      break;
    case "message":
      console.log(`[${entry.id}] ${entry.message.role}: ${JSON.stringify(entry.message.content)}`);
      break;
    case "compaction":
      console.log(`[${entry.id}] Compaction: ${entry.tokensBefore} tokens summarized`);
      break;
    case "branch_summary":
      console.log(`[${entry.id}] Branch from ${entry.fromId}`);
      break;
    case "custom":
      console.log(`[${entry.id}] Custom (${entry.customType}): ${JSON.stringify(entry.data)}`);
      break;
    case "custom_message":
      console.log(`[${entry.id}] Extension message (${entry.customType}): ${entry.content}`);
      break;
    case "label":
      console.log(`[${entry.id}] Label "${entry.label}" on ${entry.targetId}`);
      break;
    case "model_change":
      console.log(`[${entry.id}] Model: ${entry.provider}/${entry.modelId}`);
      break;
    case "thinking_level_change":
      console.log(`[${entry.id}] Thinking: ${entry.thinkingLevel}`);
      break;
  }
}
```

---

## Key Insights for Minerva

### Relevance to Minerva

The pi coding agent session architecture has several concepts applicable to Minerva:

1. **Tree-based conversation**: Non-linear session flows via parent-child relationships
2. **Context compaction**: Summarization of earlier messages to manage token limits
3. **Extension system**: Custom message types for plugin/extension state
4. **File-based persistence**: Simple JSONL format for durability

### Design Patterns

- **Immutable entries**: Once written, entries are never modified (append-only)
- **Branching without file duplication**: Tree structure enables multiple conversation paths in single file
- **Context building from leaf**: Always reconstruct context by walking from current position to root
- **Separation of concerns**: Base message types in `pi-ai`, extended types in `pi-coding-agent`

### Potential Adaptations

For Minerva's pi-agent-core implementation:
- Consider tree structure for supporting branching conversations
- Use entry IDs for referencing specific points in conversation history
- Implement context compaction for long-running sessions
- Support custom message types for extensibility
- Leverage similar content block pattern for rich message content

---

## Related Documentation

- [pi-agent-core Events Model](./events.md) - Event system that maps well to session entries
- [Minerva Architecture](../../architecture/INDEX.md) - System architecture overview
