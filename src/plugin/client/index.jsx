/**
 * dsh-coderag — browser half of the native settings page.
 *
 * T5-02 placeholder: proves the lazy-CJS factory packaging (`window.__
 * ModuleLoader__.load`). The `plugins.row.config` form is implemented in T5-04.
 */

/** Client services this plugin reads; both are part of the DSH client baseline. */
export const inject = ['slots']

/**
 * Register the settings page contributions.
 * @param {import('@deepseek-ai/cordis').Context} ctx - the browser plugin context.
 */
export function apply(ctx) {
  // T5-04 registers `plugins.row.config` here. Keep the skeleton side-effect free.
  void ctx
}
