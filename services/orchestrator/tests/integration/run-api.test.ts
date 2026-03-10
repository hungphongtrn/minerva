import type { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { AppModule } from '../../dist/app.module.js';
import { SANDBOX_ADAPTER } from '../../dist/providers/provider-tokens.js';
import { MockSandboxAdapter } from '../test-utils/mock-sandbox-adapter.js';

describe('Run API', () => {
  let app: INestApplication;

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

  it('creates, executes, and reports a run', async () => {
    const createResponse = await request(app.getHttpServer())
      .post('/api/v0/runs')
      .send({
        userId: 'user-1',
        agentPackId: 'valid-pack',
        prompt: 'tool:bash echo hello world',
      })
      .expect(201);

    expect(createResponse.body.runId).toBeTruthy();
    expect(createResponse.body.state).toBe('queued');

    const runId = createResponse.body.runId as string;

    let latestResponse = await request(app.getHttpServer())
      .get(`/api/v0/runs/${runId}`)
      .expect(200);

    for (let attempt = 0; attempt < 20 && latestResponse.body.state !== 'completed'; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 50));
      latestResponse = await request(app.getHttpServer())
        .get(`/api/v0/runs/${runId}`)
        .expect(200);
    }

    expect(latestResponse.body.state).toBe('completed');
    expect(latestResponse.body.durationMs).toBeGreaterThanOrEqual(0);
  });

  it('cancels a queued run', async () => {
    await request(app.getHttpServer())
      .post('/api/v0/runs')
      .send({
        userId: 'user-2',
        agentPackId: 'valid-pack',
        prompt: 'tool:bash slow-command',
      })
      .expect(201);

    const createResponse = await request(app.getHttpServer())
      .post('/api/v0/runs')
      .send({
        userId: 'user-2',
        agentPackId: 'valid-pack',
        prompt: 'plain response',
      })
      .expect(201);

    const cancelResponse = await request(app.getHttpServer())
      .post(`/api/v0/runs/${createResponse.body.runId}/cancel`)
      .send({ reason: 'Changed my mind' })
      .expect(200);

    expect(cancelResponse.body.state).toBe('cancelled');
    expect(cancelResponse.body.reason).toBe('Changed my mind');
  });
});
