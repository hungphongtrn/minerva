import { CanActivate, ExecutionContext, Injectable } from '@nestjs/common';
import {
  AUTHENTICATED_OWNER_REQUEST_KEY,
  type GatewayAuthenticatedRequest,
} from './authenticated-owner.decorator.js';
import { GatewayAuthService } from './gateway-auth.service.js';

@Injectable()
export class GatewayAuthGuard implements CanActivate {
  constructor(private readonly gatewayAuthService: GatewayAuthService) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest<GatewayAuthenticatedRequest>();
    request[AUTHENTICATED_OWNER_REQUEST_KEY] = this.gatewayAuthService.authenticate(request.headers);
    return true;
  }
}
