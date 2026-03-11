---
# minerva-izp3
title: Implement LLM environment variable configuration
status: completed
type: task
priority: normal
created_at: 2026-03-10T09:28:56Z
updated_at: 2026-03-11T06:50:29Z
---

Implement tasks from OpenSpec change 'support-llm-env-variables' to add environment variable support for LLM configuration with validation and NestJS integration.



## Summary of Changes

### Completed Implementation

**1. Setup (1.1-1.3)**
- Verified @mariozechner/pi-ai package is in package.json
- Verified zod validation library is present
- Created src/config/llm.config.ts with LlmConfig class

**2. Configuration Implementation (2.1-2.6)**
- Created LlmConfig class with @Injectable() decorator
- Added validation for LLM_BASE_URL (valid URL via zod)
- Added validation for LLM_API_KEY (non-empty string)
- Added validation for LLM_MODEL (non-empty string)
- Implemented fail-fast validation at startup via LlmConfig.fromEnv()
- Created createModel() method generating custom Model object for pi-mono ai package

**3. NestJS Integration (3.1-3.3)**
- Created LlmConfigModule with @Global() decorator
- Exported LLM_CONFIG provider using Symbol
- Imported LlmConfigModule in main AppModule

**4. Security (4.1-4.2)**
- LLM_API_KEY is never logged
- API key only accessible via getApiKey() method
- No class-transformer @Exclude() needed (not using class-transformer)

**5. Testing (5.1-5.6)**
- Unit tests for LlmConfig validation logic
- Unit tests for custom Model object creation
- Integration tests for startup with valid env vars
- Integration tests for startup failure with missing vars
- Integration tests for startup failure with invalid LLM_BASE_URL
- Integration tests for using custom model with pi-mono ai package

**6. Documentation (6.1-6.3)**
- Updated README.md with LLM configuration section
- Updated .env.example with three required variables
- Documented error messages and troubleshooting

### Files Modified/Created
- src/config/llm.config.ts (new)
- src/config/llm-config.constants.ts (new)
- src/config/llm-config.module.ts (new)
- src/app.module.ts (modified)
- tests/unit/config/llm.config.test.ts (new)
- tests/integration/llm-config.test.ts (new)
- README.md (updated)
- .env.example (updated)
