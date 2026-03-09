# API Reference

## Classes

### Agent

The main class for managing agent state and execution.

#### Constructor

```typescript
constructor(opts: AgentOptions = {})
```

**AgentOptions:**

| Option | Type | Description |
|--------|------|-------------|
| `initialState` | `Partial<AgentState>` | Initial agent state |
| `convertToLlm` | `(messages: AgentMessage[]) => Message[] \| Promise<Message[]>` | Convert messages to LLM format |
| `transformContext` | `(messages: AgentMessage[], signal?: AbortSignal) => Promise<AgentMessage[]>` | Transform context before LLM call |
| `steeringMode` | `"all" \| "one-at-a-time"` | Steering message processing mode |
| `followUpMode` | `"all" \| "one-at-a-time"` | Follow-up message processing mode |
| `streamFn` | `StreamFn` | Custom stream function |
| `sessionId` | `string` | Session identifier for caching |
| `getApiKey` | `(provider: string) => Promise<string \| undefined> \| string \| undefined` | Dynamic API key resolution |
| `onPayload` | `SimpleStreamOptions["onPayload"]` | Inspect/replace payloads |
| `thinkingBudgets` | `ThinkingBudgets` | Custom thinking budgets |
| `transport` | `Transport` | Preferred transport |
| `maxRetryDelayMs` | `number` | Maximum retry delay |

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `state` | `AgentState` | Current agent state (read-only) |
| `sessionId` | `string \| undefined` | Get/set session ID |
| `thinkingBudgets` | `ThinkingBudgets \| undefined` | Get/set thinking budgets |
| `transport` | `Transport` | Get transport |
| `maxRetryDelayMs` | `number \| undefined` | Get/set max retry delay |

#### Methods

##### Prompting

```typescript
// Text prompt
async prompt(input: string, images?: ImageContent[]): Promise<void>

// AgentMessage prompt
async prompt(message: AgentMessage): Promise<void>

// Multiple messages
async prompt(messages: AgentMessage[]): Promise<void>

// Continue from current context
async continue(): Promise<void>
```

##### State Management

```typescript
setSystemPrompt(v: string): void
setModel(m: Model<any>): void
setThinkingLevel(l: ThinkingLevel): void
setTools(t: AgentTool<any>[]): void
replaceMessages(ms: AgentMessage[]): void
appendMessage(m: AgentMessage): void
clearMessages(): void
reset(): void
```

##### Steering & Follow-up

```typescript
steer(m: AgentMessage): void
followUp(m: AgentMessage): void
clearSteeringQueue(): void
clearFollowUpQueue(): void
clearAllQueues(): void
hasQueuedMessages(): boolean
setSteeringMode(mode: "all" | "one-at-a-time"): void
getSteeringMode(): "all" | "one-at-a-time"
setFollowUpMode(mode: "all" | "one-at-a-time"): void
getFollowUpMode(): "all" | "one-at-a-time"
```

##### Control

```typescript
abort(): void
waitForIdle(): Promise<void>
```

##### Events

```typescript
subscribe(fn: (e: AgentEvent) => void): () => void
```

---

## Types

### AgentState

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

### AgentMessage

```typescript
type AgentMessage = Message | CustomAgentMessages[keyof CustomAgentMessages];
```

### AgentTool

```typescript
interface AgentTool<TParameters extends TSchema = TSchema, TDetails = any> extends Tool<TParameters> {
  label: string;
  execute: (
    toolCallId: string,
    params: Static<TParameters>,
    signal?: AbortSignal,
    onUpdate?: AgentToolUpdateCallback<TDetails>,
  ) => Promise<AgentToolResult<TDetails>>;
}
```

### AgentToolResult

```typescript
interface AgentToolResult<T> {
  content: (TextContent | ImageContent)[];
  details: T;
}
```

### AgentEvent

```typescript
type AgentEvent =
  // Agent lifecycle
  | { type: "agent_start" }
  | { type: "agent_end"; messages: AgentMessage[] }
  // Turn lifecycle
  | { type: "turn_start" }
  | { type: "turn_end"; message: AgentMessage; toolResults: ToolResultMessage[] }
  // Message lifecycle
  | { type: "message_start"; message: AgentMessage }
  | { type: "message_update"; message: AgentMessage; assistantMessageEvent: AssistantMessageEvent }
  | { type: "message_end"; message: AgentMessage }
  // Tool execution
  | { type: "tool_execution_start"; toolCallId: string; toolName: string; args: any }
  | { type: "tool_execution_update"; toolCallId: string; toolName: string; args: any; partialResult: any }
  | { type: "tool_execution_end"; toolCallId: string; toolName: string; result: any; isError: boolean };
```

### AgentLoopConfig

```typescript
interface AgentLoopConfig extends SimpleStreamOptions {
  model: Model<any>;
  convertToLlm: (messages: AgentMessage[]) => Message[] | Promise<Message[]>;
  transformContext?: (messages: AgentMessage[], signal?: AbortSignal) => Promise<AgentMessage[]>;
  getApiKey?: (provider: string) => Promise<string | undefined> | string | undefined;
  getSteeringMessages?: () => Promise<AgentMessage[]>;
  getFollowUpMessages?: () => Promise<AgentMessage[]>;
}
```

### ThinkingLevel

```typescript
type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high" | "xhigh";
```

### StreamFn

```typescript
type StreamFn = (
  ...args: Parameters<typeof streamSimple>
) => ReturnType<typeof streamSimple> | Promise<ReturnType<typeof streamSimple>>;
```

---

## Functions

### Low-Level API

```typescript
// Start new agent loop
function agentLoop(
  prompts: AgentMessage[],
  context: AgentContext,
  config: AgentLoopConfig,
  signal?: AbortSignal,
  streamFn?: StreamFn,
): EventStream<AgentEvent, AgentMessage[]>

// Continue existing loop
function agentLoopContinue(
  context: AgentContext,
  config: AgentLoopConfig,
  signal?: AbortSignal,
  streamFn?: StreamFn,
): EventStream<AgentEvent, AgentMessage[]>
```

### Proxy Utilities

```typescript
function streamProxy(
  model: Model<any>,
  context: Context,
  options: ProxyStreamOptions & { authToken: string; proxyUrl: string },
): EventStream<StreamEvent, AssistantMessage>
```

---

## Interfaces

### AgentContext

```typescript
interface AgentContext {
  systemPrompt: string;
  messages: AgentMessage[];
  tools?: AgentTool<any>[];
}
```

### CustomAgentMessages

```typescript
interface CustomAgentMessages {
  // Empty by default - extend via declaration merging
}
```

Example extension:

```typescript
declare module "@mariozechner/pi-agent-core" {
  interface CustomAgentMessages {
    notification: { role: "notification"; text: string; timestamp: number };
  }
}
```

---

## Type Guards

### isStreaming

Check if agent is currently processing:

```typescript
if (agent.state.isStreaming) {
  // Agent is busy
}
```

### hasPendingToolCalls

Check for pending tool executions:

```typescript
if (agent.state.pendingToolCalls.size > 0) {
  // Tools are running
}
```
