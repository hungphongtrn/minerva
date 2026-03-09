# Tools

Tools allow agents to perform actions and access external systems. The pi-agent-core SDK provides a type-safe tool system using JSON Schema validation.

## Tool Definition

```typescript
import { Type } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";

const readFileTool: AgentTool = {
  name: "read_file",
  label: "Read File",           // Human-readable name for UI
  description: "Read a file's contents",
  parameters: Type.Object({
    path: Type.String({ 
      description: "File path to read" 
    }),
    encoding: Type.Optional(
      Type.String({ 
        description: "File encoding",
        default: "utf-8"
      })
    ),
  }),
  execute: async (toolCallId, params, signal, onUpdate) => {
    const content = await fs.readFile(params.path, params.encoding || "utf-8");
    
    return {
      content: [{ type: "text", text: content }],
      details: { 
        path: params.path, 
        size: content.length 
      },
    };
  },
};
```

## Tool Structure

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | `string` | Yes | Unique identifier (kebab-case recommended) |
| `label` | `string` | Yes | Human-readable display name |
| `description` | `string` | Yes | Description for the LLM |
| `parameters` | `TSchema` | Yes | JSON Schema for validation |
| `execute` | `function` | Yes | Async execution function |

## Execute Function

```typescript
execute: (
  toolCallId: string,                    // Unique ID for this call
  params: Static<TParameters>,           // Validated parameters
  signal?: AbortSignal,                  // Cancellation signal
  onUpdate?: AgentToolUpdateCallback<T>  // Optional progress callback
) => Promise<AgentToolResult<T>>
```

### Return Value

```typescript
interface AgentToolResult<T> {
  content: (TextContent | ImageContent)[];  // Content for LLM
  details: T;                                // Additional data for UI/logs
}
```

## Parameter Validation

Use `@sinclair/typebox` for type-safe JSON Schema:

```typescript
import { Type } from "@sinclair/typebox";

const searchTool: AgentTool = {
  name: "search",
  label: "Search",
  description: "Search for documents",
  parameters: Type.Object({
    query: Type.String({ description: "Search query" }),
    limit: Type.Optional(
      Type.Number({ 
        description: "Max results",
        minimum: 1,
        maximum: 100,
        default: 10
      })
    ),
    filters: Type.Optional(
      Type.Object({
        dateFrom: Type.Optional(Type.String()),
        dateTo: Type.Optional(Type.String()),
        tags: Type.Optional(Type.Array(Type.String())),
      })
    ),
  }),
  // ...
};
```

## Error Handling

**Always throw errors** for failures. Don't return error messages as content.

```typescript
execute: async (toolCallId, params, signal, onUpdate) => {
  // Good: Throw on error
  if (!fs.existsSync(params.path)) {
    throw new Error(`File not found: ${params.path}`);
  }
  
  // Good: Throw on validation
  if (params.limit > 1000) {
    throw new Error("Limit cannot exceed 1000");
  }
  
  // Process...
  return { content: [...], details: {...} };
}
```

The agent catches errors and reports them to the LLM with `isError: true`.

## Streaming Tool Execution

For long-running operations, stream progress updates:

```typescript
const downloadTool: AgentTool = {
  name: "download",
  label: "Download File",
  description: "Download a file with progress",
  parameters: Type.Object({
    url: Type.String(),
  }),
  execute: async (toolCallId, params, signal, onUpdate) => {
    const response = await fetch(params.url);
    const totalSize = parseInt(response.headers.get('content-length') || '0');
    let downloaded = 0;
    
    const reader = response.body?.getReader();
    const chunks: Uint8Array[] = [];
    
    while (true) {
      if (signal?.aborted) {
        throw new Error("Download cancelled");
      }
      
      const { done, value } = await reader!.read();
      if (done) break;
      
      chunks.push(value);
      downloaded += value.length;
      
      // Stream progress update
      onUpdate?.({
        content: [{ 
          type: "text", 
          text: `Downloaded ${downloaded} of ${totalSize} bytes` 
        }],
        details: { downloaded, totalSize, percent: (downloaded / totalSize) * 100 },
      });
    }
    
    // Combine chunks and save...
    return {
      content: [{ type: "text", text: `Downloaded ${downloaded} bytes` }],
      details: { url: params.url, size: downloaded },
    };
  },
};
```

