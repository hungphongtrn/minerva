# Events

The pi-agent-core SDK uses a comprehensive event system for real-time updates. Events are emitted at every stage of the agent lifecycle.

## Event Categories

### Agent Lifecycle Events

| Event | Description | Payload |
|-------|-------------|---------|
| `agent_start` | Agent begins processing | None |
| `agent_end` | Agent completes | `messages: AgentMessage[]` |

### Turn Lifecycle Events

A **turn** is one LLM call plus any resulting tool executions.

| Event | Description | Payload |
|-------|-------------|---------|
| `turn_start` | New turn begins | None |
| `turn_end` | Turn completes | `message`, `toolResults` |

### Message Lifecycle Events

| Event | Description | Payload |
|-------|-------------|---------|
| `message_start` | Any message begins | `message: AgentMessage` |
| `message_update` | Assistant message streaming | `message`, `assistantMessageEvent` |
| `message_end` | Message completes | `message: AgentMessage` |

### Tool Execution Events

| Event | Description | Payload |
|-------|-------------|---------|
| `tool_execution_start` | Tool begins | `toolCallId`, `toolName`, `args` |
| `tool_execution_update` | Tool streams progress | `toolCallId`, `toolName`, `args`, `partialResult` |
| `tool_execution_end` | Tool completes | `toolCallId`, `toolName`, `result`, `isError` |

## Event Sequences

### Simple Prompt

```
prompt("Hello!")
├─ agent_start
├─ turn_start
├─ message_start   { message: userMessage }
├─ message_end     { message: userMessage }
├─ message_start   { message: assistantMessage }
├─ message_update  { message: partial, assistantMessageEvent: text_delta }
├─ message_update  { message: partial, assistantMessageEvent: text_delta }
├─ message_end     { message: assistantMessage }
├─ turn_end        { message: assistantMessage, toolResults: [] }
└─ agent_end       { messages: [userMessage, assistantMessage] }
```

### With Tool Calls

```
prompt("Read config.json")
├─ agent_start
├─ turn_start
│
├─ message_start/end  { userMessage }
│
├─ message_start      { assistantMessage with toolCall }
├─ message_update...  { streaming }
├─ message_end        { assistantMessage }
│
├─ tool_execution_start  { toolCallId, toolName, args }
├─ tool_execution_end    { toolCallId, toolName, result, isError }
│
├─ message_start/end  { toolResultMessage }
├─ turn_end           { message: assistantMessage, toolResults: [...] }
│
├─ turn_start
├─ message_start      { assistantMessage (response to tool) }
├─ message_update...
├─ message_end
├─ turn_end
└─ agent_end
```

### With Steering

```
prompt("Process files")
├─ agent_start
├─ turn_start
├─ message_start/end  { userMessage }
│
├─ message_start/end  { assistantMessage with 3 toolCalls }
│
├─ tool_execution_start  { file1 }
├─ tool_execution_end    { file1 }
│
// User calls steer("Stop after file2!")
│
├─ tool_execution_start  { file2 }
├─ tool_execution_end    { file2 }
│
// Remaining tool is skipped
├─ tool_execution_start  { file3 }
├─ tool_execution_end    { file3 skipped, isError: true }
├─ message_start/end     { toolResult (file3 skipped) }
├─ turn_end
│
// Steering message injected
├─ turn_start
├─ message_start/end  { steeringMessage }
├─ message_start/end  { assistant responds to steering }
├─ turn_end
└─ agent_end
```

## Subscribing to Events

```typescript
const unsubscribe = agent.subscribe((event) => {
  switch (event.type) {
    case "agent_start":
      console.log("Agent started");
      break;
    case "message_update":
      handleStreaming(event);
      break;
    case "tool_execution_start":
      showToolSpinner(event.toolName);
      break;
    case "tool_execution_end":
      hideToolSpinner(event.toolName);
      if (event.isError) {
        showError(event.result);
      }
      break;
  }
});

// Unsubscribe when done
unsubscribe();
```

## Streaming Text

```typescript
agent.subscribe((event) => {
  if (event.type === "message_update") {
    const { assistantMessageEvent } = event;
    
    switch (assistantMessageEvent.type) {
      case "text_delta":
        process.stdout.write(assistantMessageEvent.delta);
        break;
      case "thinking_delta":
        // Handle reasoning/thinking output
        break;
      case "toolcall_start":
      case "toolcall_delta":
        // Handle tool call streaming
        break;
    }
  }
});
```

## Building UI Updates

### Chat Interface

```typescript
const messages: AgentMessage[] = [];

agent.subscribe((event) => {
  switch (event.type) {
    case "message_start":
      messages.push(event.message);
      renderMessages();
      break;
      
    case "message_update":
      // Update the last message with partial content
      messages[messages.length - 1] = event.message;
      renderMessages();
      break;
      
    case "message_end":
      // Final update
      messages[messages.length - 1] = event.message;
      renderMessages();
      break;
  }
});
```

### Tool Status Display

```typescript
const activeTools = new Map<string, { name: string; startTime: number }>();

agent.subscribe((event) => {
  switch (event.type) {
    case "tool_execution_start":
      activeTools.set(event.toolCallId, {
        name: event.toolName,
        startTime: Date.now(),
      });
      updateToolDisplay();
      break;
      
    case "tool_execution_update":
      // Show progress
      const tool = activeTools.get(event.toolCallId);
      if (tool) {
        showToolProgress(tool.name, event.partialResult);
      }
      break;
      
    case "tool_execution_end":
      activeTools.delete(event.toolCallId);
      updateToolDisplay();
      
      if (event.isError) {
        showToolError(event.toolName, event.result);
      } else {
        showToolSuccess(event.toolName);
      }
      break;
  }
});
```

### Progress Indicators

```typescript
agent.subscribe((event) => {
  switch (event.type) {
    case "agent_start":
      showGlobalSpinner();
      break;
      
    case "agent_end":
      hideGlobalSpinner();
      break;
      
    case "turn_start":
      showTurnIndicator();
      break;
      
    case "turn_end":
      hideTurnIndicator();
      break;
  }
});
```

## EventStream API

The low-level functions return an `EventStream` that can be consumed with `for await`:

```typescript
import { agentLoop } from "@mariozechner/pi-agent-core";

const stream = agentLoop(prompts, context, config);

for await (const event of stream) {
  console.log(event.type);
}

// Get final result
const messages = await stream.result();
```

### Aborting Streams

```typescript
const controller = new AbortController();

const stream = agentLoop(prompts, context, config, controller.signal);

// Later...
controller.abort();
```
