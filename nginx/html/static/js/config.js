// The site's public client config from the API (GET /client-config): Turnstile's
// site key, the moderation page's Auth0 app, the API docs path, the PostHog key
// and the owner's dashboard links. Fetched once per page; {} when unavailable.

let config = null;

export function clientConfig(api) {
  config ??= fetch(`${api}/client-config`, { headers: { Accept: "application/json" } })
    .then((r) => (r.ok ? r.json() : {}))
    .catch(() => ({}));
  return config;
}
