# Deployment Security Checklist

Items that cannot be implemented in application code and must be addressed at deployment time or later.
Items already fixed in code are **not** listed here — see git history for those changes.

---

## Before Any Public Deployment

### TLS / HTTPS

- [x] Configure TLS termination (Certbot/Let's Encrypt or a load balancer cert). Live in production via Let's Encrypt — see [VM_DEPLOYMENT.md](VM_DEPLOYMENT.md#ssl-with-lets-encrypt).
- [x] Once TLS is live, add `Strict-Transport-Security` to `nginx/nginx.conf` — present in `nginx/nginx.conf`.
- [x] Redirect all HTTP traffic to HTTPS — present in `nginx/nginx.conf` (`listen 80; return 301 https://$host$request_uri;`).

### Environment Variables

- [ ] Set `ENVIRONMENT=production` (public API docs off, `Secure` session cookie, wildcard CORS refused).
- [ ] Set `FRONTEND_ORIGIN=https://yourdomain.com` — the API refuses to start with a wildcard in non-local mode, and Turnstile checks tokens against its hostname.
- [ ] Rotate `POSTGRES_PASSWORD` from the `.env.example` placeholder to a 32+ character random password (e.g. `openssl rand -hex 32`). Compose has no fallback and refuses to start without one.
- [ ] Ensure `.env.local` and `.env.non-docker.local` are never committed — `.gitignore` covers them but double-check with `git ls-files | grep env`.
- [ ] Consider a secrets manager (AWS Secrets Manager, GCP Secret Manager, or Docker Secrets) instead of flat `.env` files for production credentials.

### Database

- [x] The database port is published on `127.0.0.1` only (`docker-compose.yml`), so it isn't reachable from the internet even if the cloud firewall changes.
- [ ] Create the API and pipeline roles (`sql/app_roles.sql`, steps in [VM_DEPLOYMENT.md](VM_DEPLOYMENT.md#database-roles)) and set `API_DB_*` / `PIPELINE_DB_*`. Until then both connect as the owner.
- [ ] Create a read-only DB user for any future read-replica or analytics access.

---

## Restrict Admin Surface Area

### Prefect UI

The Prefect UI (`/prefect/`) is the owner's only (the role is re-checked against the database on every request), but is still reachable over the public internet. A compromised owner account exposes pipeline controls and execution logs.

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

- [x] `nginx/nginx.conf` sends a Content-Security-Policy (scripts from this site, Turnstile, and the inline theme script by hash; `backend/tests/unit/deploy_config_test.py` keeps the hash in step). If you add a third-party script, font host or API the browser calls, add it there. To diagnose a blocked resource, the browser console names the directive.

---

## Auth0 Configuration

- [ ] **Enforce MFA** for moderator and owner roles: Auth0 Dashboard → Security → Multi-factor Authentication → enable for users with elevated roles, or use Actions to enforce conditionally.
- [ ] **Restrict sign-up**: If this is invite-only, disable public sign-up in Auth0 and use invitations instead. Otherwise, any email address can register and obtain a `user`-level token.
- [ ] **Token expiry**: Verify the Auth0 access token lifetime is ≤ 24 hours (default is 86400s — acceptable, but confirm it matches your threat model).
- [ ] **Allowed callback/logout URLs**: Lock these down to only your production domain in the Auth0 application settings.

---

## Submission Spam Protection

- [x] The feedback form (`/submissions/feedback`, `/submissions/scores`) checks Cloudflare Turnstile server-side (failing closed if Cloudflare is down), plus a honeypot, per-visitor and daily limits, duplicate suppression and a queue circuit breaker.
- [x] The asset and data submissions (logos, helmets, colors, locations, helmet assignments) require a signed-in account, with a per-account daily cap; uploads are checked to be real images, and rejected ones are deleted from Cloudinary.

---

## CDN / Edge Security (Optional but Recommended)

- [ ] Place Cloudflare (or equivalent) in front of the origin. This adds:
  - A second layer of rate limiting at the network edge
  - Bot Fight Mode to block automated scanners before they reach the API
  - DDoS mitigation for the public analytics endpoints
  - Free SSL/TLS management

---

## Ongoing

- [x] **Pinned builds**: images by digest, Python packages from `uv.lock` with hashes checked.
- [ ] **Dependency scanning**: `.github/dependabot.yml` is in the repo; turn on Dependabot alerts and security updates in GitHub (Settings → Code security), along with secret scanning + push protection, CodeQL default setup, and private vulnerability reporting (see `SECURITY.md`).
- [ ] **Log aggregation**: Ship structured logs (the `_log.info(...)` calls in the admin and moderation routers) to a centralized service (Datadog, Loki, CloudWatch) so admin action history is queryable and alertable.
- [ ] **DB backup**: schedule `scripts/backup_db.sh` with cron and turn on Lightsail automatic snapshots ([VM_DEPLOYMENT.md](VM_DEPLOYMENT.md#backups)). Test a restore once.
- [x] **Contact-email retention**: the daily digest flow removes the email from feedback decided more than 90 days ago.
- [ ] **Incident response**: Document what to do if Cloudinary credentials are leaked (regenerate API key in Cloudinary console, rotate `CLOUDINARY_API_KEY`/`CLOUDINARY_API_SECRET` in all deployment configs, restart API containers).
