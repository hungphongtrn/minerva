# @mariozechner/pi-ai Package Research

Research document for the `@mariozechner/pi-ai` package - a unified LLM API with automatic model discovery, provider configuration, token and cost tracking.

## Overview

The pi-ai package provides a unified interface for working with multiple LLM providers, abstracting away provider-specific implementations while maintaining full access to provider-specific features when needed.

## Package Information

| Property | Value |
|----------|-------|
| **Name** | `@mariozechner/pi-ai` |
| **Version** | 0.57.1 |
| **License** | MIT |
| **Node.js** | >= 20.0.0 |
| **Repository** | https://github.com/badlogic/pi-mono/tree/main/packages/ai |
| **Author** | Mario Zechner |

## Installation

```bash
npm install @mariozechner/pi-ai
```

TypeBox exports are re-exported: `Type`, `Static`, and `TSchema`.

## Dependencies

Key dependencies:
- `@anthropic-ai/sdk` - Anthropic API client
- `@aws-sdk/client-bedrock-runtime` - AWS Bedrock support
- `@google/genai` - Google Generative AI
- `@mistralai/mistralai` - Mistral API
- `@sinclair/typebox` - JSON Schema type system
- `ajv` / `ajv-formats` - Schema validation
- `openai` - OpenAI API client
- `undici` - HTTP client

## Supported Providers

The package supports the following LLM providers:

| Provider | API | Environment Variable |
|----------|-----|---------------------|
| OpenAI | `openai-responses` | `OPENAI_API_KEY` |
| Azure OpenAI | `azure-openai-responses` | `AZURE_OPENAI_API_KEY` |
| OpenAI Codex | `openai-codex-responses` | OAuth |
| Anthropic | `anthropic-messages` | `ANTHROPIC_API_KEY` or `ANTHROPIC_OAUTH_TOKEN` |
| Google | `google-generative-ai` | `GEMINI_API_KEY` |
| Vertex AI | `google-vertex` | `GOOGLE_CLOUD_API_KEY` or ADC |
| Mistral | `mistral-conversations` | `MISTRAL_API_KEY` |
| Groq | `openai-completions` | `GROQ_API_KEY` |
| Cerebras | `openai-completions` | `CEREBRAS_API_KEY` |
| xAI | `openai-completions` | `XAI_API_KEY` |
| OpenRouter | `openai-completions` | `OPENROUTER_API_KEY` |
| Vercel AI Gateway | `openai-completions` | `AI_GATEWAY_API_KEY` |
| MiniMax | `openai-completions` | `MINIMAX_API_KEY` |
| GitHub Copilot | `openai-responses` | `COPILOT_GITHUB_TOKEN` or `GH_TOKEN` |
| Google Gemini CLI | `google-gemini-cli` | OAuth |
| Antigravity | `google-gemini-cli` | OAuth |
| Amazon Bedrock | `bedrock-converse-stream` | AWS credentials |
| OpenCode Zen/Go | `openai-completions` | `OPENCODE_API_KEY` |
| Kimi For Coding | `anthropic-messages` | `KIMI_API_KEY` |

## Core API

### Model Selection

```typescript
import { getModel, getProviders, getModels } from '@mariozechner/pi-ai';

// Get all available providers
const providers = getProviders();
// ['openai', 'anthropic', 'google', 'xai', 'groq', ...]

// Get all models from a provider
const anthropicModels = getModels('anthropic');

// Get a specific model (fully typed with auto-completion)
const model = getModel('openai', 'gpt-4o-mini');
```

### Streaming API

```typescript
import { stream, getModel } from '@mariozechner/pi-ai';

const model = getModel('openai', 'gpt-4o-mini');
const context = {
  systemPrompt: 'You are a helpful assistant.',
  messages: [{ role: 'user', content: 'Hello!' }]
};

const s = stream(model, context);

for await (const event of s) {
  switch (event.type) {
    case 'text_delta':
      process.stdout.write(event.delta);
      break;
    case 'toolcall_end':
      console.log('Tool called:', event.toolCall.name);
      break;
    case 'done':
      console.log('Finished:', event.reason);
      break;
  }
}

// Get final message
const finalMessage = await s.result();
```

### Complete (Non-Streaming) API

