import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module.js';
import { RuntimeModule } from '../runtime/runtime.module.js';
import { RunsController } from './runs.controller.js';

@Module({
  imports: [AuthModule, RuntimeModule],
  controllers: [RunsController],
})
export class RunsModule {}
