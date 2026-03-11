import type { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { AppModule } from '../../dist/app.module.js';
import { SANDBOX_ADAPTER } from '../../dist/providers/provider-tokens.js';
import { MockSandboxAdapter } from '../test-utils/mock-sandbox-adapter.js';
import { createGatewayAuthHeaders } from '../test-utils/gateway-auth.js';

describe('Run API', () => {
  let app: INestApplication;
  const ownerHeaders = createGatewayAuthHeaders();

  beforeAll(async () => {
    const moduleRef = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(SANDBOX_ADAPTER)
      .useValue(new MockSandboxAdapter())
      .compile();

    app = moduleRef.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    if (app) {
      await app.close();
    }
  });

  it('creates and reports a run for the authenticated owner', async () => {
    const createResponse = await request(app.getHttpServer())
      .post('/api/v0/runs')
      .set(ownerHeaders)
      .send({
        agentPackId: 'valid-pack',
        prompt: 'tool:bash echo hello world',
      })
      .expect(201);

    expect(createResponse.body.runId).toBeTruthy();
    expect(createResponse.body.state).toBe('queued');
    expect(createResponse.body.tenantId).toBe('tenant-1');
    expect(createResponse.body.subjectId).toBe('user-1');

    const runId = createResponse.body.runId as string;

    const latestResponse = await request(app.getHttpServer())
      .get(`/api/v0/runs/${runId}`)
      .set(ownerHeaders)
      .expect(200);

    expect(latestResponse.body.runId).toBe(runId);
    expect(latestResponse.body.tenantId).toBe('tenant-1');
    expect(latestResponse.body.subjectId).toBe('user-1');
  });

  it('allows the authenticated owner to issue a cancellation request', async () => {
    const createResponse = await request(app.getHttpServer())
      .post('/api/v0/runs')
      .set(ownerHeaders)
      .send({
        agentPackId: 'valid-pack',
        prompt: 'plain response',
      })
      .expect(201);

    const cancelResponse = await request(app.getHttpServer())
      .post(`/api/v0/runs/${createResponse.body.runId}/cancel`)
      .set(ownerHeaders)
      .send({ reason: 'Changed my mind' })
      .expect(200);

    expect(cancelResponse.body.runId).toBe(createResponse.body.runId);
    expect(['cancelled', 'failed']).toContain(cancelResponse.body.state);
  });

  it('rejects missing gateway proof', async () => {
    await request(app.getHttpServer())
      .post('/api/v0/runs')
      .send({
        agentPackId: 'valid-pack',
        prompt: 'plain response',
      })
      .expect(401);
  });

  it('does not expose runs to a different authenticated owner', async () => {
    const createResponse = await request(app.getHttpServer())
      .post('/api/v0/runs')
      .set(createGatewayAuthHeaders({ tenantId: 'tenant-a', subjectId: 'user-a' }))
      .send({
        agentPackId: 'valid-pack',
        prompt: 'plain response',
      })
      .expect(201);

    await request(app.getHttpServer())
      .get(`/api/v0/runs/${createResponse.body.runId}`)
      .set(createGatewayAuthHeaders({ tenantId: 'tenant-b', subjectId: 'user-b' }))
      .expect(404);

    await request(app.getHttpServer())
      .post(`/api/v0/runs/${createResponse.body.runId}/cancel`)
      .set(createGatewayAuthHeaders({ tenantId: 'tenant-b', subjectId: 'user-b' }))
      .send({ reason: 'not allowed' })
      .expect(404);
  });
});
