# Core Concepts

## Agent Lifecycle

The Agent follows a well-defined lifecycle:

```
┌─────────────┐
│   Created   │
└──────┬──────┘
       │ prompt()
       ▼
┌─────────────┐     ┌─────────────┐
│  Streaming  │────▶│   Error     │
└──────┬──────┘     └─────────────┘
       │ complete
       ▼
┌─────────────┐
│    Idle     │
└─────────────┘
```

### State Management

The agent maintains internal state:

```typescript
interface AgentState {
  systemPrompt: string;
  model: Model<any>;
  thinkingLevel: ThinkingLevel;
  tools: AgentTool<any>[];
  messages: AgentMessage[];
  isStreaming: boolean;
  streamMessage: AgentMessage | null;
  pendingToolCalls: Set<string>;
  error?: string;
}
```

## Message Types

### AgentMessage vs LLM Message

The SDK distinguishes between two message types:

| Type | Purpose | Examples |
|------|---------|----------|
| `AgentMessage` | Application-level messages | user, assistant, toolResult, custom types |
| `Message` (LLM) | Messages the LLM can process | user, assistant, toolResult |

**Key difference**: AgentMessage supports extensibility through custom types that don't need to be understood by the LLM.

### Message Flow

```
AgentMessage[] → transformContext() → AgentMessage[] → convertToLlm() → Message[] → LLM
                    (optional)                           (required)
```

### Built-in Message Roles

```typescript
type AgentMessage = 
  | UserMessage      // User input
  | AssistantMessage // LLM response
  | ToolResultMessage // Tool execution result
  | CustomMessage    // App-specific types
```

## Turn-Based Execution

A **turn** consists of:
1. One LLM call
2. Zero or more tool executions
3. Final response

```
prompt("Hello")
├─ agent_start
├─ turn_start
├─ message_start/end (user)
├─ message_start/end (assistant)
├─ turn_end
└─ agent_end
```

With tool calls:
```
prompt("Read file")
├─ agent_start
├─ turn_start
├─ message_start/end (user)
├─ message_start/end (assistant with toolCall)
├─ tool_execution_start/end
├─ message_start/end (toolResult)
├─ turn_end
├─ turn_start
├─ message_start/end (assistant response)
├─ turn_end
└─ agent_end
```

## Context Window Management

The `transformContext` option allows pruning or transforming messages before each LLM call:

```typescript
const agent = new Agent({
  transformContext: async (messages, signal) => {
    if (estimateTokens(messages) > MAX_TOKENS) {
      return pruneOldMessages(messages);
    }
    return messages;
  },
});
```

## Steering and Follow-up

### Steering Messages

Interrupt the agent during execution:

```
User sends steering message
        │
        ▼
Tool completes
        │
        ▼
Remaining tools skipped
        │
        ▼
Steering message injected
        │
        ▼
LLM responds
```

```typescript
// Queue a steering message
agent.steer({
  role: "user",
  content: "Stop! Do this instead.",
  timestamp: Date.now(),
});
```

### Follow-up Messages

Queue work after agent finishes:

```
Agent completes all work
        │
        ▼
Check followUpQueue
        │
        ▼
Inject follow-up messages
        │
        ▼
Continue with new turn
```

```typescript
// Queue a follow-up message
agent.followUp({
  role: "user",
  content: "Also summarize the result.",
  timestamp: Date.now(),
});
```

### Modes

Both steering and follow-up support two modes:

| Mode | Behavior |
|------|----------|
| `"one-at-a-time"` | Process one message per turn (default) |
| `"all"` | Process all queued messages at once |

```typescript
agent.setSteeringMode("one-at-a-time");
agent.setFollowUpMode("all");
```

## Tool Execution Flow

```
AssistantMessage with toolCalls
        │
        ▼
For each toolCall:
  ├─ Find matching tool
  ├─ Validate arguments (JSON Schema)
  ├─ Execute
  ├─ Stream updates (optional)
  └─ Return result
        │
        ▼
Create ToolResultMessage
        │
        ▼
Add to context
        │
        ▼
LLM responds to results
```

## Error Handling

Tools should **throw errors** rather than return error content:

```typescript
execute: async (toolCallId, params, signal, onUpdate) => {
  if (!fs.existsSync(params.path)) {
    throw new Error(`File not found: ${params.path}`);
  }
  return { content: [...], details: {...} };
}
```

The agent catches errors and reports them to the LLM as tool errors with `isError: true`.

## Thinking Levels

Support for reasoning/thinking models:

```typescript
type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high" | "xhigh";

// Note: "xhigh" only supported by OpenAI gpt-5.1-codex-max, gpt-5.2, gpt-5.2-codex, gpt-5.3, and gpt-5.3-codex models
```

Custom budgets for token-based providers:

```typescript
agent.thinkingBudgets = {
  minimal: 128,
  low: 512,
  medium: 1024,
  high: 2048,
};
```
