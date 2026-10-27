/**
 * dsh-coderag — host half of the native settings page.
 *
 * T5-02 placeholder: this entry point exists so the build pipeline can emit
 * `lib/index.js`. The Config and the MCP-row sync are implemented in T5-03.
 */

import z from '@deepseek-ai/schemastery'

export const name = 'dsh-coderag'
export const inject = ['loader']

export const Config = z.object({
  root: z.string().default('').volatile(),
  maxFiles: z.natural().default(0).volatile(),
  maxFileBytes: z.natural().default(0).volatile(),
  extraExtensions: z.string().default('').volatile(),
  semantic: z.boolean().default(false).volatile(),
  semanticBackend: z.union([z.const(''), z.const('ollama'), z.const('openai')]).default('').volatile(),
  semanticUrl: z.string().default('').volatile(),
  semanticModel: z.string().default('').volatile(),
  semanticTimeout: z.natural().default(0).volatile(),
  semanticBatch: z.natural().default(0).volatile(),
})

export function apply() {}
