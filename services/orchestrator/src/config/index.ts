import { z } from 'zod';
import type { OrchestratorConfig } from './types.js';

const envSchema = z.object({
  PORT: z.coerce.number().default(3000),
  HOST: z.string().default('0.0.0.0'),
  LOG_LEVEL: z.enum(['debug', 'info', 'warn', 'error']).default('info'),
  DAYTONA_SERVER_URL: z.string().min(1, 'DAYTONA_SERVER_URL is required'),
  DAYTONA_API_KEY: z.string().min(1, 'DAYTONA_API_KEY is required'),
  DAYTONA_TARGET: z.string().default('us'),
});

export function validateConfig(config: Record<string, unknown>): z.infer<typeof envSchema> {
  const result = envSchema.safeParse(config);

  if (!result.success) {
    const errors = result.error.issues
      .map((issue: z.ZodIssue) => `${issue.path.join('.')}: ${issue.message}`)
      .join('\n');
    throw new Error(`Configuration validation failed:\n${errors}`);
  }

  return result.data;
}

export function loadConfig(): OrchestratorConfig {
  const env = validateConfig(process.env as Record<string, unknown>);

  return {
    server: {
      port: env.PORT,
      host: env.HOST,
    },
    logging: {
      level: env.LOG_LEVEL,
    },
    daytona: {
      serverUrl: env.DAYTONA_SERVER_URL,
      apiKey: env.DAYTONA_API_KEY,
      target: env.DAYTONA_TARGET,
    },
  };
}
