import {
  Body,
  Controller,
  Get,
  HttpCode,
  Param,
  Post,
} from '@nestjs/common';
import {
  RunExecutionService,
  type CancelRunRequestBody,
  type CreateRunRequestBody,
} from '../runtime/run-execution.service.js';
import { type Run } from '../types/run.js';

@Controller('api/v0/runs')
export class RunsController {
  constructor(private readonly runExecutionService: RunExecutionService) {}

  @Post()
  async createRun(@Body() body: CreateRunRequestBody): Promise<Record<string, unknown>> {
    const run = await this.runExecutionService.createRun(body);

    return {
      runId: run.id,
      state: run.state,
      createdAt: run.createdAt.toISOString(),
      queuePosition: run.queuePosition ?? null,
      userId: run.userId,
    };
  }

  @Get(':runId')
  async getRun(@Param('runId') runId: string): Promise<Record<string, unknown>> {
    const run = await this.runExecutionService.getRun(runId);

    return this.toRunResponse(run);
  }

  @Post(':runId/cancel')
  @HttpCode(200)
  async cancelRun(
    @Param('runId') runId: string,
    @Body() body: CancelRunRequestBody
  ): Promise<Record<string, unknown>> {
    const run = await this.runExecutionService.cancelRun(runId, body);

    return {
      runId: run.id,
      state: run.state,
      cancelledAt: run.completedAt?.toISOString() ?? null,
      reason: body?.reason ?? run.error ?? 'cancelled',
    };
  }

  private toRunResponse(run: Run): Record<string, unknown> {
    const now = Date.now();
    const durationMs = run.startedAt
      ? (run.completedAt?.getTime() ?? now) - run.startedAt.getTime()
      : 0;

    return {
      runId: run.id,
      userId: run.userId,
      state: run.state,
      createdAt: run.createdAt.toISOString(),
      startedAt: run.startedAt?.toISOString() ?? null,
      completedAt: run.completedAt?.toISOString() ?? null,
      queuePosition: run.queuePosition ?? null,
      error: run.error ?? null,
      durationMs,
    };
  }
}
