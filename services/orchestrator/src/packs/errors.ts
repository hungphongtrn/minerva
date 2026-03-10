/**
 * Custom error types for pack operations
 */

export class PackError extends Error {
  constructor(
    message: string,
    public code: string
  ) {
    super(message);
    this.name = 'PackError';
  }
}

export class PackValidationError extends PackError {
  constructor(
    message: string,
    public field: string,
    public severity: 'error' | 'warning'
  ) {
    super(message, 'VALIDATION_ERROR');
    this.name = 'PackValidationError';
  }
}

export class PackNotFoundError extends PackError {
  constructor(packPath: string) {
    super(`Pack not found at path: ${packPath}`, 'PACK_NOT_FOUND');
    this.name = 'PackNotFoundError';
  }
}

export class MissingRequiredFileError extends PackValidationError {
  constructor(fileName: string) {
    super(
      `Missing required file: ${fileName}`,
      fileName,
      'error'
    );
    this.name = 'MissingRequiredFileError';
  }
}

export class SkillLoadError extends PackError {
  constructor(
    skillPath: string,
    public cause: Error
  ) {
    super(
      `Failed to load skill at ${skillPath}: ${cause.message}`,
      'SKILL_LOAD_ERROR'
    );
    this.name = 'SkillLoadError';
  }
}
