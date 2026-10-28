/**
 * Credential lookups for the CodeRAG Host plugin.
 *
 * The cloud embedding key lives in DSH's credentials service under the fixed
 * reference {@link SEMANTIC_KEY_REF}; the settings page writes it through the
 * credentials Remote and the Host reads it here to hand it to the MCP child and
 * the admin CLI. No other component may read or render the value.
 *
 * The result distinguishes the three states the callers need:
 * - `available: false` — no provider / provider failure: keep whatever value the
 *   MCP row already has (do not silently delete a key because the provider is
 *   temporarily down);
 * - `available: true, value: string` — configured: use it;
 * - `available: true, value: undefined` — the provider answered and the key is
 *   not configured: callers must clear the row's stale key.
 */

import { SEMANTIC_KEY_REF } from '../shared/admin-protocol.js'

/**
 * Resolve the cloud API key fact for one Host call.
 * @param {import('@deepseek-ai/cordis').Context} ctx - a context that can reach the credentials provider.
 * @returns {Promise<{ available: boolean, value?: string }>} the fact; never throws.
 */
export async function resolveCredential(ctx) {
  const credentials = ctx.get('credentials')
  if (credentials === undefined || typeof credentials.resolve !== 'function') return { available: false }
  try {
    const resolved = await credentials.resolve(SEMANTIC_KEY_REF)
    const value = resolved?.value
    return {
      available: true,
      value: typeof value === 'string' && value !== '' ? value : undefined,
    }
  } catch {
    // A provider that is mounted but refuses is treated as unavailable: the
    // existing MCP env must survive a transient credentials failure.
    return { available: false }
  }
}