```typescript
import { complete, getModel } from '@mariozechner/pi-ai';

const model = getModel('openai', 'gpt-4o-mini');
const response = await complete(model, context);

for (const block of response.content) {
  if (block.type === 'text') {
    console.log(block.text);
  } else if (block.type === 'toolCall') {
    console.log('Tool:', block.name, block.arguments);
  }
}
```

### Simple API with Reasoning

```typescript
import { completeSimple, streamSimple, getModel } from '@mariozechner/pi-ai';

const model = getModel('anthropic', 'claude-sonnet-4-20250514');

// Non-streaming with reasoning
const response = await completeSimple(model, context, {
  reasoning: 'medium'  // 'minimal' | 'low' | 'medium' | 'high' | 'xhigh'
});

// Streaming with reasoning
const s = streamSimple(model, context, { reasoning: 'high' });
for await (const event of s) {
  if (event.type === 'thinking_delta') {
    process.stdout.write(event.delta);
  }
}
```

## Configuration Options

### StreamOptions (Base Options)

All providers share these common options:

```typescript
interface StreamOptions {
  temperature?: number;           // Sampling temperature
  maxTokens?: number;             // Maximum tokens to generate
  signal?: AbortSignal;           // AbortController signal
  apiKey?: string;                // Override environment API key
  transport?: Transport;          // 'sse' | 'websocket' | 'auto'
  cacheRetention?: CacheRetention; // 'none' | 'short' | 'long'
  sessionId?: string;             // Session identifier for caching
  onPayload?: (payload, model) => unknown | undefined; // Debug callback
  headers?: Record<string, string>; // Custom HTTP headers
  maxRetryDelayMs?: number;       // Maximum retry delay (default: 60000)
  metadata?: Record<string, unknown>; // Provider-specific metadata
}
```

### SimpleStreamOptions

Extended options for `streamSimple()` and `completeSimple()`:

```typescript
interface SimpleStreamOptions extends StreamOptions {
  reasoning?: ThinkingLevel;      // 'minimal' | 'low' | 'medium' | 'high' | 'xhigh'
  thinkingBudgets?: ThinkingBudgets; // Custom token budgets per level
}
```

### Provider-Specific Options

#### OpenAI Responses

```typescript
interface OpenAIResponsesOptions extends StreamOptions {
  reasoningEffort?: 'minimal' | 'low' | 'medium' | 'high' | 'xhigh';
  reasoningSummary?: 'auto' | 'detailed' | 'concise' | null;
  serviceTier?: 'auto' | 'default' | 'flex' | 'priority';
}
```

#### OpenAI Completions (and compatible providers)

```typescript
interface OpenAICompletionsOptions extends StreamOptions {
  toolChoice?: 'auto' | 'none' | 'required' | { type: 'function'; function: { name: string } };
  reasoningEffort?: 'minimal' | 'low' | 'medium' | 'high' | 'xhigh';
}
```

#### Anthropic

```typescript
interface AnthropicOptions extends StreamOptions {
  thinkingEnabled?: boolean;
  thinkingBudgetTokens?: number;
}
```

#### Google

```typescript
interface GoogleOptions extends StreamOptions {
  thinking?: {
    enabled: boolean;
    budgetTokens?: number;  // -1 for dynamic, 0 to disable
  };
}
```

## Environment Variables

### API Keys

| Provider | Environment Variable(s) |
|----------|------------------------|
| OpenAI | `OPENAI_API_KEY` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_BASE_URL` or `AZURE_OPENAI_RESOURCE_NAME` |
| Anthropic | `ANTHROPIC_API_KEY` or `ANTHROPIC_OAUTH_TOKEN` |
| Google | `GEMINI_API_KEY` |
| Vertex AI | `GOOGLE_CLOUD_API_KEY` or `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` + ADC |
| Mistral | `MISTRAL_API_KEY` |
| Groq | `GROQ_API_KEY` |
| Cerebras | `CEREBRAS_API_KEY` |
| xAI | `XAI_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |
| Vercel AI Gateway | `AI_GATEWAY_API_KEY` |
| zAI | `ZAI_API_KEY` |
| MiniMax | `MINIMAX_API_KEY` |
| OpenCode | `OPENCODE_API_KEY` |
| Kimi For Coding | `KIMI_API_KEY` |
| GitHub Copilot | `COPILOT_GITHUB_TOKEN` or `GH_TOKEN` or `GITHUB_TOKEN` |

