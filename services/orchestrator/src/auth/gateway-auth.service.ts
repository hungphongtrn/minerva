import { Inject, Injectable, UnauthorizedException } from '@nestjs/common';
import { timingSafeEqual } from 'node:crypto';
import type { IncomingHttpHeaders } from 'node:http';
import { ORCHESTRATOR_CONFIG } from '../config/config.constants.js';
import type { OrchestratorConfig } from '../config/types.js';
import type { OwnerPrincipal } from '../types/owner.js';

@Injectable()
export class GatewayAuthService {
  constructor(
    @Inject(ORCHESTRATOR_CONFIG) private readonly config: OrchestratorConfig
  ) {}

  authenticate(headers: IncomingHttpHeaders): OwnerPrincipal {
    const proof = this.readRequiredHeader(headers, this.config.gateway.proofHeader, 'gateway proof');

    if (!this.isExpectedProof(proof)) {
      throw new UnauthorizedException('Invalid gateway proof');
    }

    return {
      tenantId: this.readRequiredHeader(
        headers,
        this.config.gateway.tenantIdHeader,
        'tenant identity'
      ),
      subjectId: this.readRequiredHeader(
        headers,
        this.config.gateway.subjectIdHeader,
        'subject identity'
      ),
    };
  }

  private isExpectedProof(value: string): boolean {
    const actual = Buffer.from(value);
    const expected = Buffer.from(this.config.gateway.proofSecret);

    if (actual.length !== expected.length) {
      return false;
    }

    return timingSafeEqual(actual, expected);
  }

  private readRequiredHeader(
    headers: IncomingHttpHeaders,
    headerName: string,
    description: string
  ): string {
    const rawValue = headers[headerName.toLowerCase()];

    if (Array.isArray(rawValue)) {
      throw new UnauthorizedException(`Expected a single ${description} header`);
    }

    const value = rawValue?.trim();
    if (!value) {
      throw new UnauthorizedException(`Missing ${description}`);
    }

    return value;
  }
}
