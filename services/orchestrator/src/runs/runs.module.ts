import { Module } from '@nestjs/common';
import { RuntimeModule } from '../runtime/runtime.module.js';
import { RunsController } from './runs.controller.js';

@Module({
  imports: [RuntimeModule],
  controllers: [RunsController],
})
export class RunsModule {}
