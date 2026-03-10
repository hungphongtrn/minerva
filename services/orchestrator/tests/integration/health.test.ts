import type { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { AppModule } from '../../dist/app.module.js';

describe('Health endpoint', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleRef = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleRef.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    if (app) {
      await app.close();
    }
  });

  it('responds with 200 and health payload', async () => {
    const response = await request(app.getHttpServer()).get('/health').expect(200);

    expect(response.body.status).toBe('ok');
    expect(new Date(response.body.timestamp).toISOString()).toBe(response.body.timestamp);
  });
});