## Cancellation Support

Check the abort signal for user cancellations:

```typescript
execute: async (toolCallId, params, signal, onUpdate) => {
  for (const item of largeDataset) {
    // Check for cancellation
    if (signal?.aborted) {
      throw new Error("Operation cancelled by user");
    }
    
    // Process item...
    await process(item);
  }
  
  return { content: [...], details: {...} };
}
```

## Registering Tools

```typescript
const agent = new Agent({
  initialState: {
    tools: [readFileTool, searchTool, downloadTool],
  },
});

// Or dynamically
agent.setTools([readFileTool, searchTool]);
```

## Tool Examples

### File Operations

```typescript
const fileTools: AgentTool[] = [
  {
    name: "read_file",
    label: "Read File",
    description: "Read file contents",
    parameters: Type.Object({
      path: Type.String(),
    }),
    execute: async (id, params) => {
      const content = await fs.readFile(params.path, "utf-8");
      return {
        content: [{ type: "text", text: content }],
        details: { path: params.path },
      };
    },
  },
  {
    name: "write_file",
    label: "Write File",
    description: "Write content to a file",
    parameters: Type.Object({
      path: Type.String(),
      content: Type.String(),
    }),
    execute: async (id, params) => {
      await fs.writeFile(params.path, params.content);
      return {
        content: [{ type: "text", text: "File written successfully" }],
        details: { path: params.path, size: params.content.length },
      };
    },
  },
];
```

### HTTP Requests

```typescript
const fetchTool: AgentTool = {
  name: "fetch",
  label: "Fetch URL",
  description: "Make HTTP requests",
  parameters: Type.Object({
    url: Type.String(),
    method: Type.Optional(
      Type.Union([Type.Literal("GET"), Type.Literal("POST")])
    ),
    headers: Type.Optional(Type.Record(Type.String(), Type.String())),
    body: Type.Optional(Type.String()),
  }),
  execute: async (id, params, signal) => {
    const response = await fetch(params.url, {
      method: params.method || "GET",
      headers: params.headers,
      body: params.body,
      signal,
    });
    
    const text = await response.text();
    
    return {
      content: [{ type: "text", text }],
      details: { 
        status: response.status,
        statusText: response.statusText,
        headers: Object.fromEntries(response.headers),
      },
    };
  },
};
```

### Database Query

```typescript
const queryTool: AgentTool = {
  name: "query_database",
  label: "Query Database",
  description: "Execute a database query",
  parameters: Type.Object({
    sql: Type.String({ description: "SQL query" }),
    params: Type.Optional(Type.Array(Type.Any())),
  }),
  execute: async (id, params) => {
    const result = await db.query(params.sql, params.params || []);
    
    return {
      content: [{ 
        type: "text", 
        text: JSON.stringify(result.rows, null, 2) 
      }],
      details: { 
        rowCount: result.rowCount,
        columns: result.columns,
      },
    };
  },
};
```

### Image Generation

```typescript
const generateImageTool: AgentTool = {
  name: "generate_image",
  label: "Generate Image",
  description: "Generate an image from a description",
  parameters: Type.Object({
    prompt: Type.String({ description: "Image description" }),
    size: Type.Optional(
      Type.Union([
        Type.Literal("256x256"),
        Type.Literal("512x512"),
        Type.Literal("1024x1024"),
      ])
    ),
  }),
  execute: async (id, params) => {
    const imageData = await imageGenerator.generate(params.prompt, {
      size: params.size || "1024x1024",
    });
    
    return {
      content: [
        { type: "text", text: "Image generated successfully" },
        { type: "image", data: imageData.base64, mimeType: "image/png" },
      ],
      details: { size: params.size, prompt: params.prompt },
    };
  },
};
```

## Best Practices

1. **Use descriptive names**: `read_file` not `read`
2. **Clear descriptions**: Help the LLM understand when to use the tool
3. **Validate parameters**: Use strict TypeBox schemas
4. **Throw on errors**: Don't return error content
5. **Stream progress**: For long operations, use `onUpdate`
6. **Handle cancellation**: Check `signal?.aborted`
7. **Return details**: Include metadata for UI display
8. **Keep it focused**: One tool should do one thing well
