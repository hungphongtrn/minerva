import { z } from 'zod';
import type { OrchestratorConfig } from './types.js';
import { WorkspaceStrategy } from '../sandbox/types.js';

const envSchema = z.object({
  PORT: z.coerce.number().default(3000),
  HOST: z.string().default('0.0.0.0'),
  DATABASE_URL: z.string().url().optional(),
  GATEWAY_PROOF_HEADER: z.string().default('x-minerva-gateway-proof'),
  GATEWAY_PROOF_SECRET: z.string().min(1, 'GATEWAY_PROOF_SECRET is required'),
  GATEWAY_TENANT_ID_HEADER: z.string().default('x-minerva-tenant-id'),
  GATEWAY_SUBJECT_ID_HEADER: z.string().default('x-minerva-subject-id'),
  LOG_LEVEL: z.enum(['debug', 'info', 'warn', 'error']).default('info'),
  DAYTONA_SERVER_URL: z.string().min(1, 'DAYTONA_SERVER_URL is required'),
  DAYTONA_API_KEY: z.string().min(1, 'DAYTONA_API_KEY is required'),
  DAYTONA_TARGET: z.string().default('us'),
  PACKS_BASE_PATH: z.string().default('./packs'),
  PACKS_MAX_SKILL_SIZE: z.coerce.number().default(100 * 1024),
  PACKS_ALLOWED_EXTENSIONS: z.string().default('.md'),
  DAYTONA_WORKSPACE_STRATEGY: z.enum(['per_run', 'per_user']).default('per_run'),
  DAYTONA_WORKSPACE_IMAGE: z.string().default('daytonaio/workspace:latest'),
  DAYTONA_WORKSPACE_CPU: z.coerce.number().default(2),
  DAYTONA_WORKSPACE_MEMORY: z.string().default('4Gi'),
  DAYTONA_WORKSPACE_DISK: z.string().default('10Gi'),
  DAYTONA_WORKSPACE_NETWORK: z.enum(['none', 'restricted', 'full']).default('none'),
  DAYTONA_MAX_FILE_SIZE: z.coerce.number().default(10 * 1024 * 1024),
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
    gateway: {
      proofHeader: env.GATEWAY_PROOF_HEADER,
      proofSecret: env.GATEWAY_PROOF_SECRET,
      tenantIdHeader: env.GATEWAY_TENANT_ID_HEADER,
      subjectIdHeader: env.GATEWAY_SUBJECT_ID_HEADER,
    },
    database: {
      url: env.DATABASE_URL,
    },
    logging: {
      level: env.LOG_LEVEL,
    },
    daytona: {
      serverUrl: env.DAYTONA_SERVER_URL,
      apiKey: env.DAYTONA_API_KEY,
      target: env.DAYTONA_TARGET,
    },
    packs: {
      basePath: env.PACKS_BASE_PATH,
      maxSkillSize: env.PACKS_MAX_SKILL_SIZE,
      allowedExtensions: env.PACKS_ALLOWED_EXTENSIONS.split(',').map((ext: string) => ext.trim()),
    },
    sandbox: {
      strategy: env.DAYTONA_WORKSPACE_STRATEGY as WorkspaceStrategy,
      workspace: {
        image: env.DAYTONA_WORKSPACE_IMAGE,
        resources: {
          cpu: env.DAYTONA_WORKSPACE_CPU,
          memory: env.DAYTONA_WORKSPACE_MEMORY,
          disk: env.DAYTONA_WORKSPACE_DISK,
        },
        network: {
          outbound: env.DAYTONA_WORKSPACE_NETWORK,
        },
        timeout: {
          idleMinutes: 30,
          maxLifetimeMinutes: 120,
        },
      },
      security: {
        maxFileSize: env.DAYTONA_MAX_FILE_SIZE,
      },
    },
  };
}
