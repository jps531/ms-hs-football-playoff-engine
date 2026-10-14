// The site's public client config from the API: Turnstile's site key and the
// moderation page's Auth0 app. Fetched once per page; {} when unavailable.

let config = null;

export function clientConfig(api) {
  config ??= fetch(`${api}/client-config`, { headers: { Accept: "application/json" } })
    .then((r) => (r.ok ? r.json() : {}))
    .catch(() => ({}));
  return config;
}
