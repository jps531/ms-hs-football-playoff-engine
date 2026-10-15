# Production / VM Deployment (AWS Lightsail)

This project is deployed on an AWS Lightsail Ubuntu instance (`mshsfootball.com`). On an x86_64 Linux VM the API runs in Docker normally — no Apple Silicon crypto limitation.

## One-time instance setup

1. Create a Lightsail instance: **Linux/Unix → OS Only → Ubuntu 22.04 LTS**, General purpose, 4 GB RAM minimum. Assign a static IP immediately after creation (first one is free).

2. Open firewall ports in the Lightsail **Networking** tab: HTTP (80) and HTTPS (443). SSH (22) is open by default.

3. Upload your Mac's public SSH key (`~/.ssh/id_ed25519.pub`) during instance creation so you can SSH from Terminal:
   ```
   ssh ubuntu@YOUR_STATIC_IP
   ```

4. Install Docker:
   ```
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker ubuntu
   ```
   Log out and back in for the group change to take effect.

5. Add a GitHub deploy key so the VM can clone the private repo:
   ```
   ssh-keygen -t ed25519 -C "lightsail-football" -f ~/.ssh/github_deploy
   cat ~/.ssh/github_deploy.pub   # add this to GitHub → Settings → SSH keys
   cat >> ~/.ssh/config << 'EOF'
   Host github.com
       IdentityFile ~/.ssh/github_deploy
       IdentitiesOnly yes
   EOF
   ```

6. Clone the repo:
   ```
   git clone git@github.com:jps531/ms-hs-football-playoff-engine.git
   cd ms-hs-football-playoff-engine
   ```

## Domain and DNS

The domain `mshsfootball.com` is registered and its DNS zone is managed in Lightsail (**Networking → DNS zones**) with an A record pointing to the static IP. The domain is also assigned to the instance under the **Domains** tab.

## Environment and first deploy

Copy and fill in the environment file:
```
cp .env.example .env.local
nano .env.local
```

Key values to set:
- `POSTGRES_HOST=db` — uses Docker's internal service name (PostgreSQL runs in the same stack)
- `POSTGRES_PASSWORD` — generate with `openssl rand -base64 32`
- `CLOUDINARY_*` — from your Cloudinary dashboard
- `CLOUDINARY_BASE_URL` — hardcode the full URL: `https://res.cloudinary.com/YOUR_CLOUD_NAME/image/upload`
- `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` — from your Auth0 dashboard (same tenant as local dev)
- `FRONTEND_ORIGIN=https://mshsfootball.com`

Then bring up the stack (PostgreSQL runs in Docker alongside the other services):
```
docker compose --env-file .env.local --profile local-db up --build -d
```

## SSL with Let's Encrypt

