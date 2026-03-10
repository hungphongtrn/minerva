import {
  BadRequestException,
  Inject,
  Injectable,
  InternalServerErrorException,
  NotFoundException,
  ServiceUnavailableException,
} from '@nestjs/common';
import type {
  Agent as PiAgent,
  AgentEvent,
  AgentMessage as PiAgentMessage,
  AgentTool as PiAgentTool,
  AgentToolResult,
} from '@mariozechner/pi-agent-core';
import type { Message } from '@mariozechner/pi-ai';
import path from 'node:path';
import { ORCHESTRATOR_CONFIG } from '../config/config.constants.js';
import type { OrchestratorConfig } from '../config/types.js';
import { ModelProviderService } from '../model-provider/model-provider.service.js';
import { packLoader } from '../packs/loader.js';
import { systemPromptAssembler } from '../packs/assembler.js';
import { LOGGER, SANDBOX_ADAPTER } from '../providers/provider-tokens.js';
import type { ILogger } from '../providers/types.js';
import type { ISandboxAdapter } from '../sandbox/adapter.js';
import { SSEService } from '../sse/sse.service.js';
import { createToolRegistry } from '../tools/index.js';
import type { ToolContext, ToolEventEmitter } from '../tools/types.js';
import { RunManager } from '../services/run-manager.js';
import { RunState, type Run } from '../types/run.js';

export interface CreateRunRequestBody {
  agentPackId?: string;
  prompt?: string;
  userId?: string;
  maxDurationMs?: number;
}

export interface CancelRunRequestBody {
  reason?: string;
}

@Injectable()
export class RunExecutionService {
  private readonly processingUsers = new Set<string>();
  private readonly terminalEvents = new Set<string>();

  constructor(
    private readonly runManager: RunManager,
    private readonly sseService: SSEService,
    @Inject(SANDBOX_ADAPTER) private readonly sandboxAdapter: ISandboxAdapter,
    private readonly modelProviderService: ModelProviderService,
    @Inject(ORCHESTRATOR_CONFIG) private readonly config: OrchestratorConfig,
    @Inject(LOGGER) private readonly logger: ILogger
  ) {}

  async createRun(body: CreateRunRequestBody): Promise<Run> {
    const prompt = body.prompt?.trim();
    const agentPackId = body.agentPackId?.trim();
    const userId = body.userId?.trim() || 'anonymous';

    if (!prompt) {
      throw new BadRequestException('prompt is required');
    }

    if (!agentPackId) {
      throw new BadRequestException('agentPackId is required');
    }

    const run = await this.runManager.createRun({
      userId,
      agentPackId,
      prompt,
      maxDurationMs: body.maxDurationMs,
    });

    this.sseService.broadcastOrchestratorEvent(run.id, 'run_queued', {
      queue_position: run.queuePosition ?? 0,
    });

    void this.processUserQueue(userId);

    return run;
  }

  async getRun(runId: string): Promise<Run> {
    const run = await this.runManager.getRun(runId);
    if (!run) {
      throw new NotFoundException(`Run '${runId}' not found`);
    }

    return run;
  }

  async cancelRun(runId: string, body?: CancelRunRequestBody): Promise<Run> {
    const existing = await this.runManager.getRun(runId);
    if (!existing) {
      throw new NotFoundException(`Run '${runId}' not found`);
    }

    const cancelled = await this.runManager.cancelRun(runId, body?.reason);

    if (cancelled.state === RunState.CANCELLED) {
      this.emitTerminalOnce(cancelled.id, 'run_cancelled', {
        cancelled_at: cancelled.completedAt?.toISOString() ?? new Date().toISOString(),
        reason: body?.reason ?? 'cancelled',
      });
    }

    return cancelled;
  }

  private async processUserQueue(userId: string): Promise<void> {
    if (this.processingUsers.has(userId)) {
      return;
    }

    this.processingUsers.add(userId);

    try {
      for (;;) {
        const nextRun = await this.runManager.acquireNextRun(userId);
        if (!nextRun) {
          break;
        }

        await this.executeRun(nextRun);
      }
    } finally {
      this.processingUsers.delete(userId);
    }
  }

