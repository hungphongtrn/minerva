/**
 * SSE Controller
 *
 * HTTP endpoint for run event streaming.
 * GET /api/v0/runs/:runId/stream
 */

import {
  Controller,
  Get,
  Param,
  Query,
  Req,
  Res,
  Headers,
  NotFoundException,
  Logger,
} from '@nestjs/common';
import type { Request, Response } from 'express';
import { SSEService } from './sse.service.js';
import { RunManager } from '../services/run-manager.js';
import type { SSEStream } from './stream.js';
import { isTerminalState } from '../types/run.js';

@Controller('api/v0/runs')
export class SSEController {
  private readonly logger = new Logger(SSEController.name);
  private readonly keepAliveIntervalMs = 30000;

  constructor(
    private readonly sseService: SSEService,
    private readonly runManager: RunManager
  ) {}

  @Get(':runId/stream')
  async streamEvents(
    @Param('runId') runId: string,
    @Query('replayFrom') replayFrom: string | undefined,
    @Headers('last-event-id') lastEventId: string | undefined,
    @Req() req: Request,
    @Res() res: Response
  ): Promise<void> {
    // Validate run exists
    const run = await this.runManager.getRun(runId);
    if (!run) {
      throw new NotFoundException(`Run ${runId} not found`);
    }

    // Get replay position from header or query
    const startSeqStr = replayFrom ?? lastEventId;
    const startSeq = startSeqStr ? parseInt(startSeqStr, 10) : null;

    // Set SSE headers
    res.set({
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no', // Disable nginx buffering
    });

    // Create SSE stream wrapper
    const stream: SSEStream = {
      write: (event) => {
        const data = JSON.stringify(event);
        res.write(`id: ${event.seq}\n`);
        res.write(`event: ${event.type}\n`);
        res.write(`data: ${data}\n\n`);
      },
      close: () => {
        res.end();
      },
      isOpen: () => {
        return !res.writableEnded;
      },
      getClientInfo: () => ({
        ip: req.ip ?? 'unknown',
        userAgent: req.headers['user-agent'],
      }),
    };

    // Register stream
    const cleanup = this.sseService.registerStream(runId, stream);

    // Replay buffered events if requested
    if (startSeq !== null && !isNaN(startSeq)) {
      const bufferedEvents = this.sseService.getBufferedEventsFrom(startSeq);
      for (const event of bufferedEvents) {
        stream.write(event);
      }
    }

    // Send initial connection event
    const connectedEvent = this.sseService.createEnvelope(runId, 'stream_connected', {
      run_state: run.state,
      replay_from: startSeq,
    });
    stream.write(connectedEvent);

    // Keep-alive timer
    const keepAliveTimer = setInterval(() => {
      if (stream.isOpen()) {
        res.write(':keepalive\n\n');
      } else {
        clearInterval(keepAliveTimer);
      }
    }, this.keepAliveIntervalMs);

    // Handle client disconnect
    req.on('close', () => {
      clearInterval(keepAliveTimer);
      clearInterval(checkRunState);
      cleanup();
      this.logger.debug(`Client disconnected from run ${runId}`);
    });

    // Handle run completion - close stream when run reaches terminal state
    const checkRunState = setInterval(() => {
      void (async () => {
        try {
          const currentRun = await this.runManager.getRun(runId);
          if (currentRun && isTerminalState(currentRun.state)) {
            clearInterval(checkRunState);
            clearInterval(keepAliveTimer);
            cleanup();
            this.logger.debug(`Closing stream for run ${runId} - reached terminal state: ${currentRun.state}`);
          }
        } catch (error) {
          this.logger.error(`Error checking run state for ${runId}:`, error);
        }
      })();
    }, 1000);

    // Note: We don't await - the connection stays open until cleanup
  }
}
