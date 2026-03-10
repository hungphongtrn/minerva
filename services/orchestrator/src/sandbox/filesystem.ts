import type { Sandbox } from '@daytonaio/sdk';
import type { DaytonaClient } from './daytona-client.js';
import type { FileReadOptions, FileWriteOptions } from './types.js';
import { validatePath } from './security.js';
import { PathTraversalError, FileTooLargeError } from './errors.js';

const DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

export class FilesystemService {
  constructor(
    private client: DaytonaClient,
    private maxFileSize: number = DEFAULT_MAX_FILE_SIZE
  ) {}

  async readFile(
    sandbox: Sandbox,
    userPath: string,
    options?: FileReadOptions
  ): Promise<string> {
    const rootPath = this.client.getWorkspaceRoot();
    
    // Validate path
    const validation = validatePath(userPath, rootPath);
    if (!validation.isValid) {
      throw new PathTraversalError(userPath, validation.error || 'Invalid path', sandbox.id);
    }

    const fullPath = `${rootPath}/${validation.normalizedPath}`;

    // Check file size before reading
    try {
      const fileInfo = await sandbox.fs.getFileDetails(fullPath);
      const maxSize = options?.maxSize || this.maxFileSize;
      
      if (fileInfo.size > maxSize) {
        throw new FileTooLargeError(userPath, fileInfo.size, maxSize, sandbox.id);
      }
    } catch (error) {
      // If we can't get file info, continue anyway - the read will fail if it doesn't exist
      if (error instanceof FileTooLargeError) {
        throw error;
      }
    }

    // Read the file
    const content = await this.client.readFile(sandbox, fullPath);
    return content;
  }

  async writeFile(
    sandbox: Sandbox,
    userPath: string,
    content: string,
    options?: FileWriteOptions
  ): Promise<void> {
    const rootPath = this.client.getWorkspaceRoot();

    // Validate path
    const validation = validatePath(userPath, rootPath);
    if (!validation.isValid) {
      throw new PathTraversalError(userPath, validation.error || 'Invalid path', sandbox.id);
    }

    // Check content size
    const contentSize = Buffer.byteLength(content, options?.encoding || 'utf8');
    if (contentSize > this.maxFileSize) {
      throw new FileTooLargeError(userPath, contentSize, this.maxFileSize, sandbox.id);
    }

    const fullPath = `${rootPath}/${validation.normalizedPath}`;

    // Create parent directories if requested
    if (options?.createDirs) {
      const dirPath = fullPath.substring(0, fullPath.lastIndexOf('/'));
      if (dirPath && dirPath !== rootPath) {
        try {
          await sandbox.fs.createFolder(dirPath, '755');
        } catch {
          // Directory might already exist, continue
        }
      }
    }

    // Write the file
    await this.client.writeFile(sandbox, fullPath, content);

    // Set permissions if specified
    if (options?.mode) {
      try {
        await sandbox.fs.setFilePermissions(fullPath, {
          mode: options.mode.toString(8),
        });
      } catch {
        // Ignore permission errors
      }
    }
  }
}
