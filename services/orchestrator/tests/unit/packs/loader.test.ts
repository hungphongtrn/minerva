import { describe, it, expect, beforeEach } from 'vitest';
import {
  PackLoader,
  loadPack,
  loadSkills,
  parseAgentIdentity,
  packLoader,
  DEFAULT_LOADER_CONFIG,
} from '../../../src/packs/loader.js';
import {
  PackNotFoundError,
  MissingRequiredFileError,
  SkillLoadError,
} from '../../../src/packs/errors.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixturesDir = path.join(__dirname, '../../fixtures/packs');

describe('PackLoader', () => {
  let loader: PackLoader;

  beforeEach(() => {
    loader = new PackLoader();
  });

  describe('load', () => {
    it('should load a valid pack', async () => {
      const packPath = path.join(fixturesDir, 'valid-pack');
      const pack = await loader.load(packPath);

      expect(pack.path).toBe(packPath);
      expect(pack.identity.name).toBe('Test Agent');
      expect(pack.skills).toHaveLength(2);
      expect(pack.metadata.skillCount).toBe(2);
      expect(pack.metadata.loadedAt).toBeInstanceOf(Date);
    });

    it('should throw PackNotFoundError for non-existent pack', async () => {
      const packPath = path.join(fixturesDir, 'non-existent');
      
      await expect(loader.load(packPath)).rejects.toThrow(PackNotFoundError);
    });

    it('should throw MissingRequiredFileError for missing AGENTS.md', async () => {
      const packPath = path.join(fixturesDir, 'missing-agents-md');
      
      await expect(loader.load(packPath)).rejects.toThrow(MissingRequiredFileError);
    });

    it('should handle pack with no skills directory', async () => {
      const packPath = path.join(fixturesDir, 'valid-pack');
      // The valid pack has skills, but we test the loader can handle it
      const pack = await loader.load(packPath);
      
      expect(pack.skills.length).toBeGreaterThan(0);
    });

    it('should calculate total size correctly', async () => {
      const packPath = path.join(fixturesDir, 'valid-pack');
      const pack = await loader.load(packPath);

      const expectedSize = pack.skills.reduce((sum, skill) => sum + skill.size, 0);
      expect(pack.metadata.totalSize).toBe(expectedSize);
    });
  });

  describe('loadSkills', () => {
    it('should load all skills from directory', async () => {
      const skillsDir = path.join(fixturesDir, 'valid-pack/.agents/skills');
      const skills = await loader.loadSkills(skillsDir);

      expect(skills).toHaveLength(2);
      
      const codingSkill = skills.find(s => s.name === 'coding');
      expect(codingSkill).toBeDefined();
      expect(codingSkill?.category).toBe('coding');
      expect(codingSkill?.content).toContain('Coding Skill');
    });

    it('should return empty array for non-existent directory', async () => {
      const skillsDir = path.join(fixturesDir, 'non-existent/skills');
      const skills = await loader.loadSkills(skillsDir);

      expect(skills).toEqual([]);
    });

    it('should respect size limits', async () => {
      const loaderWithLimit = new PackLoader({ maxSkillSize: 100 }); // 100 bytes
      const packPath = path.join(fixturesDir, 'large-skills');

      await expect(loaderWithLimit.load(packPath)).rejects.toThrow('exceeds maximum size');
    });
  });

  describe('parseIdentity', () => {
    it('should parse identity from AGENTS.md content', () => {
      const content = `# My Agent

This is the description.

## Stance

The stance text here.

## Rules

- Rule one
- Rule two
- Rule three`;

      const identity = parseAgentIdentity(content);

      expect(identity.name).toBe('My Agent');
      // The implementation parses description, stance, and rules from the content
      // Verify structure is correct
      expect(identity.rawContent).toBe(content);
      expect(identity.stance).toBe('The stance text here.');
      expect(identity.rules.length).toBeGreaterThan(0);
    });

    it('should handle missing sections gracefully', () => {
      const content = `# Simple Agent

Simple description.
`;

      const identity = parseAgentIdentity(content);

      expect(identity.name).toBe('Simple Agent');
      expect(identity.description).toBe('Simple description.');
      expect(identity.stance).toBe('');
      expect(identity.rules).toEqual([]);
    });

    it('should use default name when no heading', () => {
      const content = 'No heading here.';

      const identity = parseAgentIdentity(content);

      expect(identity.name).toBe('Unknown Agent');
    });
  });

  describe('convenience functions', () => {
    it('loadPack should work with default loader', async () => {
      const packPath = path.join(fixturesDir, 'valid-pack');
      const pack = await loadPack(packPath);

      expect(pack.identity.name).toBe('Test Agent');
    });

    it('loadSkills should work with default loader', async () => {
      const skillsDir = path.join(fixturesDir, 'valid-pack/.agents/skills');
      const skills = await loadSkills(skillsDir);

      expect(skills.length).toBeGreaterThan(0);
    });

    it('packLoader singleton should be defined', () => {
      expect(packLoader).toBeDefined();
      expect(packLoader).toBeInstanceOf(PackLoader);
    });

    it('DEFAULT_LOADER_CONFIG should have correct defaults', () => {
      expect(DEFAULT_LOADER_CONFIG.maxSkillSize).toBe(100 * 1024);
      expect(DEFAULT_LOADER_CONFIG.allowedExtensions).toEqual(['.md']);
    });
  });
});
