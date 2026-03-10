## 1. Setup

- [x] 1.1 Add `@mariozechner/pi-ai` package to package.json
- [x] 1.2 Add validation library (Joi or class-validator) to package.json if not present
- [x] 1.3 Create `src/config/llm.config.ts` configuration file

## 2. Configuration Implementation

- [x] 2.1 Create `LlmConfig` class with `@Injectable()` decorator for NestJS
- [x] 2.2 Add validation for `LLM_BASE_URL` (must be valid URL)
- [x] 2.3 Add validation for `LLM_API_KEY` (must be non-empty string)
- [x] 2.4 Add validation for `LLM_MODEL` (must be non-empty string)
- [x] 2.5 Implement fail-fast validation at startup
- [x] 2.6 Create method to generate custom Model object for pi-mono ai package

## 3. NestJS Integration

- [x] 3.1 Create `LlmConfigModule` to register the configuration
- [x] 3.2 Export `LlmConfig` provider from the module
- [x] 3.3 Import `LlmConfigModule` in the main AppModule

## 4. Security

- [x] 4.1 Ensure `LLM_API_KEY` is never logged
- [x] 4.2 Add `@Exclude()` decorator if using class-transformer (not needed - no class-transformer usage)

## 5. Testing

- [x] 5.1 Write unit tests for `LlmConfig` validation logic
- [x] 5.2 Write unit tests for custom Model object creation
- [x] 5.3 Write integration test for startup with valid environment variables
- [x] 5.4 Write integration test for startup failure with missing environment variables
- [x] 5.5 Write integration test for startup failure with invalid `LLM_BASE_URL`
- [x] 5.6 Write integration test for using custom model with pi-mono ai package

## 6. Documentation

- [x] 6.1 Update README.md with environment variable configuration instructions
- [x] 6.2 Add `.env.example` file with the three required variables
- [x] 6.3 Document error messages and troubleshooting
