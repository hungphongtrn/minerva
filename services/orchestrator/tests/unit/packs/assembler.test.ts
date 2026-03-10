import { describe, it, expect, beforeEach } from 'vitest';
import {
  SystemPromptAssembler,
  assembleSystemPrompt,
  systemPromptAssembler,
  DEFAULT_ASSEMBLY_RULES,
} from '../../../src/packs/assembler.js';
import type { AgentPack, AgentIdentity, Skill, AssemblyRules } from '../../../src/packs/types.js';

describe('SystemPromptAssembler', () => {
  let assembler: SystemPromptAssembler;

  const mockIdentity: AgentIdentity = {
    name: 'Test Agent',
    description: 'A test agent',
    stance: 'Be helpful',
    rules: ['Rule 1', 'Rule 2'],
    rawContent: '# Test Agent\n\nA test agent',
  };

  const mockSkills: Skill[] = [
    {
      name: 'zzzz',
      category: 'z-category',
      content: 'ZZZZ skill content',
      path: '/test/zzzz/SKILL.md',
      size: 100,
    },
    {
      name: 'aaaa',
      category: 'a-category',
      content: 'AAAA skill content',
      path: '/test/aaaa/SKILL.md',
      size: 50,
    },
    {
      name: 'mmmm',
      category: 'm-category',
      content: 'MMMM skill content',
      path: '/test/mmmm/SKILL.md',
      size: 75,
    },
  ];

  const createMockPack = (skills: Skill[] = mockSkills): AgentPack => ({
    path: '/test/pack',
    identity: mockIdentity,
    skills,
    metadata: {
      loadedAt: new Date('2024-01-01'),
      skillCount: skills.length,
      totalSize: skills.reduce((sum, s) => sum + s.size, 0),
    },
  });

  beforeEach(() => {
    assembler = new SystemPromptAssembler();
  });

  describe('assemble', () => {
    it('should assemble prompt with identity first', () => {
      const pack = createMockPack();
      const prompt = assembler.assemble(pack);

      expect(prompt.fullPrompt).toContain('# Test Agent');
      expect(prompt.fullPrompt).toContain('A test agent');
      expect(prompt.identity).toContain('# Test Agent');
    });

    it('should include skills section', () => {
      const pack = createMockPack();
      const prompt = assembler.assemble(pack);

      expect(prompt.skills).toContain('## Skills');
      expect(prompt.skills).toContain('AAAA skill content');
      expect(prompt.skills).toContain('ZZZZ skill content');
    });

    it('should group skills by category', () => {
      const pack = createMockPack();
      const prompt = assembler.assemble(pack);

      expect(prompt.skills).toContain('### a-category');
      expect(prompt.skills).toContain('### m-category');
      expect(prompt.skills).toContain('### z-category');
    });

    it('should order skills alphabetically when configured', () => {
      const assemblerAlpha = new SystemPromptAssembler({ skillOrdering: 'alphabetical' });
      const pack = createMockPack();
      const prompt = assemblerAlpha.assemble(pack);

      // Alphabetically: aaaa, mmmm, zzzz
      // Look for the "#### skillname" headers
      const aaaaIndex = prompt.skills.indexOf('#### aaaa');
      const mmmmIndex = prompt.skills.indexOf('#### mmmm');
      const zzzzIndex = prompt.skills.indexOf('#### zzzz');

      expect(aaaaIndex).toBeLessThan(mmmmIndex);
      expect(mmmmIndex).toBeLessThan(zzzzIndex);
    });

    it('should order skills by size when configured', () => {
      const assemblerSize = new SystemPromptAssembler({ skillOrdering: 'size' });
      const pack = createMockPack();
      const prompt = assemblerSize.assemble(pack);

      // By size: aaaa (50), mmmm (75), zzzz (100)
      // Look for the "#### skillname" headers only
      const aaaaPos = prompt.skills.indexOf('#### aaaa');
      const mmmmPos = prompt.skills.indexOf('#### mmmm');
      const zzzzPos = prompt.skills.indexOf('#### zzzz');

      expect(aaaaPos).toBeLessThan(mmmmPos);
      expect(mmmmPos).toBeLessThan(zzzzPos);
    });

    it('should include assembly rules when configured', () => {
      const assemblerWithMeta = new SystemPromptAssembler({ includeSkillMetadata: true });
      const pack = createMockPack();
      const prompt = assemblerWithMeta.assemble(pack);

      expect(prompt.assemblyRules).toContain('Assembly Information');
      expect(prompt.assemblyRules).toContain('aaaa');
    });

    it('should not include assembly rules by default', () => {
      const pack = createMockPack();
      const prompt = assembler.assemble(pack);

      expect(prompt.assemblyRules).toBe('');
      expect(prompt.sections).toHaveLength(2); // Only identity and skills
    });

    it('should handle empty skills array', () => {
      const pack = createMockPack([]);
      const prompt = assembler.assemble(pack);

      expect(prompt.skills).toBe('');
      expect(prompt.sections).toHaveLength(2);
    });

    it('should throw when prompt exceeds max length', () => {
      const assemblerShort = new SystemPromptAssembler({ maxPromptLength: 10 });
      const pack = createMockPack();

      expect(() => assemblerShort.assemble(pack)).toThrow('exceeds maximum length');
    });

    it('should return structured sections', () => {
      const pack = createMockPack();
      const prompt = assembler.assemble(pack);

      expect(prompt.sections).toHaveLength(2);
      expect(prompt.sections[0].name).toBe('identity');
      expect(prompt.sections[0].order).toBe(0);
      expect(prompt.sections[1].name).toBe('skills');
      expect(prompt.sections[1].order).toBe(1);
    });

    it('should include rules in identity section', () => {
      const pack = createMockPack();
      const prompt = assembler.assemble(pack);

      expect(prompt.identity).toContain('## Rules');
      expect(prompt.identity).toContain('- Rule 1');
      expect(prompt.identity).toContain('- Rule 2');
    });

    it('should include stance in identity section', () => {
      const pack = createMockPack();
      const prompt = assembler.assemble(pack);

      expect(prompt.identity).toContain('## Stance');
      expect(prompt.identity).toContain('Be helpful');
    });
  });

  describe('convenience functions', () => {
    it('assembleSystemPrompt should work with default assembler', () => {
      const pack = createMockPack();
      const prompt = assembleSystemPrompt(pack);

      expect(prompt.identity).toContain('# Test Agent');
      expect(prompt.skills).toContain('## Skills');
    });

    it('systemPromptAssembler singleton should be defined', () => {
      expect(systemPromptAssembler).toBeDefined();
      expect(systemPromptAssembler).toBeInstanceOf(SystemPromptAssembler);
    });

    it('DEFAULT_ASSEMBLY_RULES should have correct defaults', () => {
      expect(DEFAULT_ASSEMBLY_RULES.identityFirst).toBe(true);
      expect(DEFAULT_ASSEMBLY_RULES.includeSkillMetadata).toBe(false);
      expect(DEFAULT_ASSEMBLY_RULES.skillOrdering).toBe('category');
      expect(DEFAULT_ASSEMBLY_RULES.maxPromptLength).toBe(128000);
    });
  });
});
