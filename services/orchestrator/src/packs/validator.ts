/**
 * Pack validation logic
 */

import fs from 'node:fs';
import path from 'node:path';
import type {
  PackValidationResult,
  PackValidationErrorItem,
  PackValidationWarningItem,
} from './types.js';
import { PackNotFoundError } from './errors.js';

export interface IPackValidator {
  validate(packPath: string): Promise<PackValidationResult>;
  validateSync(packPath: string): PackValidationResult;
}

export class PackValidator implements IPackValidator {
  private requiredFiles: string[] = ['AGENTS.md'];

  validate(packPath: string): Promise<PackValidationResult> {
    return new Promise((resolve, reject) => {
      try {
        resolve(this.validateSync(packPath));
      } catch (error) {
        reject(error);
      }
    });
  }

  validateSync(packPath: string): PackValidationResult {
    const errors: PackValidationErrorItem[] = [];
    const warnings: PackValidationWarningItem[] = [];

    // Check if pack path exists
    if (!fs.existsSync(packPath)) {
      throw new PackNotFoundError(packPath);
    }

    // Check if pack path is a directory
    const stats = fs.statSync(packPath);
    if (!stats.isDirectory()) {
      errors.push({
        message: 'Pack path must be a directory',
        field: 'packPath',
        code: 'NOT_A_DIRECTORY',
      });
      return { valid: false, errors, warnings };
    }

    // Check required files
    const requiredErrors = this.checkRequiredFiles(packPath);
    errors.push(...requiredErrors);

    // Check directory structure
    const dirWarnings = this.checkDirectoryStructure(packPath);
    warnings.push(...dirWarnings);

    return {
      valid: errors.length === 0,
      errors,
      warnings,
    };
  }

  private checkRequiredFiles(packPath: string): PackValidationErrorItem[] {
    const errors: PackValidationErrorItem[] = [];

    for (const file of this.requiredFiles) {
      const filePath = path.join(packPath, file);
      if (!fs.existsSync(filePath)) {
        errors.push({
          message: `Missing required file: ${file}`,
          field: file,
          code: 'MISSING_REQUIRED_FILE',
        });
      }
    }

    return errors;
  }

  private checkDirectoryStructure(packPath: string): PackValidationWarningItem[] {
    const warnings: PackValidationWarningItem[] = [];

    const skillsDir = path.join(packPath, '.agents', 'skills');
    if (!fs.existsSync(skillsDir)) {
      warnings.push({
        message: 'No .agents/skills directory found - pack will have no skills',
        field: 'skills',
        code: 'NO_SKILLS_DIRECTORY',
      });
    }

    return warnings;
  }
}

export const packValidator = new PackValidator();

/**
 * Validate a pack at the given path
 */
export function validatePack(packPath: string): Promise<PackValidationResult> {
  return packValidator.validate(packPath);
}

/**
 * Validate a pack synchronously
 */
export function validatePackSync(packPath: string): PackValidationResult {
  return packValidator.validateSync(packPath);
}
