import { Module } from '@nestjs/common';
import { GatewayAuthGuard } from './gateway-auth.guard.js';
import { GatewayAuthService } from './gateway-auth.service.js';

@Module({
  providers: [GatewayAuthService, GatewayAuthGuard],
  exports: [GatewayAuthService, GatewayAuthGuard],
})
export class AuthModule {}
