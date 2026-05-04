# Deployment Security Checklist

Items that cannot be implemented in application code and must be addressed at deployment time or later.
Items already fixed in code are **not** listed here — see git history for those changes.

---

## Before Any Public Deployment

### TLS / HTTPS

- [ ] Configure TLS termination (Certbot/Let's Encrypt or a load balancer cert).
- [ ] Once TLS is live, add `Strict-Transport-Security` to `nginx/nginx.conf`:
  ```nginx
  add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
  ```
- [ ] Redirect all HTTP traffic to HTTPS:
  ```nginx
  server {
      listen 80;
      return 301 https://$host$request_uri;
  }
  ```

### Environment Variables

- [ ] Set `FRONTEND_ORIGIN=https://yourdomain.com` — the API refuses to start with a wildcard in non-local mode.
- [ ] Rotate `POSTGRES_PASSWORD` from the `.env.example` placeholder to a 32+ character random password (e.g. `openssl rand -base64 32`).
- [ ] Ensure `.env.local` and `.env.non-docker.local` are never committed — `.gitignore` covers them but double-check with `git ls-files | grep env`.
- [ ] Consider a secrets manager (AWS Secrets Manager, GCP Secret Manager, or Docker Secrets) instead of flat `.env` files for production credentials.

### Database

- [ ] The database port (`5432`) must **not** be exposed to the public internet. In `docker-compose.yml`, verify that `ports:` is absent from the `db` service (or bound to `127.0.0.1` only).
- [ ] Create a read-only DB user for any future read-replica or analytics access — the API user should have only the minimum permissions required.

---

## Restrict Admin Surface Area

### Prefect UI

The Prefect UI (`/prefect/`) is protected by moderator JWT auth, but is still reachable over the public internet. This means a compromised moderator account exposes pipeline controls and execution logs.

- [ ] **IP allowlist**: Restrict `/prefect/` and `/api/v1/admin/*` to a known IP range (office/VPN) via nginx `allow`/`deny`:
  ```nginx
  location /prefect/ {
      allow 203.0.113.0/24;  # replace with your IP range
      deny all;
      auth_request /internal/auth/verify-moderator;
      ...
  }
  ```
- [ ] Alternatively, place Prefect behind a VPN (WireGuard, Tailscale) and only allow VPN IPs.

### Content Security Policy

Once the frontend stack is finalized, add a `Content-Security-Policy` header tailored to the actual origins and script sources in use. A starter policy for an API-only backend:
```nginx
add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none';" always;
```

---

## Auth0 Configuration

- [ ] **Enforce MFA** for moderator and owner roles: Auth0 Dashboard → Security → Multi-factor Authentication → enable for users with elevated roles, or use Actions to enforce conditionally.
- [ ] **Restrict sign-up**: If this is invite-only, disable public sign-up in Auth0 and use invitations instead. Otherwise, any email address can register and obtain a `user`-level token.
- [ ] **Token expiry**: Verify the Auth0 access token lifetime is ≤ 24 hours (default is 86400s — acceptable, but confirm it matches your threat model).
- [ ] **Allowed callback/logout URLs**: Lock these down to only your production domain in the Auth0 application settings.

---

## Anonymous Submission Spam Protection

The `/api/v1/submissions/*` endpoints accept unauthenticated requests by design, but have no CAPTCHA. A motivated attacker can flood the moderation queue.

- [ ] Add Cloudflare Turnstile (or hCaptcha) to the frontend submission forms. The backend should validate the Turnstile token server-side before inserting into the submissions table.
  - Endpoint: `POST https://challenges.cloudflare.com/turnstile/v0/siteverify`
  - Add `turnstile_token: str` field to `SubmitColorsRequest`, `SubmitLocationRequest`, `SubmitScoreRequest`, `SubmitFeedbackRequest`, and the logo/helmet form bodies.
- [ ] Alternatively, consider requiring authentication for all submission types (sacrifice anonymous contributions for queue integrity).

---

## CDN / Edge Security (Optional but Recommended)

- [ ] Place Cloudflare (or equivalent) in front of the origin. This adds:
  - A second layer of rate limiting at the network edge
  - Bot Fight Mode to block automated scanners before they reach the API
  - DDoS mitigation for the public analytics endpoints
  - Free SSL/TLS management

---

## Ongoing

- [ ] **Dependency scanning**: Enable Dependabot (GitHub) or `uv audit` in CI to catch newly-disclosed CVEs in pinned dependencies.
- [ ] **Log aggregation**: Ship structured logs (the `_log.info(...)` calls added in admin/moderation routers) to a centralized service (Datadog, Loki, CloudWatch) so admin action history is queryable and alertable.
- [ ] **DB backup**: Set up automated PostgreSQL backups before going live. At minimum, `pg_dump` on a cron schedule to an offsite location.
- [ ] **Incident response**: Document what to do if Cloudinary credentials are leaked (regenerate API key in Cloudinary console, rotate `CLOUDINARY_API_KEY`/`CLOUDINARY_API_SECRET` in all deployment configs, restart API containers).