### Azure OpenAI Additional Variables

- `AZURE_OPENAI_API_VERSION` - API version override (default: `v1`)
- `AZURE_OPENAI_DEPLOYMENT_NAME_MAP` - Model to deployment mapping (e.g., `gpt-4o-mini=my-deployment,gpt-4o=prod`)

### Vertex AI Configuration

```bash
# Local development (ADC)
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT="my-project"
export GOOGLE_CLOUD_LOCATION="us-central1"

# CI/Production (service account)
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

### Package-Specific Environment Variables

- `PI_AI_ANTIGRAVITY_VERSION` - Override Antigravity User-Agent version
- `PI_CACHE_RETENTION` - Set to `long` for extended prompt cache retention

## Custom Models

Create custom models for local inference or custom endpoints:

```typescript
import { Model, stream } from '@mariozechner/pi-ai';

// Ollama example
const ollamaModel: Model<'openai-completions'> = {
  id: 'llama-3.1-8b',
  name: 'Llama 3.1 8B (Ollama)',
  api: 'openai-completions',
  provider: 'ollama',
  baseUrl: 'http://localhost:11434/v1',
  reasoning: false,
  input: ['text'],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 128000,
  maxTokens: 32000
};

// LiteLLM proxy with compat settings
const litellmModel: Model<'openai-completions'> = {
  id: 'gpt-4o',
  name: 'GPT-4o (via LiteLLM)',
  api: 'openai-completions',
  provider: 'litellm',
  baseUrl: 'http://localhost:4000/v1',
  reasoning: false,
  input: ['text', 'image'],
  cost: { input: 2.5, output: 10, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 128000,
  maxTokens: 16384,
  compat: {
    supportsStore: false,
  }
};

// Use the custom model
const response = await stream(ollamaModel, context, {
  apiKey: 'dummy' // Ollama doesn't need a real key
});
```

## OpenAI Compatibility Settings

For OpenAI-compatible APIs, compatibility can be auto-detected or explicitly configured:

```typescript
interface OpenAICompletionsCompat {
  supportsStore?: boolean;
  supportsDeveloperRole?: boolean;
  supportsReasoningEffort?: boolean;
  supportsUsageInStreaming?: boolean;
  supportsStrictMode?: boolean;
  maxTokensField?: 'max_completion_tokens' | 'max_tokens';
  requiresToolResultName?: boolean;
  requiresAssistantAfterToolResult?: boolean;
  requiresThinkingAsText?: boolean;
  thinkingFormat?: 'openai' | 'zai' | 'qwen';
  openRouterRouting?: OpenRouterRouting;
  vercelGatewayRouting?: VercelGatewayRouting;
}
```

## Context Structure

```typescript
interface Context {
  systemPrompt?: string;
  messages: Message[];
  tools?: Tool[];
}

type Message = UserMessage | AssistantMessage | ToolResultMessage;

interface UserMessage {
  role: 'user';
  content: string | (TextContent | ImageContent)[];
  timestamp: number;
}

interface AssistantMessage {
  role: 'assistant';
  content: (TextContent | ThinkingContent | ToolCall)[];
  api: Api;
  provider: Provider;
  model: string;
  usage: Usage;
  stopReason: StopReason;
  errorMessage?: string;
  timestamp: number;
}

interface ToolResultMessage {
  role: 'toolResult';
  toolCallId: string;
  toolName: string;
  content: (TextContent | ImageContent)[];
  details?: any;
  isError: boolean;
  timestamp: number;
}
```

## Tool Definition

Tools use TypeBox for type-safe parameter schemas:

```typescript
import { Type, Tool, StringEnum } from '@mariozechner/pi-ai';

const weatherTool: Tool = {
  name: 'get_weather',
  description: 'Get current weather for a location',
  parameters: Type.Object({
    location: Type.String({ description: 'City name or coordinates' }),
    units: StringEnum(['celsius', 'fahrenheit'], { default: 'celsius' })
  })
};
```

## Streaming Events

| Event | Description |
|-------|-------------|
| `start` | Stream begins |
| `text_start` | Text block starts |
| `text_delta` | Text chunk received |
| `text_end` | Text block complete |
| `thinking_start` | Thinking block starts |
| `thinking_delta` | Thinking chunk received |
| `thinking_end` | Thinking block complete |
| `toolcall_start` | Tool call begins |
| `toolcall_delta` | Tool arguments streaming |
| `toolcall_end` | Tool call complete |
| `done` | Stream complete |
| `error` | Error occurred |

## Integration Patterns

### Basic Integration with Environment Variables

```typescript
import { getModel, complete, getEnvApiKey } from '@mariozechner/pi-ai';

// Check if API key is configured
const apiKey = getEnvApiKey('openai');
if (!apiKey) {
  throw new Error('OPENAI_API_KEY not set');
}

// Use model (automatically picks up environment key)
const model = getModel('openai', 'gpt-4o-mini');
const response = await complete(model, context);
```

### Custom Configuration with Explicit Options

```typescript
import { getModel, complete } from '@mariozechner/pi-ai';

const model = getModel('openai', 'gpt-4o-mini');

const response = await complete(model, context, {
  apiKey: process.env.CUSTOM_API_KEY,
  temperature: 0.7,
  maxTokens: 4096,
  headers: {
    'X-Custom-Header': 'value'
  }
});
```

### Error Handling

```typescript
const s = stream(model, context);

for await (const event of s) {
  if (event.type === 'error') {
    console.error('Error:', event.error.errorMessage);
    console.log('Partial content:', event.error.content);
  }
}

const message = await s.result();
if (message.stopReason === 'error' || message.stopReason === 'aborted') {
  console.error('Request failed:', message.errorMessage);
}
```

### AbortController Support

```typescript
const controller = new AbortController();
setTimeout(() => controller.abort(), 5000);

const response = await complete(model, context, {
  signal: controller.signal
});
```

## Browser Usage

```typescript
import { getModel, complete } from '@mariozechner/pi-ai';

// API key must be passed explicitly (no environment variables in browser)
const model = getModel('anthropic', 'claude-3-5-haiku-20241022');

const response = await complete(model, {
  messages: [{ role: 'user', content: 'Hello!' }]
}, {
  apiKey: 'your-api-key'
});
```

**Note:** Amazon Bedrock and OAuth flows are not supported in browser environments.

## OAuth Providers

Several providers require OAuth authentication:

```typescript
import { loginAnthropic, getOAuthApiKey } from '@mariozechner/pi-ai/oauth';

// Login to provider
const credentials = await loginAnthropic({
  onAuth: (url, instructions) => console.log(`Open: ${url}`),
  onPrompt: async (prompt) => await getUserInput(prompt.message),
  onProgress: (message) => console.log(message)
});

// Use credentials
const result = await getOAuthApiKey('anthropic', { anthropic: credentials });
const model = getModel('anthropic', 'claude-sonnet-4-20250514');
const response = await complete(model, context, { apiKey: result.apiKey });
```

## CLI Usage

```bash
# Interactive login
npx @mariozechner/pi-ai login

# Login to specific provider
npx @mariozechner/pi-ai login anthropic

# List available providers
npx @mariozechner/pi-ai list
```

## Key Files

```
packages/ai/src/
├── index.ts              # Main exports
├── types.ts              # Core type definitions
├── models.ts             # Model registry functions
├── stream.ts             # Streaming API
├── env-api-keys.ts       # Environment variable handling
├── api-registry.ts       # Provider registry
├── providers/            # Provider implementations
│   ├── anthropic.ts
│   ├── openai-responses.ts
│   ├── openai-completions.ts
│   ├── google.ts
│   └── ...
└── utils/                # Utilities
```

## Summary for Integration

For integrating with environment variable configuration:

1. **Use `getEnvApiKey(provider)`** to check/read API keys from environment
2. **Use `getModel(provider, modelId)`** to get a typed model reference
3. **Pass `apiKey` in options** to override environment variables
4. **Use `stream()` or `complete()`** for standard streaming/non-streaming
5. **Use `streamSimple()` or `completeSimple()`** for simplified reasoning support

The package automatically handles:
- Environment variable lookup
- Provider-specific authentication
- Token usage tracking
- Cost calculation
- Cross-provider context compatibility
