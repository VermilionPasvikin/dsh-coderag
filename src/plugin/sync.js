/**
 * MCP-row synchronization for the dsh-coderag settings page.
 *
 * The settings row (`coderag`) owns the editable values; the MCP client row
 * (`mcp-coderag`) owns the stdio child process. Changing `config.env` on the
 * MCP row is an ordinary (non-volatile) Loader config change, so the Loader
 * remounts that row and `@deepseek-ai/dsh-mcp-client` spawns the Python engine
 * again with the new environment. `docs/settings-ui-plan.md` records the
 * measurements behind that claim.
 *
 * Not responsible for: validating the settings schema, reading the settings
 * namespace, or persisting anything. The update stays in memory: the profile
 * patch is written only by DSH's settings service, for the `coderag` row.
 */

import { MCP_ROW_ID, envPlan, mergeOwnedEnv } from './shared/settings.js'
import { SEMANTIC_KEY_REF } from './shared/admin-protocol.js'

/**
 * Find the MCP client row in the running Loader tree.
 * @param {{ entries(): Generator<{ options: { id?: string } }> } | undefined} loader - the Loader service.
 * @returns {object | undefined} the entry, or undefined when the row is absent.
 */
export function findMCPEntry(loader) {
  if (loader === undefined || typeof loader.entries !== 'function') return undefined
  for (const entry of loader.entries()) {
    if (entry?.options?.id === MCP_ROW_ID) return entry
  }
  return undefined
}

/**
 * Whether the owned variables of an environment differ from the desired plan.
 * Unrelated variables are ignored on purpose: the plugin must preserve them.
 * @param {Record<string, unknown> | undefined} env - current environment.
 * @param {{ set: Record<string, string>, remove: string[] }} plan - desired owned variables.
 * @returns {boolean} true when an owned variable must change.
 */
export function ownedEnvMismatch(env, plan) {
  const source = env !== null && typeof env === 'object' ? env : {}
  for (const name of plan.remove) {
    if (source[name] !== undefined) return true
  }
  for (const [name, value] of Object.entries(plan.set)) {
    if (source[name] !== value) return true
  }
  return false
}

/**
 * Read the env object of a raw MCP row config.
 * @param {unknown} config - raw `entry.options.config`.
 * @returns {Record<string, unknown>} the env object (empty when absent).
 */
function rawEnv(config) {
  if (config === null || typeof config !== 'object') return {}
  const env = Reflect.get(config, 'env')
  return env !== null && typeof env === 'object' && !Array.isArray(env) ? screenEnv(env) : {}
}

/**
 * Copy an env object without prototype noise.
 * @param {Record<string, unknown>} env - candidate env.
 * @returns {Record<string, unknown>} a shallow copy.
 */
function screenEnv(env) {
  return { ...env }
}

/**
 * Push the settings values into the MCP row's environment.
 *
 * Update order:
 * 1. write the merged env into the entry options (this also wakes a row that is
 *    still importing, because `entry.update` joins its init task);
 * 2. wait for the mount to settle and compare the env the plugin actually
 *    received; a change that raced with the first import is forced once with
 *    `fiber.update(config, true)` so the Python child really restarts;
 * 3. leave unrelated env variables untouched.
 *
 * @param {object} entry - the MCP row's Loader entry.
 * @param {Record<string, unknown>} values - normalized settings values.
 * @param {{ apiKey?: string }} [options] - resolved cloud key; omitted keeps the row's current value.
 * @returns {Promise<'unchanged' | 'synced' | 'forced'>} what happened.
 */
export async function syncMCPRow(entry, values, options = {}) {
  const plan = envPlan(values)
  const apiKey = options.apiKey
  // The key is not a schema field: it is resolved from the credentials service
  // on every sync and only ever travels into the child environment. An absent
  // lookup (provider missing/unset) leaves whatever the row already had.
  if (typeof apiKey === 'string' && apiKey !== '') plan.set[SEMANTIC_KEY_REF] = apiKey
  const nextEnv = mergeOwnedEnv(rawEnv(entry.options?.config), values)
  if (typeof apiKey === 'string' && apiKey !== '') nextEnv[SEMANTIC_KEY_REF] = apiKey
  const rawChanged = ownedEnvMismatch(rawEnv(entry.options?.config), plan)
  const liveEnv = () => (entry.fiber !== undefined ? entry.fiber.config?.env : undefined)
  const liveChanged = entry.fiber !== undefined && entry.fiber.config !== undefined
    && ownedEnvMismatch(liveEnv(), plan)
  if (!rawChanged && !liveChanged) return 'unchanged'

  const nextConfig = { ...(entry.options?.config ?? {}), env: nextEnv }
  await entry.update({ config: nextConfig })
  if (entry.fiber === undefined) return 'synced'
  await entry.fiber.await()
  if (!entry.fiber.config || !ownedEnvMismatch(liveEnv(), plan)) return 'synced'

  // The row imported before this update could reach it; restart it explicitly
  // with the config the entry already holds, without persisting anything.
  entry.fiber.update(nextConfig, true)
  await entry.fiber.await()
  return 'forced'
}
