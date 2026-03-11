import {
  Controller,
  Body,
  Get,
  HttpCode,
  Param,
  Post,
  UseGuards,
} from '@nestjs/common';
import { AuthenticatedOwner } from '../auth/authenticated-owner.decorator.js';
import { GatewayAuthGuard } from '../auth/gateway-auth.guard.js';
import {
  RunExecutionService,
  type CancelRunRequestBody,
  type CreateRunRequestBody,
} from '../runtime/run-execution.service.js';
import type { OwnerPrincipal } from '../types/owner.js';
import { type Run } from '../types/run.js';

@Controller('api/v0/runs')
@UseGuards(GatewayAuthGuard)
export class RunsController {
  constructor(private readonly runExecutionService: RunExecutionService) {}

  @Post()
  async createRun(
    @AuthenticatedOwner() owner: OwnerPrincipal,
    @Body() body: CreateRunRequestBody
  ): Promise<Record<string, unknown>> {
    const run = await this.runExecutionService.createRun(owner, body);

    return {
      runId: run.id,
      state: run.state,
      createdAt: run.createdAt.toISOString(),
      queuePosition: run.queuePosition ?? null,
      tenantId: run.owner.tenantId,
      subjectId: run.owner.subjectId,
    };
  }

  @Get(':runId')
  async getRun(
    @Param('runId') runId: string,
    @AuthenticatedOwner() owner: OwnerPrincipal
  ): Promise<Record<string, unknown>> {
    const run = await this.runExecutionService.getRun(runId, owner);

    return this.toRunResponse(run);
  }

  @Post(':runId/cancel')
  @HttpCode(200)
  async cancelRun(
    @Param('runId') runId: string,
    @AuthenticatedOwner() owner: OwnerPrincipal,
    @Body() body: CancelRunRequestBody
  ): Promise<Record<string, unknown>> {
    const run = await this.runExecutionService.cancelRun(runId, owner, body);

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
      tenantId: run.owner.tenantId,
      subjectId: run.owner.subjectId,
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
