import { Module } from '@nestjs/common';
import { HealthController } from './health.controller.js';
import { ModelProviderModule } from '../model-provider/model-provider.module.js';

@Module({
  imports: [ModelProviderModule],
  controllers: [HealthController],
})
export class HealthModule {}
