import 'reflect-metadata';

process.env.PORT ??= '3000';
process.env.HOST ??= '127.0.0.1';
process.env.LOG_LEVEL ??= 'info';
process.env.DAYTONA_SERVER_URL ??= 'https://example.test';
process.env.DAYTONA_API_KEY ??= 'test-key';
process.env.DAYTONA_TARGET ??= 'us';
process.env.PACKS_BASE_PATH ??= './tests/fixtures/packs';

export {};
