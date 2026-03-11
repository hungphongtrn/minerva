/**
 * SSE Module
 *
 * NestJS module for Server-Sent Events functionality.
 */

import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module.js';
import { SSEController } from './sse.controller.js';
import { RuntimeModule } from '../runtime/runtime.module.js';

@Module({
  imports: [AuthModule, RuntimeModule],
  controllers: [SSEController],
})
export class SSEModule {}
