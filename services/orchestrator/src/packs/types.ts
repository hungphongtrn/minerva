/**
 * Core domain types for agent packs
 */

export interface AgentPack {
  path: string;
  identity: AgentIdentity;
  skills: Skill[];
  metadata: PackMetadata;
}

export interface AgentIdentity {
  name: string;
  description: string;
  stance: string;
  rules: string[];
  rawContent: string;
}

export interface Skill {
  name: string;
  category: string;
  content: string;
  path: string;
  size: number;
}

export interface PackMetadata {
  loadedAt: Date;
  skillCount: number;
  totalSize: number;
}

export interface PackValidationResult {
  valid: boolean;
  errors: PackValidationErrorItem[];
  warnings: PackValidationWarningItem[];
}

export interface PackValidationErrorItem {
  message: string;
  field: string;
  code: string;
}

export interface PackValidationWarningItem {
  message: string;
  field: string;
  code: string;
}

export interface SystemPrompt {
  identity: string;
  skills: string;
  assemblyRules: string;
  fullPrompt: string;
  sections: PromptSection[];
}

export interface PromptSection {
  name: string;
  content: string;
  order: number;
}

export interface PackLoaderConfig {
  maxSkillSize: number;
  allowedExtensions: string[];
}

export interface AssemblyRules {
  identityFirst: boolean;
  includeSkillMetadata: boolean;
  skillOrdering: 'alphabetical' | 'category' | 'size';
  maxPromptLength: number;
}