HTTPS is live in production via this setup (Certbot-issued Let's Encrypt cert, HSTS header, and HTTP→HTTPS redirect in `nginx/nginx.conf`).

Renewals run in **webroot** mode: Certbot drops a challenge token in `/var/www/certbot` on the host, and nginx (which mounts that directory read-only) serves it on port 80 ahead of the HTTPS redirect. nginx keeps running the whole time, so Certbot's timer can renew unattended.

### First certificate (new instance)

nginx won't start until certificate files exist, so the very first certificate is issued in standalone mode with the stack down:

```
docker compose --env-file .env.local --profile local-db down
sudo apt install certbot -y
sudo certbot certonly --standalone -d mshsfootball.com
```

### Switch renewals to webroot

Create the webroot, bring the stack up, and re-issue once through it. That records webroot as the renewal method in `/etc/letsencrypt/renewal/mshsfootball.com.conf`:

```
sudo mkdir -p /var/www/certbot
docker compose --env-file .env.local --profile local-db up --build -d
sudo certbot certonly --webroot -w /var/www/certbot --cert-name mshsfootball.com \
  -d mshsfootball.com --force-renewal
```

The same command repairs an instance whose certificate has already expired: nginx starts fine with an expired certificate, and the challenge is served over plain HTTP.

### Adding www (optional)

`nginx.conf` answers for `www.mshsfootball.com`, but the certificate only covers it once DNS does. Add an A record for `www` pointing at the static IP, wait until `dig +short www.mshsfootball.com` returns it, then re-run the webroot command above with `-d www.mshsfootball.com` added. Certbot validates every name or none, so a `www` without DNS fails the whole request (`NXDOMAIN looking up A`).

### Reload nginx after each renewal

nginx only reads certificates at startup or reload. The nginx container is named `nginx_<ENVIRONMENT>`, so the hook finds it by prefix rather than hard-coding a name:

```
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh << 'HOOK'
#!/bin/bash
docker ps -q --filter "name=^nginx_" | xargs -r -I{} docker exec {} nginx -s reload
HOOK
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

If you added `pre`/`post` hooks that stop and start nginx for standalone renewals, delete them; webroot doesn't need port 80 to itself.

### Verify

```
sudo certbot renew --dry-run          # should succeed through the webroot
systemctl list-timers | grep certbot  # the apt package's twice-daily renewal timer
echo | openssl s_client -connect mshsfootball.com:443 -servername mshsfootball.com 2>/dev/null \
  | openssl x509 -noout -enddate -ext subjectAltName
```

## Auth0 URL updates

In Auth0 → Applications → Your Application → Settings, add `https://mshsfootball.com` to each field alongside the existing localhost entries (comma-separated):

- **Allowed Callback URLs:** `http://localhost:8000/docs/oauth2-redirect, https://mshsfootball.com/docs/oauth2-redirect`
- **Allowed Web Origins:** `http://localhost:8000, https://mshsfootball.com`
- **Allowed Logout URLs:** `http://localhost:8000, https://mshsfootball.com`

`AUTH0_AUDIENCE` is the **Identifier** value from Auth0 → Applications → APIs → your API.

## Deploying updates

```
git pull
docker compose --env-file .env.local --profile local-db up --build -d
```

If the pull changed `nginx/nginx.conf`, also recreate nginx. The config is bind-mounted as a single file, and `git pull` replaces that file rather than editing it, so a running container (and `nginx -s reload`) can keep seeing the old copy:

```
docker compose --env-file .env.local --profile local-db up -d --force-recreate nginx
```

Required env vars: `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, all `POSTGRES_*`, `CLOUDINARY_*`, `FRONTEND_ORIGIN`.
Optional: `AUTH0_SPA_CLIENT_ID`, `TURNSTILE_*`, `SMTP_*`, `DIGEST_TO` (see below).

## Share cards (link previews)

Each morning, after the region update, the Prefect worker draws a link-preview
card and meta tags for every region, class and bracket page, and for every
team (a region or bracket link with `?team=<slug>`, the URL the app shows when
a team is picked)
(`backend/prefect/share_assets_pipeline.py`). It reads the site's own API and
writes into the `share-assets` volume, which nginx serves at `/static/og/` and
splices into each page's `<head>` with a server-side include. Until a page has
its own, it gets the generic tags in `index.html`.

The same run writes each region and class page's content as static HTML
(`body/*.html`: the headline, standings table, remaining games, what each team
needs, and the snapshot line), plus a front-page index and `sitemap.xml`.
nginx includes a page's content inside `<main>`, so search engines and
browsers without JavaScript get the real race; the app replaces it on load.
Links to an older week, season or odds mode skip it, since the latest snapshot
would be the wrong one. `robots.txt` (in `nginx/html`) points crawlers at the
sitemap.

To redraw them by hand (after a deploy, or after rerunning a pipeline), run the
`share-assets` deployment from the Prefect UI. To check one:

```
curl -s https://mshsfootball.com/standings/3a/6 | grep -E '<title>|og:image"'
curl -s 'https://mshsfootball.com/standings/3a/6?team=raleigh' | grep -E '<title>|og:image"'
curl -s 'https://mshsfootball.com/brackets/3a?team=raleigh' | grep -E '<title>|og:image"'
# Page content, as a crawler (or a browser without JavaScript) gets it:
curl -s https://mshsfootball.com/standings/3a/6 | sed -n '/<main/,/<\/main>/p' | sed 's/<[^>]*>/ /g' | tr -s ' ' | head -c 600; echo
curl -s https://mshsfootball.com/sitemap.xml | head -5
```

Facebook caches previews; its Sharing Debugger ("Scrape Again") refreshes one.
Card URLs carry the snapshot date (`?v=20261009`), so a new day's card is a new
URL and is fetched fresh.

## Feedback, moderation and spam protection

The feedback form (`/feedback`, and the "Wrong score?" and "Tell us" links) files
submissions into the moderation queue. Moderators review them at `/moderate`, and
a daily email lists what came in. Each piece below is off until it's configured.

### Moderation page (`/moderate`)

The page signs in with Auth0 directly from the browser (authorization code + PKCE),
so it needs its own Auth0 application:

1. Auth0 → Applications → **Create Application** → **Single Page Web Applications**
   (name it e.g. "MSHSF moderation").
2. In its Settings:
   - **Allowed Callback URLs:** `https://mshsfootball.com/moderate`
   - **Allowed Logout URLs:** `https://mshsfootball.com/moderate`
   - **Allowed Web Origins:** `https://mshsfootball.com`
   - Add the `http://localhost` equivalents if you test locally.
3. Authorize the app for your API: Applications → APIs → your API →
   **Application Access** (older dashboards: **Machine to Machine Applications**),
   find the new app and set **User Access** to **Authorized** (older dashboards:
   turn its toggle on). No scopes are needed. Skipping this gives
   `Client "…" is not authorized to access resource server "…"` on sign-in.
4. Put its **Client ID** in `.env.local` as `AUTH0_SPA_CLIENT_ID` and recreate the API.

Only users whose row in `users` has role `moderator` or `owner` see the queue. A
user row is created on first sign-in; promote it with:

```
UPDATE users SET role = 'moderator' WHERE email = 'someone@example.com';
```

Signing in also sets the session cookie the Prefect UI link uses, so the page's
"Prefect" link opens without a Bearer header.

### Turnstile (spam check on the form)

1. Cloudflare dashboard → **Turnstile** → **Add widget**. Hostname
   `mshsfootball.com`, widget mode **Managed** (the form keeps it invisible unless
   Cloudflare wants a click). The site doesn't have to be proxied by Cloudflare.
2. Set `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY` in `.env.local` and recreate
   the API. With no secret set, the form doesn't load the widget and the API
   doesn't check tokens.

If Cloudflare's verify endpoint is unreachable, submissions are let through (and
logged) rather than refused; the rate limits and queue cap still apply. A visitor
whose content blocker stops the widget loading is told to allow
`challenges.cloudflare.com`.

### Daily digest email

The `submission-digest` deployment runs at 7:00 America/Chicago and emails
`DIGEST_TO` a reminder whenever anything is waiting for a decision (pending, or a
logo accepted but still needing its asset): what came in since yesterday first,
then everything older that's still open, with how long it has waited, and a link
to `/moderate`. Once the queue is clear it stops sending. Configure SMTP for the Prefect worker:

| Provider | `SMTP_HOST` | `SMTP_PORT` | `SMTP_USERNAME` / `SMTP_PASSWORD` |
|---|---|---|---|
| Gmail (needs 2-step verification) | `smtp.gmail.com` | `587` | your address / an [app password](https://myaccount.google.com/apppasswords) |
| Resend | `smtp.resend.com` | `465` | `resend` / an API key |
| Amazon SES | `email-smtp.<region>.amazonaws.com` | `587` | SES SMTP credentials |

Set `SMTP_FROM` when the From address differs from the login (Resend, SES), then
recreate the worker. To test, run the `submission-digest` deployment from the
Prefect UI; without SMTP settings it logs the email it would have sent.

### Rate limits

- nginx: every API request is limited to 10 a second per IP, with a burst of 60
  (a page load makes at most 6). `/api/v1/submissions/` is also limited to 10 a
  minute, with a burst of 5. Both return JSON 429s.
- API: the feedback and score forms allow 5 a minute and 30 a day per IP, ignore
  repeats of a pending report, and refuse new ones (503) past 300 pending in an
  hour. A filled honeypot field gets a fake success.
