# Examples

## Basic Usage

### Simple Chat Agent

```typescript
import { Agent } from "@mariozechner/pi-agent-core";
import { getModel } from "@mariozechner/pi-ai";

const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
});

// Stream text to console
agent.subscribe((event) => {
  if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

await agent.prompt("Hello, how are you?");
console.log("\n--- Done ---");
```

### With Tool Use

```typescript
import { Agent } from "@mariozechner/pi-agent-core";
import { getModel } from "@mariozechner/pi-ai";
import { Type } from "@sinclair/typebox";
import * as fs from "fs/promises";

const readFileTool = {
  name: "read_file",
  label: "Read File",
  description: "Read a file's contents",
  parameters: Type.Object({
    path: Type.String({ description: "File path" }),
  }),
  execute: async (toolCallId, params) => {
    const content = await fs.readFile(params.path, "utf-8");
    return {
      content: [{ type: "text", text: content }],
      details: { path: params.path },
    };
  },
};

const agent = new Agent({
  initialState: {
    systemPrompt: "You can read files to help answer questions.",
    model: getModel("openai", "gpt-4o"),
    tools: [readFileTool],
  },
});

agent.subscribe((event) => {
  if (event.type === "message_update") {
    const { assistantMessageEvent } = event;
    if (assistantMessageEvent.type === "text_delta") {
      process.stdout.write(assistantMessageEvent.delta);
    }
  }
});

await agent.prompt("Read README.md and summarize it");
```

## Advanced Patterns

### Context Window Management

```typescript
const agent = new Agent({
  initialState: {
    systemPrompt: "You are an assistant with limited context.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
  transformContext: async (messages, signal) => {
    // Keep only last 20 messages
    if (messages.length > 20) {
      return messages.slice(-20);
    }
    return messages;
  },
});
```

### Multi-Modal Input

```typescript
import { Agent } from "@mariozechner/pi-agent-core";
import { getModel } from "@mariozechner/pi-ai";

const agent = new Agent({
  initialState: {
    systemPrompt: "You can analyze images.",
    model: getModel("openai", "gpt-4o"),
  },
});

// Load image
const imageBuffer = await fs.readFile("./image.png");
const base64Image = imageBuffer.toString("base64");

await agent.prompt("What's in this image?", [
  {
    type: "image",
    data: base64Image,
    mimeType: "image/png",
  },
]);
```

### Custom Message Types

```typescript
// Extend the module
declare module "@mariozechner/pi-agent-core" {
  interface CustomAgentMessages {
    notification: {
      role: "notification";
      text: string;
      timestamp: number;
      level: "info" | "warning" | "error";
    };
  }
}

const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
  // Filter out notifications for the LLM
  convertToLlm: (messages) => 
    messages.filter((m) => m.role !== "notification"),
});

// Add a notification
agent.appendMessage({
  role: "notification",
  text: "System maintenance scheduled",
  timestamp: Date.now(),
  level: "info",
});

await agent.prompt("What notifications do I have?");
```

### Steering During Tool Execution

```typescript
const agent = new Agent({
  initialState: {
    systemPrompt: "Process all files in the directory.",
    model: getModel("openai", "gpt-4o"),
    tools: [processFileTool],
  },
});

// Start processing
const processingPromise = agent.prompt("Process all files in ./data/");

// After 2 seconds, interrupt
setTimeout(() => {
  agent.steer({
    role: "user",
    content: "Actually, skip any JSON files and only process CSV files.",
    timestamp: Date.now(),
  });
}, 2000);

await processingPromise;
```

### Follow-up Messages

```typescript
const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
});

// Initial prompt
await agent.prompt("Analyze this data: ...");

// Queue follow-ups while agent is working
agent.followUp({
  role: "user",
  content: "Now create a summary of your analysis.",
  timestamp: Date.now(),
});

agent.followUp({
  role: "user",
  content: "Also suggest improvements.",
  timestamp: Date.now(),
});

// Continue to process follow-ups
await agent.continue();
```

### Dynamic API Keys

```typescript
const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("openai", "gpt-4o"),
  },
  // Resolve API key dynamically (e.g., from OAuth token)
  getApiKey: async (provider) => {
    if (provider === "openai") {
      return await refreshOAuthToken();
    }
    return process.env[`${provider.toUpperCase()}_API_KEY`];
  },
});
```

### Proxy Usage

```typescript
import { Agent, streamProxy } from "@mariozechner/pi-agent-core";

const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("openai", "gpt-4o"),
  },
  streamFn: (model, context, options) =>
    streamProxy(model, context, {
      ...options,
      authToken: await getAuthToken(),
      proxyUrl: "https://your-proxy-server.com/api/llm",
    }),
});
```

