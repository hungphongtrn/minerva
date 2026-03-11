import 'reflect-metadata';

process.env.PORT ??= '3000';
process.env.HOST ??= '127.0.0.1';
process.env.GATEWAY_PROOF_SECRET ??= 'test-gateway-proof';
process.env.LOG_LEVEL ??= 'info';
process.env.DAYTONA_SERVER_URL ??= 'https://example.test';
process.env.DAYTONA_API_KEY ??= 'test-key';
process.env.DAYTONA_TARGET ??= 'us';
process.env.MODEL_PROVIDER ??= 'openai';
process.env.OPENAI_API_KEY ??= 'test-openai-key';
process.env.MODEL_NAME ??= 'gpt-4o-mini';
process.env.LLM_BASE_URL ??= 'https://api.openai.com/v1';
process.env.LLM_API_KEY ??= 'test-llm-key';
process.env.LLM_MODEL ??= 'gpt-4o-mini';
process.env.PACKS_BASE_PATH ??= './tests/fixtures/packs';

export {};
