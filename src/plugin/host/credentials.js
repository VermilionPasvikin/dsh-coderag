/**
 * Credential lookups for the CodeRAG Host plugin.
 *
 * The cloud embedding key lives in DSH's credentials service under the fixed
 * reference {@link SEMANTIC_KEY_REF}; the settings page writes it through the
 * credentials Remote and the Host reads it here to hand it to the MCP child and
 * the admin CLI. No other component may read or render the value.
 *
 * The provider is optional: a deployment without a credentials mount keeps
 * working (the key simply stays absent), so lookups degrade to `undefined`
 * instead of failing the plugin.
 */

import { SEMANTIC_KEY_REF } from '../shared/admin-protocol.js'

/**
 * Resolve the cloud API key for one Host call.
 * @param {import('@deepseek-ai/cordis').Context} ctx - a context that can reach the credentials provider.
 * @returns {Promise<string | undefined>} the key, or undefined when the provider is absent or unset.
 */
export async function resolveApiKey(ctx) {
  const credentials = ctx.get('credentials')
  if (credentials === undefined || typeof credentials.resolve !== 'function') return undefined
  const resolved = await credentials.resolve(SEMANTIC_KEY_REF)
  const value = resolved?.value
  return typeof value === 'string' && value !== '' ? value : undefined
}
