import { createParamDecorator, ExecutionContext, UnauthorizedException } from '@nestjs/common';
import type { Request } from 'express';
import type { OwnerPrincipal } from '../types/owner.js';

export const AUTHENTICATED_OWNER_REQUEST_KEY = 'authenticatedOwner';

export type GatewayAuthenticatedRequest = Request & {
  authenticatedOwner?: OwnerPrincipal;
};

export const AuthenticatedOwner = createParamDecorator(
  (_data: unknown, context: ExecutionContext): OwnerPrincipal => {
    const request = context.switchToHttp().getRequest<GatewayAuthenticatedRequest>();
    const owner = request.authenticatedOwner;

    if (!owner) {
      throw new UnauthorizedException('Authenticated owner is missing');
    }

    return owner;
  }
);
