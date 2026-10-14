// Moderator sign-in with Auth0: the authorization-code flow with PKCE, which
// is what Auth0 recommends for a page with no server-side session of its own.
//
// signIn() sends the browser to Auth0 with a fresh code challenge. Auth0 sends
// it back to /moderate?code=…&state=…, where completeSignIn() checks the state
// and trades the code (with its verifier) for an access token. The token lives
// in sessionStorage, so it lasts as long as the tab and is gone when it closes.

const TOKEN_KEY = "mshsf.mod.token";
const PENDING_KEY = "mshsf.mod.pkce";
const EXPIRY_SLACK_MS = 60_000; // treat a token as expired a minute early

export function base64url(bytes) {
  let text = "";
  for (const b of bytes) text += String.fromCharCode(b);
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function randomString(bytes = 32) {
  return base64url(crypto.getRandomValues(new Uint8Array(bytes)));
}

/** The S256 code challenge for a PKCE verifier. */
export async function challengeFor(verifier) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

export function authorizeUrl(cfg, { redirectUri, state, challenge }) {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: cfg.auth0_client_id,
    redirect_uri: redirectUri,
    audience: cfg.auth0_audience,
    scope: "openid profile email",
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  return `https://${cfg.auth0_domain}/authorize?${params}`;
}

export function tokenRequest(cfg, { code, verifier, redirectUri }) {
  return {
    url: `https://${cfg.auth0_domain}/oauth/token`,
    body: {
      grant_type: "authorization_code",
      client_id: cfg.auth0_client_id,
      code,
      code_verifier: verifier,
      redirect_uri: redirectUri,
    },
  };
}

export function logoutUrl(cfg, returnTo) {
  const params = new URLSearchParams({ client_id: cfg.auth0_client_id, returnTo });
  return `https://${cfg.auth0_domain}/v2/logout?${params}`;
}

/** The stored access token if it hasn't expired, else null. */
export function storedToken(storage, now = Date.now()) {
  try {
    const saved = JSON.parse(storage.getItem(TOKEN_KEY) ?? "null");
    if (saved?.token && saved.expiresAt - EXPIRY_SLACK_MS > now) return saved.token;
  } catch {
    /* unreadable: treat as signed out */
  }
  return null;
}

export function saveToken(storage, token, expiresInSeconds, now = Date.now()) {
  storage.setItem(TOKEN_KEY, JSON.stringify({ token, expiresAt: now + expiresInSeconds * 1000 }));
}

export function forgetToken(storage) {
  storage.removeItem(TOKEN_KEY);
}

/** Auth0's error text, with the fix added for the one setup mistake it doesn't explain. */
export function explainAuthError(text) {
  if (/not authorized to access resource server/i.test(text ?? "")) {
    return `${text} In Auth0, open Applications → APIs → your API → Application Access and authorize this application for user access.`;
  }
  return text;
}

/** Send the browser to Auth0's sign-in page. */
export async function signIn(cfg, redirectUri, storage = sessionStorage) {
  const verifier = randomString(48);
  const state = randomString(16);
  storage.setItem(PENDING_KEY, JSON.stringify({ verifier, state }));
  location.assign(authorizeUrl(cfg, { redirectUri, state, challenge: await challengeFor(verifier) }));
}

/**
 * Finish a sign-in from the URL Auth0 returned to. Returns the access token,
 * or throws an Error whose message can be shown. Leaves storage tidy either way.
 */
export async function completeSignIn(cfg, redirectUri, url, storage = sessionStorage, fetcher = fetch) {
  const params = new URL(url).searchParams;
  const pending = JSON.parse(storage.getItem(PENDING_KEY) ?? "null");
  storage.removeItem(PENDING_KEY);
  if (params.get("error")) throw new Error(explainAuthError(params.get("error_description") || params.get("error")));
  if (!pending || params.get("state") !== pending.state) throw new Error("That sign-in link was stale. Please sign in again.");
  const { url: tokenUrl, body } = tokenRequest(cfg, { code: params.get("code"), verifier: pending.verifier, redirectUri });
  const res = await fetcher(tokenUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.access_token) throw new Error(explainAuthError(data.error_description) || "Auth0 didn't return a token.");
  saveToken(storage, data.access_token, data.expires_in ?? 3600);
  return data.access_token;
}
