import { describe, it, expect } from 'vitest';
import { validatePath, sanitizeFilename } from './security.js';

describe('validatePath', () => {
  const workspaceRoot = '/workspace';

  it('should accept valid relative paths', () => {
    const result = validatePath('file.txt', workspaceRoot);
    expect(result.isValid).toBe(true);
    expect(result.normalizedPath).toBe('file.txt');
  });

  it('should accept nested paths', () => {
    const result = validatePath('src/components/button.tsx', workspaceRoot);
    expect(result.isValid).toBe(true);
    expect(result.normalizedPath).toBe('src/components/button.tsx');
  });

  it('should reject absolute paths', () => {
    const result = validatePath('/etc/passwd', workspaceRoot);
    expect(result.isValid).toBe(false);
    expect(result.error).toBe('Absolute paths not allowed');
  });

  it('should reject path traversal with ../', () => {
    const result = validatePath('../../../etc/passwd', workspaceRoot);
    expect(result.isValid).toBe(false);
    expect(result.error).toBe('Path traversal detected');
  });

  it('should reject path traversal embedded in valid path', () => {
    const result = validatePath('foo/../../../etc/passwd', workspaceRoot);
    expect(result.isValid).toBe(false);
    expect(result.error).toBe('Path traversal detected');
  });

  it('should reject path traversal with ./../', () => {
    const result = validatePath('./../../etc/passwd', workspaceRoot);
    expect(result.isValid).toBe(false);
    expect(result.error).toBe('Path traversal detected');
  });

  it('should reject path traversal with multiple levels', () => {
    const result = validatePath('foo/bar/../../../../etc/passwd', workspaceRoot);
    expect(result.isValid).toBe(false);
    expect(result.error).toBe('Path traversal detected');
  });

  it('should reject null bytes', () => {
    const result = validatePath('file.txt\0.exe', workspaceRoot);
    expect(result.isValid).toBe(false);
    expect(result.error).toBe('Path contains null bytes');
  });

  it('should normalize . in paths', () => {
    const result = validatePath('./file.txt', workspaceRoot);
    expect(result.isValid).toBe(true);
    expect(result.normalizedPath).toBe('file.txt');
  });

  it('should normalize .. within bounds', () => {
    const result = validatePath('foo/bar/../baz.txt', workspaceRoot);
    expect(result.isValid).toBe(true);
    expect(result.normalizedPath).toBe('foo/baz.txt');
  });

  it('should reject Windows-style path traversal', () => {
    const result = validatePath('..\\..\\windows\\system32\\config\\sam', workspaceRoot);
    // On Unix systems, backslash is not a path separator, but the path still starts with ..
    expect(result.isValid).toBe(false);
    expect(result.error).toBe('Path traversal detected');
  });

  it('should handle empty path', () => {
    const result = validatePath('.', workspaceRoot);
    expect(result.isValid).toBe(true);
    expect(result.normalizedPath).toBe('.');
  });
});

describe('sanitizeFilename', () => {
  it('should remove null bytes', () => {
    const result = sanitizeFilename('file\0.txt');
    expect(result).toBe('file.txt');
  });

  it('should replace path separators with underscore', () => {
    const result = sanitizeFilename('path/to/file.txt');
    expect(result).toBe('path_to_file.txt');
  });

  it('should replace backslash separators with underscore', () => {
    const result = sanitizeFilename('path\\to\\file.txt');
    expect(result).toBe('path_to_file.txt');
  });

  it('should remove leading dots', () => {
    const result = sanitizeFilename('..hidden.txt');
    expect(result).toBe('hidden.txt');
  });

  it('should trim whitespace', () => {
    const result = sanitizeFilename('  file.txt  ');
    expect(result).toBe('file.txt');
  });

  it('should return unnamed for empty string', () => {
    const result = sanitizeFilename('');
    expect(result).toBe('unnamed');
  });

  it('should return unnamed for string with only dots', () => {
    const result = sanitizeFilename('...');
    expect(result).toBe('unnamed');
  });
});
