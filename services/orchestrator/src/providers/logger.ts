import { pino } from 'pino';
import type { ILogger } from './types.js';

export function createLogger(level: string = 'info'): ILogger {
  const logger = pino({
    level,
    transport: {
      target: 'pino-pretty',
      options: {
        colorize: true,
      },
    },
  });

  return {
    debug: (message: string, meta?: Record<string, unknown>) => {
      logger.debug(meta || {}, message);
    },
    info: (message: string, meta?: Record<string, unknown>) => {
      logger.info(meta || {}, message);
    },
    warn: (message: string, meta?: Record<string, unknown>) => {
      logger.warn(meta || {}, message);
    },
    error: (message: string, error?: Error, meta?: Record<string, unknown>) => {
      logger.error({ ...meta, error: error?.message, stack: error?.stack }, message);
    },
  };
}
