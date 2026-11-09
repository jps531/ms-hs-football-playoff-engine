// Feature flags (backend/helpers/feature_flags.py): whether a part of a page that ships switched off is
// on for this viewer. The server says which are (client-config's `features`): those on for everyone,
// and in the owner's browser, those on for the owner only too. Nothing is stored in the browser to pick
// them. A flag the server doesn't list, or a config that couldn't load, is off.
//
//   import { feature } from "./features.js";
//   if (await feature("new_bracket_view")) { ... }

import { clientConfig } from "./config.js";

/** Whether *name* is in a client config's list of flags on (false for a config without one). */
export function isOn(config, name) {
  return Array.isArray(config?.features) && config.features.includes(name);
}

/** Whether the flag *name* is on for this viewer. */
export async function feature(name, api = "/api/v1") {
  return isOn(await clientConfig(api), name);
}
