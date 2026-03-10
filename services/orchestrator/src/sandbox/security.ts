import path from 'node:path';
import type { PathValidationResult } from './types.js';

/**
 * Validate and normalize a user-provided path.
 * 
 * Rules:
 * 1. Path must be relative (no leading /)
 * 2. Path must not escape workspace root (no ../..)
 * 3. Path must not contain null bytes
 * 4. Path is normalized (resolve . and .. safely)
 */
export function validatePath(
  userPath: string,
  workspaceRoot: string
): PathValidationResult {
  // Check for null bytes
  if (userPath.includes('\0')) {
    return { isValid: false, normalizedPath: '', error: 'Path contains null bytes' };
  }

  // Check for absolute paths
  if (path.isAbsolute(userPath)) {
    return { isValid: false, normalizedPath: '', error: 'Absolute paths not allowed' };
  }

  // Normalize the path
  const normalized = path.normalize(userPath);

  // Check for traversal attempts after normalization
  if (normalized.startsWith('..')) {
    return { isValid: false, normalizedPath: '', error: 'Path traversal detected' };
  }

  // Final resolved path must still be under workspace root
  const resolvedPath = path.join(workspaceRoot, normalized);
  const relativeToRoot = path.relative(workspaceRoot, resolvedPath);

  if (relativeToRoot.startsWith('..') || path.isAbsolute(relativeToRoot)) {
    return { isValid: false, normalizedPath: '', error: 'Path escapes workspace root' };
  }

  return { isValid: true, normalizedPath: normalized };
}

/**
 * Sanitize a filename to prevent directory traversal
 */
export function sanitizeFilename(filename: string): string {
  // Remove null bytes
  let sanitized = filename.replace(/\0/g, '');
  
  // Remove path separators
  sanitized = sanitized.replace(/[/\\]/g, '_');
  
  // Remove leading dots (hidden files)
  sanitized = sanitized.replace(/^\.+/, '');
  
  // Trim whitespace
  sanitized = sanitized.trim();
  
  // Ensure not empty
  if (!sanitized) {
    sanitized = 'unnamed';
  }
  
  return sanitized;
}
