import { Module } from '@nestjs/common';
import type { StreamFn } from '@mariozechner/pi-agent-core';
import { ORCHESTRATOR_CONFIG } from '../config/config.constants.js';
import type { OrchestratorConfig } from '../config/types.js';
import { SANDBOX_ADAPTER, AGENT_STREAM_FN } from '../providers/provider-tokens.js';
import { DaytonaSandboxAdapter, type ISandboxAdapter } from '../sandbox/adapter.js';
import { DaytonaClient } from '../sandbox/daytona-client.js';
import { ExecutionService } from '../sandbox/execution.js';
import { FilesystemService } from '../sandbox/filesystem.js';
import { NetworkValidationService } from '../sandbox/network.js';
import { WorkspaceManager } from '../sandbox/workspace-manager.js';
import { RunManager } from '../services/run-manager.js';
import { SSEService } from '../sse/sse.service.js';
import { RunExecutionService } from './run-execution.service.js';

@Module({
  providers: [
    RunManager,
    SSEService,
    {
      provide: SANDBOX_ADAPTER,
      inject: [ORCHESTRATOR_CONFIG],
      useFactory: (config: OrchestratorConfig): ISandboxAdapter => {
        let adapter: DaytonaSandboxAdapter | undefined;

        const getAdapter = (): DaytonaSandboxAdapter => {
          if (!adapter) {
            const client = new DaytonaClient(config.daytona);
            const workspaceManager = new WorkspaceManager(client, {
              strategy: config.sandbox.strategy,
              workspaceConfig: config.sandbox.workspace,
            });
            const executionService = new ExecutionService();
            const filesystemService = new FilesystemService(client, config.sandbox.security.maxFileSize);
            const networkService = new NetworkValidationService(client);

            adapter = new DaytonaSandboxAdapter(
              client,
              workspaceManager,
              executionService,
              filesystemService,
              networkService
            );
          }

          return adapter;
        };

        return {
          async getOrCreateWorkspace(userId, strategy) {
            return getAdapter().getOrCreateWorkspace(userId, strategy);
          },
          async destroyWorkspace(workspaceId) {
            return getAdapter().destroyWorkspace(workspaceId);
          },
          execute(workspaceId, command, options) {
            return getAdapter().execute(workspaceId, command, options);
          },
          async readFile(workspaceId, path, options) {
            return getAdapter().readFile(workspaceId, path, options);
          },
          async writeFile(workspaceId, path, content, options) {
            return getAdapter().writeFile(workspaceId, path, content, options);
          },
          async validateNetworkIsolation(workspaceId) {
            return getAdapter().validateNetworkIsolation(workspaceId);
          },
        };
      },
    },
    {
      provide: AGENT_STREAM_FN,
      useFactory: (): StreamFn => {
        return async (model, context) => {
          const { scriptedStream } = await import('./scripted-stream.js');
          return scriptedStream(model as Parameters<typeof scriptedStream>[0], context);
        };
      },
    },
    RunExecutionService,
  ],
  exports: [RunManager, SSEService, RunExecutionService, SANDBOX_ADAPTER, AGENT_STREAM_FN],
})
export class RuntimeModule {}
