import { describe, it, expect } from 'vitest';
import {
  PackError,
  PackValidationError,
  PackNotFoundError,
  MissingRequiredFileError,
  SkillLoadError,
} from '../../../src/packs/errors.js';

describe('PackError', () => {
  it('should have correct code', () => {
    const error = new PackError('test message', 'TEST_CODE');
    
    expect(error.message).toBe('test message');
    expect(error.code).toBe('TEST_CODE');
    expect(error.name).toBe('PackError');
  });
});

describe('PackValidationError', () => {
  it('should have correct properties for error severity', () => {
    const error = new PackValidationError('validation failed', 'field1', 'error');
    
    expect(error.message).toBe('validation failed');
    expect(error.field).toBe('field1');
    expect(error.severity).toBe('error');
    expect(error.code).toBe('VALIDATION_ERROR');
    expect(error.name).toBe('PackValidationError');
  });

  it('should have correct properties for warning severity', () => {
    const error = new PackValidationError('validation warning', 'field2', 'warning');
    
    expect(error.severity).toBe('warning');
  });
});

describe('PackNotFoundError', () => {
  it('should have correct message and code', () => {
    const error = new PackNotFoundError('/path/to/pack');
    
    expect(error.message).toBe('Pack not found at path: /path/to/pack');
    expect(error.code).toBe('PACK_NOT_FOUND');
    expect(error.name).toBe('PackNotFoundError');
  });
});

describe('MissingRequiredFileError', () => {
  it('should have correct properties', () => {
    const error = new MissingRequiredFileError('AGENTS.md');
    
    expect(error.message).toBe('Missing required file: AGENTS.md');
    expect(error.field).toBe('AGENTS.md');
    expect(error.severity).toBe('error');
    expect(error.code).toBe('VALIDATION_ERROR');
    expect(error.name).toBe('MissingRequiredFileError');
  });

  it('should work with different file names', () => {
    const error = new MissingRequiredFileError('config.json');
    
    expect(error.message).toBe('Missing required file: config.json');
    expect(error.field).toBe('config.json');
  });
});

describe('SkillLoadError', () => {
  it('should preserve cause error', () => {
    const cause = new Error('File not readable');
    const error = new SkillLoadError('/path/to/skill.md', cause);
    
    expect(error.message).toBe('Failed to load skill at /path/to/skill.md: File not readable');
    expect(error.code).toBe('SKILL_LOAD_ERROR');
    expect(error.cause).toBe(cause);
    expect(error.name).toBe('SkillLoadError');
  });

  it('should handle different error messages', () => {
    const cause = new Error('Permission denied');
    const error = new SkillLoadError('/other/skill.md', cause);
    
    expect(error.message).toContain('Permission denied');
    expect(error.message).toContain('/other/skill.md');
  });
});

describe('Error inheritance', () => {
  it('PackValidationError should be instance of PackError', () => {
    const error = new PackValidationError('test', 'field', 'error');
    
    expect(error).toBeInstanceOf(PackError);
    expect(error).toBeInstanceOf(Error);
  });

  it('PackNotFoundError should be instance of PackError', () => {
    const error = new PackNotFoundError('/test');
    
    expect(error).toBeInstanceOf(PackError);
  });

  it('MissingRequiredFileError should be instance of PackValidationError', () => {
    const error = new MissingRequiredFileError('file.md');
    
    expect(error).toBeInstanceOf(PackValidationError);
    expect(error).toBeInstanceOf(PackError);
  });

  it('SkillLoadError should be instance of PackError', () => {
    const error = new SkillLoadError('/test', new Error('cause'));
    
    expect(error).toBeInstanceOf(PackError);
  });
});
