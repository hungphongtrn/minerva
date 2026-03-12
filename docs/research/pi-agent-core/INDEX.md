# @mariozechner/pi-agent-core SDK

A stateful agent framework with tool execution and event streaming capabilities, built on top of `@mariozechner/pi-ai`.

## Overview

The pi-agent-core SDK provides a robust, extensible framework for building AI agents with:

- **Stateful conversation management** - Persistent message history with context window management
- **Tool execution** - Type-safe tool calling with streaming support
- **Event streaming** - Fine-grained events for real-time UI updates
- **Steering & follow-up** - Interrupt and queue messages during agent execution
- **Multi-provider support** - Works with OpenAI, Anthropic, Google, and other LLM providers

## Package Information

| Property | Value |
|----------|-------|
| **Name** | `@mariozechner/pi-agent-core` |
| **Version** | 0.57.1 |
| **License** | MIT |
| **Node.js** | >= 20.0.0 |
| **Repository** | https://github.com/badlogic/pi-mono/tree/main/packages/agent |

## Installation

```bash
npm install @mariozechner/pi-agent-core
```

## Dependencies

- `@mariozechner/pi-ai` - Core AI streaming and model abstractions
- `@sinclair/typebox` - JSON Schema validation for tool parameters

## Quick Start

```typescript
import { Agent } from "@mariozechner/pi-agent-core";
import { getModel } from "@mariozechner/pi-ai";

const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
});

// Subscribe to events
agent.subscribe((event) => {
  if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

// Send a prompt
await agent.prompt("Hello!");
```

## Documentation Structure

- [Core Concepts](./concepts.md) - Agent lifecycle, message flow, and architecture
- [API Reference](./api-reference.md) - Complete API documentation
- [Events](./events.md) - Event system and streaming
- [Tools](./tools.md) - Defining and using tools
- [Examples](./examples.md) - Code examples and patterns

## Key Features

### 1. Stateful Agent Management

The `Agent` class maintains conversation state including:
- Message history (`AgentMessage[]`)
- System prompt
- Tool registry
- Streaming state
- Pending tool calls

### 2. Event-Driven Architecture

Fine-grained events for building responsive UIs:
- Agent lifecycle: `agent_start`, `agent_end`
- Turn lifecycle: `turn_start`, `turn_end`
- Message lifecycle: `message_start`, `message_update`, `message_end`
- Tool execution: `tool_execution_start`, `tool_execution_update`, `tool_execution_end`

### 3. Tool System

Type-safe tool definition with JSON Schema validation:

```typescript
const tool: AgentTool = {
  name: "read_file",
  label: "Read File",
  description: "Read a file's contents",
  parameters: Type.Object({
    path: Type.String({ description: "File path" }),
  }),
  execute: async (toolCallId, params, signal, onUpdate) => {
    const content = await fs.readFile(params.path, "utf-8");
    return {
      content: [{ type: "text", text: content }],
      details: { path: params.path, size: content.length },
    };
  },
};
```

### 4. Steering & Follow-up

Control agent execution flow:
- **Steering**: Interrupt during tool execution
- **Follow-up**: Queue messages after completion

### 5. Custom Message Types

Extend the message system via declaration merging:

```typescript
declare module "@mariozechner/pi-agent-core" {
  interface CustomAgentMessages {
    notification: { role: "notification"; text: string; timestamp: number };
  }
}
```

## Architecture

```
┌─────────────────┐
│   Agent Class   │
└────────┬────────┘
         │
    ┌────▼────┐
    │  State  │
    └────┬────┘
         │
    ┌────▼────┐    ┌──────────────┐
    │  Loop   │────│  LLM Stream  │
    └────┬────┘    └──────────────┘
         │
    ┌────▼────┐
    │  Events │
    └─────────┘
```

The agent loop handles:
1. Message transformation (AgentMessage → LLM Message)
2. LLM streaming
3. Tool execution
4. Event emission
5. State updates

## File Structure

```
packages/agent/
├── src/
│   ├── index.ts          # Public exports
│   ├── agent.ts          # Agent class
│   ├── agent-loop.ts     # Core loop logic
│   ├── types.ts          # Type definitions
│   └── proxy.ts          # Proxy utilities
├── test/                 # Test files
├── README.md             # Package README
└── package.json
```

## License

MIT License - Copyright (c) Mario Zechner
