/**
 * Agent Pack Loading
 * 
 * Public API for loading and validating agent packs.
 */

// Types
export type {
  AgentPack,
  AgentIdentity,
  Skill,
  PackMetadata,
  PackValidationResult,
  PackValidationErrorItem,
  PackValidationWarningItem,
  SystemPrompt,
  PromptSection,
  PackLoaderConfig,
  AssemblyRules,
} from './types.js';

// Errors
export {
  PackError,
  PackValidationError,
  PackNotFoundError,
  MissingRequiredFileError,
  SkillLoadError,
} from './errors.js';

// Validator
export {
  PackValidator,
  IPackValidator,
  validatePack,
  validatePackSync,
  packValidator,
} from './validator.js';

// Loader
export {
  PackLoader,
  IPackLoader,
  loadPack,
  loadSkills,
  parseAgentIdentity,
  packLoader,
  DEFAULT_LOADER_CONFIG,
} from './loader.js';

// Assembler
export {
  SystemPromptAssembler,
  ISystemPromptAssembler,
  assembleSystemPrompt,
  systemPromptAssembler,
  DEFAULT_ASSEMBLY_RULES,
} from './assembler.js';