  private async executeRun(run: Run): Promise<void> {
    this.logger.info('Executing run', { runId: run.id, userId: run.userId });

    let workspaceId: string | undefined;
    let agent: PiAgent | undefined;
    let abortListenerInstalled = false;

    try {
      // Check provider health before starting
      const providerHealth = await this.modelProviderService.checkHealth();
      if (!providerHealth.healthy) {
        this.logger.error('Provider health check failed', undefined, {
          runId: run.id,
          provider: providerHealth.provider,
          error: providerHealth.error,
        });
        throw new ServiceUnavailableException(
          `Provider ${providerHealth.provider} is not available: ${providerHealth.error}`
        );
      }

      const { Agent } = await import('@mariozechner/pi-agent-core');

      const workspace = await this.sandboxAdapter.getOrCreateWorkspace(
        run.userId,
        this.config.sandbox.strategy
      );
      workspaceId = workspace.id;

      const startedRun = await this.runManager.startRun(run.id);
      this.sseService.broadcastOrchestratorEvent(run.id, 'run_started', {
        started_at: startedRun.startedAt?.toISOString() ?? new Date().toISOString(),
        sandbox_id: workspace.id,
      });

      const signal = this.runManager.getCancellationSignal(run.id);
      const packPath = this.resolvePackPath(run.agentPackId);
      const pack = await packLoader.load(packPath);
      const systemPrompt = systemPromptAssembler.assemble(pack).fullPrompt;
      const tools = this.createPiAgentTools({
        runId: run.id,
        userId: run.userId,
        workspaceId: workspace.id,
      });

      // Get model and stream function from model provider service
      const model = this.modelProviderService.getModel();
      const streamFn = this.modelProviderService.createStreamFn();

      agent = new Agent({
        initialState: {
          systemPrompt,
          model,
          tools,
          messages: [],
          thinkingLevel: 'minimal',
        },
        convertToLlm: (messages) => this.filterLlmMessages(messages),
        streamFn,
      });

      const unsubscribe = agent.subscribe((event: AgentEvent) => {
        this.sseService.broadcastAgentEvent(run.id, event as unknown as { type: string; [key: string]: unknown });
      });

      if (signal) {
        signal.addEventListener(
          'abort',
          () => {
            agent?.abort();
            const reason = String(signal.reason ?? 'cancelled');

            if (reason === 'timeout') {
              this.emitTerminalOnce(run.id, 'run_timed_out', {
                timed_out_at: new Date().toISOString(),
                timeout_duration_ms: run.maxDurationMs,
              });
            } else {
              this.emitTerminalOnce(run.id, 'run_cancelled', {
                cancelled_at: new Date().toISOString(),
                reason,
              });
            }
          },
          { once: true }
        );
        abortListenerInstalled = true;
      }

      await agent.prompt(run.prompt);
      unsubscribe();

      const latestRun = await this.runManager.getRun(run.id);
      if (!latestRun) {
        throw new InternalServerErrorException(`Run '${run.id}' disappeared during execution`);
      }

      if (latestRun.state === RunState.CANCELLED || latestRun.state === RunState.TIMED_OUT) {
        this.sseService.closeRun(run.id);
        this.terminalEvents.delete(run.id);
        return;
      }

      const completedRun = await this.runManager.completeRun(
        run.id,
        agent.state.messages as unknown[]
      );
      this.emitTerminalOnce(run.id, 'run_completed', {
        completed_at: completedRun.completedAt?.toISOString() ?? new Date().toISOString(),
        duration_ms: this.computeDurationMs(completedRun),
      });
      this.sseService.closeRun(run.id);
      this.terminalEvents.delete(run.id);
    } catch (error) {
      const latestRun = await this.runManager.getRun(run.id);
      if (latestRun && latestRun.state !== RunState.CANCELLED && latestRun.state !== RunState.TIMED_OUT) {
        // Enhanced error handling for provider-specific errors
        const enhancedError = this.enhanceProviderError(error);

        const failedRun = await this.runManager.failRun(
          run.id,
          enhancedError
        );
        this.emitTerminalOnce(run.id, 'run_failed', {
          failed_at: failedRun.completedAt?.toISOString() ?? new Date().toISOString(),
          error: failedRun.error ?? 'Unknown execution failure',
        });
        this.sseService.closeRun(run.id);
      }

      this.terminalEvents.delete(run.id);
      this.logger.error('Run execution failed', error instanceof Error ? error : undefined, {
        runId: run.id,
        workspaceId,
      });
    } finally {
      if (!abortListenerInstalled && agent) {
        agent.abort();
      }
    }
  }