## Low-Level API

### Direct Loop Usage

```typescript
import { agentLoop, agentLoopContinue } from "@mariozechner/pi-agent-core";
import { getModel } from "@mariozechner/pi-ai";

const context = {
  systemPrompt: "You are helpful.",
  messages: [],
  tools: [],
};

const config = {
  model: getModel("openai", "gpt-4o"),
  convertToLlm: (msgs) => msgs.filter(m => ["user", "assistant", "toolResult"].includes(m.role)),
};

// Start new conversation
const userMessage = {
  role: "user",
  content: "Hello!",
  timestamp: Date.now(),
};

for await (const event of agentLoop([userMessage], context, config)) {
  console.log(event.type);
}

// Continue from existing context
for await (const event of agentLoopContinue(context, config)) {
  console.log(event.type);
}
```

### Building a Chat UI

```typescript
import { Agent } from "@mariozechner/pi-agent-core";

class ChatUI {
  private agent: Agent;
  private messages: AgentMessage[] = [];
  private currentStreamingMessage: AgentMessage | null = null;

  constructor() {
    this.agent = new Agent({
      initialState: {
        systemPrompt: "You are a helpful assistant.",
        model: getModel("anthropic", "claude-sonnet-4-20250514"),
      },
    });

    this.agent.subscribe(this.handleEvent.bind(this));
  }

  private handleEvent(event: AgentEvent) {
    switch (event.type) {
      case "message_start":
        this.currentStreamingMessage = event.message;
        this.render();
        break;

      case "message_update":
        this.currentStreamingMessage = event.message;
        this.renderStreaming();
        break;

      case "message_end":
        this.messages.push(event.message);
        this.currentStreamingMessage = null;
        this.render();
        break;

      case "tool_execution_start":
        this.showToolIndicator(event.toolName);
        break;

      case "tool_execution_end":
        this.hideToolIndicator(event.toolName);
        break;
    }
  }

  async sendMessage(text: string) {
    await this.agent.prompt(text);
  }

  async sendSteering(text: string) {
    this.agent.steer({
      role: "user",
      content: text,
      timestamp: Date.now(),
    });
  }

  private render() {
    // Render all messages
    console.clear();
    for (const msg of this.messages) {
      this.renderMessage(msg);
    }
    if (this.currentStreamingMessage) {
      this.renderMessage(this.currentStreamingMessage, true);
    }
  }

  private renderStreaming() {
    // Update only the streaming message
    if (this.currentStreamingMessage) {
      this.updateStreamingMessage(this.currentStreamingMessage);
    }
  }

  private renderMessage(msg: AgentMessage, isStreaming = false) {
    // Implementation...
  }

  private updateStreamingMessage(msg: AgentMessage) {
    // Implementation...
  }

  private showToolIndicator(name: string) {
    console.log(`🔧 Running ${name}...`);
  }

  private hideToolIndicator(name: string) {
    console.log(`✅ ${name} complete`);
  }
}
```

## Error Handling

### Retry Logic

```typescript
async function promptWithRetry(agent: Agent, text: string, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      await agent.prompt(text);
      return;
    } catch (error) {
      console.error(`Attempt ${attempt} failed:`, error);
      
      if (attempt === maxRetries) {
        throw error;
      }
      
      // Wait before retry
      await new Promise(r => setTimeout(r, 1000 * attempt));
      
      // Continue from current state
      await agent.continue();
    }
  }
}
```

### Aborting Operations

```typescript
const agent = new Agent({...});

// Set up timeout
const timeout = setTimeout(() => {
  console.log("Operation timed out, aborting...");
  agent.abort();
}, 30000);

try {
  await agent.prompt("Long running task...");
} finally {
  clearTimeout(timeout);
}
```

## Testing

### Mock Tool for Testing

```typescript
const mockTool: AgentTool = {
  name: "mock_api",
  label: "Mock API",
  description: "A mock API for testing",
  parameters: Type.Object({
    endpoint: Type.String(),
  }),
  execute: async (toolCallId, params) => {
    // Return mock data
    return {
      content: [{ type: "text", text: JSON.stringify({ mock: true, endpoint: params.endpoint }) }],
      details: { mock: true },
    };
  },
};

// Test the agent
const agent = new Agent({
  initialState: {
    systemPrompt: "You are a test assistant.",
    model: getModel("openai", "gpt-4o"),
    tools: [mockTool],
  },
});

// Collect events
const events: AgentEvent[] = [];
agent.subscribe((e) => events.push(e));

await agent.prompt("Call the mock API with endpoint 'users'");

// Assert on events
assert(events.some(e => e.type === "tool_execution_start"));
assert(events.some(e => e.type === "tool_execution_end"));
```
