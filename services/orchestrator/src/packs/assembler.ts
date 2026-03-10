/**
 * System prompt assembly
 */

import type {
  AgentPack,
  AgentIdentity,
  Skill,
  SystemPrompt,
  PromptSection,
  AssemblyRules,
} from './types.js';

export interface ISystemPromptAssembler {
  assemble(pack: AgentPack): SystemPrompt;
}

export const DEFAULT_ASSEMBLY_RULES: AssemblyRules = {
  identityFirst: true,
  includeSkillMetadata: false,
  skillOrdering: 'category',
  maxPromptLength: 128000,
};

export class SystemPromptAssembler implements ISystemPromptAssembler {
  private rules: AssemblyRules;

  constructor(rules?: Partial<AssemblyRules>) {
    this.rules = { ...DEFAULT_ASSEMBLY_RULES, ...rules };
  }

  assemble(pack: AgentPack): SystemPrompt {
    const sections: PromptSection[] = [];
    let order = 0;

    // Build identity section
    const identityContent = this.buildIdentitySection(pack.identity);
    sections.push({
      name: 'identity',
      content: identityContent,
      order: order++,
    });

    // Order skills according to rules
    const orderedSkills = this.orderSkills(pack.skills);

    // Build skills section
    const skillsContent = this.buildSkillsSection(orderedSkills);
    sections.push({
      name: 'skills',
      content: skillsContent,
      order: order++,
    });

    // Build assembly rules section (optional)
    let assemblyRulesContent = '';
    if (this.rules.includeSkillMetadata) {
      assemblyRulesContent = this.buildAssemblyRulesSection(pack);
      sections.push({
        name: 'assembly-rules',
        content: assemblyRulesContent,
        order: order++,
      });
    }

    // Build full prompt
    const fullPrompt = this.buildFullPrompt(sections);

    // Check max prompt length
    if (fullPrompt.length > this.rules.maxPromptLength) {
      throw new Error(
        `Assembled prompt exceeds maximum length of ${this.rules.maxPromptLength} characters`
      );
    }

    return {
      identity: identityContent,
      skills: skillsContent,
      assemblyRules: assemblyRulesContent,
      fullPrompt,
      sections,
    };
  }

  private buildIdentitySection(identity: AgentIdentity): string {
    const parts: string[] = [];

    parts.push(`# ${identity.name}`);
    parts.push('');
    parts.push(identity.description);

    if (identity.stance) {
      parts.push('');
      parts.push('## Stance');
      parts.push('');
      parts.push(identity.stance);
    }

    if (identity.rules.length > 0) {
      parts.push('');
      parts.push('## Rules');
      parts.push('');
      identity.rules.forEach(rule => {
        parts.push(`- ${rule}`);
      });
    }

    return parts.join('\n');
  }

  private buildSkillsSection(skills: Skill[]): string {
    if (skills.length === 0) {
      return '';
    }

    const parts: string[] = [];
    parts.push('## Skills');
    parts.push('');

    // Group skills by category
    const skillsByCategory = this.groupSkillsByCategory(skills);

    for (const [category, categorySkills] of skillsByCategory) {
      parts.push(`### ${category}`);
      parts.push('');

      for (const skill of categorySkills) {
        parts.push(`#### ${skill.name}`);
        parts.push('');
        parts.push(skill.content);
        parts.push('');
      }
    }

    return parts.join('\n');
  }

  private buildAssemblyRulesSection(pack: AgentPack): string {
    const parts: string[] = [];

    parts.push('## Assembly Information');
    parts.push('');
    parts.push(`- **Loaded at**: ${pack.metadata.loadedAt.toISOString()}`);
    parts.push(`- **Pack path**: ${pack.path}`);
    parts.push(`- **Skills loaded**: ${pack.metadata.skillCount}`);
    parts.push(`- **Total size**: ${pack.metadata.totalSize} bytes`);
    parts.push(`- **Assembly rules**: ${JSON.stringify(this.rules)}`);
    parts.push('');

    if (pack.skills.length > 0) {
      parts.push('### Loaded Skills');
      parts.push('');
      for (const skill of pack.skills) {
        parts.push(`- ${skill.name} (${skill.category}): ${skill.size} bytes`);
      }
    }

    return parts.join('\n');
  }

  private groupSkillsByCategory(skills: Skill[]): Map<string, Skill[]> {
    const groups = new Map<string, Skill[]>();

    for (const skill of skills) {
      const existing = groups.get(skill.category) || [];
      existing.push(skill);
      groups.set(skill.category, existing);
    }

    return groups;
  }

  private orderSkills(skills: Skill[]): Skill[] {
    const sorted = [...skills];

    switch (this.rules.skillOrdering) {
      case 'alphabetical':
        return sorted.sort((a, b) => a.name.localeCompare(b.name));
      
      case 'category':
        return sorted.sort((a, b) => {
          const catCompare = a.category.localeCompare(b.category);
          if (catCompare !== 0) return catCompare;
          return a.name.localeCompare(b.name);
        });
      
      case 'size':
        return sorted.sort((a, b) => a.size - b.size);
      
      default:
        return sorted;
    }
  }

  private buildFullPrompt(sections: PromptSection[]): string {
    const sorted = [...sections].sort((a, b) => a.order - b.order);
    
    const parts: string[] = [];
    for (const section of sorted) {
      if (section.content) {
        parts.push(section.content);
        parts.push('');
      }
    }

    return parts.join('\n').trim();
  }
}

export const systemPromptAssembler = new SystemPromptAssembler();

/**
 * Assemble a system prompt from a pack
 */
export function assembleSystemPrompt(pack: AgentPack): SystemPrompt {
  return systemPromptAssembler.assemble(pack);
}
