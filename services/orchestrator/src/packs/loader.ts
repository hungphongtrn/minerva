/**
 * Pack loading operations
 */

import fs from 'node:fs/promises';
import fsSync from 'node:fs';
import path from 'node:path';
import type {
  AgentPack,
  AgentIdentity,
  Skill,
  PackMetadata,
  PackLoaderConfig,
} from './types.js';
import { PackNotFoundError, SkillLoadError, MissingRequiredFileError } from './errors.js';

export interface IPackLoader {
  load(packPath: string): Promise<AgentPack>;
  loadSkills(skillsDir: string): Promise<Skill[]>;
}

export const DEFAULT_LOADER_CONFIG: PackLoaderConfig = {
  maxSkillSize: 100 * 1024, // 100KB
  allowedExtensions: ['.md'],
};

export class PackLoader implements IPackLoader {
  private config: PackLoaderConfig;

  constructor(config: Partial<PackLoaderConfig> = {}) {
    this.config = { ...DEFAULT_LOADER_CONFIG, ...config };
  }

  async load(packPath: string): Promise<AgentPack> {
    // Check if pack exists
    if (!fsSync.existsSync(packPath)) {
      throw new PackNotFoundError(packPath);
    }

    // Load AGENTS.md
    const agentsMdPath = path.join(packPath, 'AGENTS.md');
    if (!fsSync.existsSync(agentsMdPath)) {
      throw new MissingRequiredFileError('AGENTS.md');
    }

    const identityContent = await fs.readFile(agentsMdPath, 'utf-8');
    const identity = this.parseIdentity(identityContent);

    // Load skills
    const skillsDir = path.join(packPath, '.agents', 'skills');
    const skills = fsSync.existsSync(skillsDir) 
      ? await this.loadSkills(skillsDir)
      : [];

    // Calculate metadata
    const totalSize = skills.reduce((sum, skill) => sum + skill.size, 0);
    const metadata: PackMetadata = {
      loadedAt: new Date(),
      skillCount: skills.length,
      totalSize,
    };

    return {
      path: packPath,
      identity,
      skills,
      metadata,
    };
  }

  async loadSkills(skillsDir: string): Promise<Skill[]> {
    const skills: Skill[] = [];

    if (!fsSync.existsSync(skillsDir)) {
      return skills;
    }

    // Get all category directories
    const categories = await fs.readdir(skillsDir);

    for (const category of categories) {
      const categoryPath = path.join(skillsDir, category);
      const stat = await fs.stat(categoryPath);

      if (!stat.isDirectory()) {
        continue;
      }

      // Look for SKILL.md in this category
      const skillFilePath = path.join(categoryPath, 'SKILL.md');
      if (fsSync.existsSync(skillFilePath)) {
        const skill = await this.readSkillFile(skillFilePath, category);
        skills.push(skill);
      }
    }

    return skills;
  }

  private parseIdentity(content: string): AgentIdentity {
    // Parse AGENTS.md content
    // Extract name from first heading
    const nameMatch = content.match(/^#\s+(.+)$/m);
    const name = nameMatch ? nameMatch[1].trim() : 'Unknown Agent';

    // Extract description (first paragraph after heading)
    const descMatch = content.match(/^#\s+.+\n\n(.+?)(?=\n\n|\n##|$)/s);
    const description = descMatch ? descMatch[1].trim() : '';

    // Extract stance (section under ## Stance)
    const stanceMatch = content.match(/##\s+Stance\n\n(.+?)(?=\n##|$)/is);
    const stance = stanceMatch ? stanceMatch[1].trim() : '';

    // Extract rules (bullet points under ## Rules)
    const rulesMatch = content.match(/##\s+Rules\n\n([\s\S]*?)(?=\n##|$)/i);
    const rules = rulesMatch 
      ? rulesMatch[1]
          .split('\n')
          .map(line => line.trim())
          .filter(line => line.startsWith('- ') || line.startsWith('* '))
          .map(line => line.replace(/^[-*]\s+/, ''))
      : [];

    return {
      name,
      description,
      stance,
      rules,
      rawContent: content,
    };
  }

  private async readSkillFile(skillPath: string, category: string): Promise<Skill> {
    try {
      const stat = await fs.stat(skillPath);
      
      // Validate size
      this.validateSkillSize(stat.size);

      const content = await fs.readFile(skillPath, 'utf-8');
      const name = path.basename(path.dirname(skillPath));

      return {
        name,
        category,
        content,
        path: skillPath,
        size: stat.size,
      };
    } catch (error) {
      if (error instanceof Error) {
        throw new SkillLoadError(skillPath, error);
      }
      throw error;
    }
  }

  private validateSkillSize(size: number): void {
    if (size > this.config.maxSkillSize) {
      throw new Error(
        `Skill file exceeds maximum size of ${this.config.maxSkillSize} bytes`
      );
    }
  }
}

export const packLoader = new PackLoader();

/**
 * Load a pack from the given path
 */
export function loadPack(packPath: string): Promise<AgentPack> {
  return packLoader.load(packPath);
}

/**
 * Load skills from a directory
 */
export function loadSkills(skillsDir: string): Promise<Skill[]> {
  return packLoader.loadSkills(skillsDir);
}

/**
 * Parse agent identity from AGENTS.md content
 */
export function parseAgentIdentity(content: string): AgentIdentity {
  return packLoader['parseIdentity'](content);
}