  /**
   * Enhances provider errors with descriptive messages for common error types.
   */
  private enhanceProviderError(error: unknown): Error {
    if (!(error instanceof Error)) {
      return new Error(String(error));
    }

    const message = error.message.toLowerCase();

    // Rate limit errors
    if (message.includes('rate limit') || message.includes('too many requests') || message.includes('429')) {
      return new Error(`Rate limit exceeded. Please wait before retrying. Original error: ${error.message}`);
    }

    // Authentication errors
    if (message.includes('authentication') || message.includes('unauthorized') || message.includes('401') ||
        message.includes('invalid api key') || message.includes('api key invalid')) {
      return new Error(`Authentication failed. Please check your API key configuration. Original error: ${error.message}`);
    }

    // Timeout errors
    if (message.includes('timeout') || message.includes('etimedout') || message.includes('econnreset')) {
      return new Error(`Request timed out. The provider may be experiencing high load or the request may be too large. Original error: ${error.message}`);
    }

    // Quota exceeded errors
    if (message.includes('quota') || message.includes('exceeded') || message.includes('billing')) {
      return new Error(`API quota exceeded. Please check your billing and usage limits. Original error: ${error.message}`);
    }

    // Return original error with provider context
    return error;
  }

  private resolvePackPath(agentPackId: string): string {
    return path.isAbsolute(agentPackId)
      ? agentPackId
      : path.resolve(process.cwd(), this.config.packs.basePath, agentPackId);
  }

  private filterLlmMessages(messages: PiAgentMessage[]): Message[] {
    return messages.filter((message): message is Message => {
      if (!message || typeof message !== 'object' || !('role' in message)) {
        return false;
      }

      return message.role === 'user' || message.role === 'assistant' || message.role === 'toolResult';
    });
  }

  private createPiAgentTools(context: ToolContext): PiAgentTool[] {
    const registry = createToolRegistry(this.sandboxAdapter);

    return registry.getAllTools().map((tool) => ({
      name: tool.name,
      label: tool.label,
      description: tool.description,
      parameters: tool.parameters,
      execute: async (toolCallId, params, signal, onUpdate): Promise<AgentToolResult<unknown>> => {
        const eventEmitter: ToolEventEmitter = {
          emitStart: () => {},
          emitUpdate: (_id, _name, partialResult) => {
            onUpdate?.(partialResult as never);
          },
          emitEnd: () => {},
        };

        const result = await tool.execute(toolCallId, params, signal ?? new AbortController().signal, eventEmitter, context);

        if (result.success) {
          return {
            content: [{ type: 'text', text: JSON.stringify(result.data ?? null, null, 2) }],
            details: result.data,
          };
        }

        return {
          content: [{ type: 'text', text: result.error?.message ?? 'Unknown tool error' }],
          details: result.error,
        };
      },
    }));
  }

  private emitTerminalOnce(
    runId: string,
    eventType: 'run_completed' | 'run_failed' | 'run_cancelled' | 'run_timed_out',
    payload: Record<string, unknown>
  ): void {
    if (this.terminalEvents.has(runId)) {
      return;
    }

    this.terminalEvents.add(runId);
    this.sseService.broadcastOrchestratorEvent(runId, eventType, payload);
  }

  private computeDurationMs(run: Run): number {
    if (!run.startedAt || !run.completedAt) {
      return 0;
    }

    return run.completedAt.getTime() - run.startedAt.getTime();
  }
}
