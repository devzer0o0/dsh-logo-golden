/**
 * Standalone tsdown config for the brand-gold plugin.
 *
 * The shared client-bundle preset that every plugin of the dsh-web family uses
 * is vendored under `build/` (it is the repository-wide single source of truth
 * there, and this repository is a standalone distribution of one package):
 * closure-factory artifact for window.__ModuleLoader__, CSS Modules inlined,
 * externals resolved through the loader module table. The node half carries no
 * behavior; types ship from lib/types (tsc).
 */
import { clientBundle } from './build/tsdown.client.ts'

export default clientBundle('@linxin666/dsh-client-ui-brand-gold', ['src/index.ts'])
