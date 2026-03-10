import type {
  AssistantMessage,
  AssistantMessageEventStream,
  Context,
  Message,
  Model,
  ToolCall,
} from '@mariozechner/pi-ai';
import { createAssistantMessageEventStream } from '@mariozechner/pi-ai';

const SCRIPTED_MODEL: Model<'openai-completions'> = {
  id: 'scripted-minerva-v0',
  name: 'Scripted Minerva v0',
  api: 'openai-completions',
  provider: 'openai',
  baseUrl: 'https://example.test/scripted',
  reasoning: false,
  input: ['text'],
  cost: {
    input: 0,
    output: 0,
    cacheRead: 0,
    cacheWrite: 0,
  },
  contextWindow: 128000,
  maxTokens: 8192,
};

type ScriptedRequest =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; toolCall: ToolCall };

export function getScriptedModel(): Model<'openai-completions'> {
  return SCRIPTED_MODEL;
}

export function scriptedStream(
  model: Model<'openai-completions'>,
  context: Context
): AssistantMessageEventStream {
  const stream = createAssistantMessageEventStream();

  void (() => {
    try {
      const request = createScriptedRequest(context.messages);

      if (request.kind === 'tool') {
        const message = createAssistantMessage(model, [request.toolCall], 'toolUse');
        stream.push({ type: 'start', partial: cloneAssistantMessage(message) });
        stream.push({
          type: 'toolcall_start',
          contentIndex: 0,
          partial: cloneAssistantMessage(message),
        });
        stream.push({
          type: 'toolcall_delta',
          contentIndex: 0,
          delta: JSON.stringify(request.toolCall.arguments),
          partial: cloneAssistantMessage(message),
        });
        stream.push({
          type: 'toolcall_end',
          contentIndex: 0,
          toolCall: request.toolCall,
          partial: cloneAssistantMessage(message),
        });
        stream.push({ type: 'done', reason: 'toolUse', message });
        return;
      }

      const finalMessage = createAssistantMessage(
        model,
        [{ type: 'text', text: request.text }],
        'stop'
      );

      stream.push({ type: 'start', partial: createAssistantMessage(model, [], 'stop') });

      let partialText = '';
      for (let index = 0; index < request.text.length; index += 12) {
        const delta = request.text.slice(index, index + 12);
        if (partialText.length === 0) {
          partialText = delta;
          stream.push({
            type: 'text_start',
            contentIndex: 0,
            partial: createAssistantMessage(model, [{ type: 'text', text: partialText }], 'stop'),
          });
        } else {
          partialText += delta;
        }

        stream.push({
          type: 'text_delta',
          contentIndex: 0,
          delta,
          partial: createAssistantMessage(model, [{ type: 'text', text: partialText }], 'stop'),
        });
      }

      stream.push({
        type: 'text_end',
        contentIndex: 0,
        content: request.text,
        partial: cloneAssistantMessage(finalMessage),
      });
      stream.push({ type: 'done', reason: 'stop', message: finalMessage });
    } catch (error) {
      const message = createAssistantMessage(
        model,
        [{ type: 'text', text: error instanceof Error ? error.message : String(error) }],
        'error',
        error instanceof Error ? error.message : String(error)
      );
      stream.push({ type: 'error', reason: 'error', error: message });
    }
  })();

  return stream;
}

function createScriptedRequest(messages: Message[]): ScriptedRequest {
  const lastMessage = messages[messages.length - 1];

  if (!lastMessage) {
    return { kind: 'text', text: 'No input provided.' };
  }

  if (lastMessage.role === 'toolResult') {
    const text = lastMessage.content
      .filter((item) => item.type === 'text')
      .map((item) => item.text)
      .join('')
      .trim();

    return {
      kind: 'text',
      text: lastMessage.isError
        ? `The ${lastMessage.toolName} tool returned an error: ${text || 'unknown error'}`
        : `The ${lastMessage.toolName} tool completed successfully. Output:\n${text || '(no text output)'}`,
    };
  }

  if (lastMessage.role !== 'user') {
    return { kind: 'text', text: 'Unsupported message type for scripted runtime.' };
  }

  const prompt = getMessageText(lastMessage).trim();
  const bashMatch = prompt.match(/^tool:bash\s+([\s\S]+)$/i);
  if (bashMatch) {
    return {
      kind: 'tool',
      toolCall: {
        type: 'toolCall',
        id: `toolcall_${Date.now()}`,
        name: 'bash',
        arguments: { command: bashMatch[1].trim() },
      },
    };
  }

  const readMatch = prompt.match(/^tool:read\s+(.+)$/i);
  if (readMatch) {
    return {
      kind: 'tool',
      toolCall: {
        type: 'toolCall',
        id: `toolcall_${Date.now()}`,
        name: 'read',
        arguments: { path: readMatch[1].trim() },
      },
    };
  }

  const writeMatch = prompt.match(/^tool:write\s+(\S+)\s+([\s\S]+)$/i);
  if (writeMatch) {
    return {
      kind: 'tool',
      toolCall: {
        type: 'toolCall',
        id: `toolcall_${Date.now()}`,
        name: 'write',
        arguments: { path: writeMatch[1].trim(), content: writeMatch[2] },
      },
    };
  }

  return {
    kind: 'text',
    text: `Received prompt: ${prompt}`,
  };
}

function getMessageText(message: Message): string {
  if (typeof message.content === 'string') {
    return message.content;
  }

  return message.content
    .filter((item) => item.type === 'text')
    .map((item) => item.text)
    .join('');
}

function createAssistantMessage(
  model: Model<'openai-completions'>,
  content: AssistantMessage['content'],
  stopReason: AssistantMessage['stopReason'],
  errorMessage?: string
): AssistantMessage {
  return {
    role: 'assistant',
    content,
    api: model.api,
    provider: model.provider,
    model: model.id,
    usage: {
      input: 0,
      output: 0,
      cacheRead: 0,
      cacheWrite: 0,
      totalTokens: 0,
      cost: {
        input: 0,
        output: 0,
        cacheRead: 0,
        cacheWrite: 0,
        total: 0,
      },
    },
    stopReason,
    errorMessage,
    timestamp: Date.now(),
  };
}

function cloneAssistantMessage(message: AssistantMessage): AssistantMessage {
  return {
    ...message,
    content: message.content.map((item) => {
      if (item.type === 'text') {
        return { ...item };
      }
      if (item.type === 'thinking') {
        return { ...item };
      }
      return {
        ...item,
        arguments: { ...item.arguments },
      };
    }),
    usage: {
      ...message.usage,
      cost: { ...message.usage.cost },
    },
  };
}
