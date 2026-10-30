# Production / VM Deployment (AWS Lightsail)

This project is deployed on an AWS Lightsail Ubuntu instance (`mshsfootball.com`). The server runs the production compose file on its own, without `docker-compose.local.yml`: nginx in front, on ports 80 and 443.

## One-time instance setup

1. Create a Lightsail instance: **Linux/Unix → OS Only → Ubuntu 22.04 LTS**, General purpose, 4 GB RAM minimum. Assign a static IP immediately after creation (first one is free). The Prefect worker is capped at 2 GB (`mem_limit` in `docker-compose.yml`), so a flow that runs away is stopped on its own rather than starving Postgres, the API and nginx; on a bigger instance it can be raised.

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

5. Add a GitHub deploy key so the VM can clone and pull the repo over SSH:
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
- `ENVIRONMENT=production` — turns off the public API docs, marks the session cookie `Secure`, and requires `FRONTEND_ORIGIN`
- `POSTGRES_HOST=db` — uses Docker's internal service name (PostgreSQL runs in the same stack)
- `POSTGRES_PASSWORD` — generate with `openssl rand -hex 32`; compose refuses to start without it
- `API_DB_PASSWORD` and `PIPELINE_DB_PASSWORD` (with `API_DB_USER=mshsfootball_api`, `PIPELINE_DB_USER=mshsfootball_pipeline`) — see [Database roles](#database-roles); on a new instance they're created with the database
- `CLOUDINARY_*` — from your Cloudinary dashboard
- `CLOUDINARY_BASE_URL` — hardcode the full URL: `https://res.cloudinary.com/YOUR_CLOUD_NAME/image/upload`
- `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` — from your Auth0 dashboard (same tenant as local dev)
- `FRONTEND_ORIGIN=https://mshsfootball.com`

Install the Nippo font files, which aren't in the repository: the two copies described in [backend/assets/fonts/README.md](../../backend/assets/fonts/README.md#nippo). Without them the site and share cards use Inter for titles.

Then bring up the stack (PostgreSQL runs in Docker alongside the other services):
```
docker compose --env-file .env.local --profile local-db up --build -d
```

### Database roles

The database is owned by `POSTGRES_USER`, which only schema setup and migrations
use. The API and the pipelines connect as their own roles (`sql/app_roles.sql`),
which can read and write rows and nothing else: they can't create or alter
tables, disable triggers (so the standings archive stays append-only), or run
`COPY … PROGRAM` and read server files the way a superuser can.

A new instance creates both roles with the database when `API_DB_PASSWORD` and
`PIPELINE_DB_PASSWORD` are set. On an existing database, create them once
(re-running is safe, and is how you change a password):

```
# 1. Add to .env.local (new random passwords):
#      API_DB_USER=mshsfootball_api
#      API_DB_PASSWORD=<openssl rand -hex 24>
#      PIPELINE_DB_USER=mshsfootball_pipeline
#      PIPELINE_DB_PASSWORD=<openssl rand -hex 24>
# 2. Create the roles, passing the passwords from the env file:
API_PW=$(grep '^API_DB_PASSWORD=' .env.local | cut -d= -f2-)
PIPE_PW=$(grep '^PIPELINE_DB_PASSWORD=' .env.local | cut -d= -f2-)
docker compose --env-file .env.local --profile local-db exec -T db \
  sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v api_password="$1" -v pipeline_password="$2" -f -' \
  sh "$API_PW" "$PIPE_PW" < sql/app_roles.sql
# 3. Recreate the API and the worker so they connect as the new roles:
docker compose --env-file .env.local --profile local-db up -d --force-recreate api prefect-worker
```

Until step 3, both keep using `POSTGRES_USER`. To check, `docker compose … exec api printenv POSTGRES_USER`
should print `mshsfootball_api`.

The database port is published on `127.0.0.1` only (for `psql` over an SSH
tunnel); containers reach it over the compose network. Docker's port rules
bypass `ufw`, so a port published on all interfaces would be open to the
internet behind nothing but the Lightsail firewall.

### Backups

`scripts/backup_db.sh` writes a compressed, verified `pg_dump` to `~/backups`
and keeps 14 days. Run it nightly from cron (`crontab -e`):

```
17 3 * * * cd /home/ubuntu/ms-hs-football-playoff-engine && scripts/backup_db.sh >> /home/ubuntu/backups/backup.log 2>&1
```

A copy on the same disk doesn't survive losing the instance, so also turn on
Lightsail's **automatic snapshots** (instance → Snapshots → Automatic
snapshots), or set `OFFSITE_CMD` to something that copies the file elsewhere.
The script's header has the restore command; try a restore into a scratch
database once, so you know it works before you need it.

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

## Auth0

All the Auth0 setup, production's included (the `/moderate` page's application and promoting moderators), is in [AUTH0_SETUP.md](AUTH0_SETUP.md). The server uses the same tenant, `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` as local development.

## Deploying updates

Note where you are, pull, and see what came in:

```
PREV=$(git rev-parse HEAD)
git pull
git log --oneline $PREV..HEAD
git diff --stat $PREV HEAD
```

Then work down this list, skipping what the pull didn't touch:

1. **New database migrations.** List them with
   `git diff --name-only --diff-filter=A $PREV HEAD -- sql/migrations`, and apply
   each before rebuilding (oldest name first), as the database owner:

   ```
   docker compose --env-file .env.local --profile local-db exec -T db \
     psql -v ON_ERROR_STOP=1 -U postgres -d mshsfootball < sql/migrations/<file>.sql
   ```

   (`-U` is your `POSTGRES_USER`.) Every migration is written to be safe to run
   more than once, so if you aren't sure one was applied, apply it again.
   `sql/init.sql` already includes them all, so a new database needs none.
2. **New settings.** If `.env.example` changed (`git diff $PREV HEAD -- .env.example`),
   add anything new to `.env.local`.
3. **Rebuild and restart:**

   ```
   docker compose --env-file .env.local --profile local-db up --build -d
   ```

4. **nginx's config.** If the pull changed `nginx/nginx.conf`, also recreate nginx.
   The config is bind-mounted as a single file, and `git pull` replaces that file
   rather than editing it, so a running container (and `nginx -s reload`) can keep
   seeing the old copy:

   ```
   docker compose --env-file .env.local --profile local-db up -d --no-deps --force-recreate nginx
   ```

5. **A model change.** If `MODEL_VERSION` changed
   (`git diff $PREV HEAD -- backend/prefect/region_scenarios_pipeline.py | grep MODEL_VERSION`),
   run `backfill-historical-snapshots` (Custom Run) for each season that should
   use the new model, then `region-scenarios-data-pipeline`, so today's snapshot
   is written last. A PR that needs any other one-off step says so in its
   description.
6. **Check it:** `docker compose --env-file .env.local --profile local-db ps`
   shows every service Up; a region page loads with today's numbers; the
   Prefect UI shows the latest runs completed. [PIPELINES.md](PIPELINES.md) lists
   every deployment.

Required env vars: `ENVIRONMENT=production`, `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, all `POSTGRES_*`,
`API_DB_*`, `PIPELINE_DB_*`, `CLOUDINARY_*`, `FRONTEND_ORIGIN`, `SESSION_SECRET_KEY`.
Optional: `AUTH0_SPA_CLIENT_ID`, `TURNSTILE_*`, `SMTP_*`, `DIGEST_TO` and `ALERT_TO` (see below), and
`POSTHOG_PROJECT_KEY`, `POSTHOG_DASHBOARD_URL`, `POSTHOG_ACTIVITY_URL` (visit counts and the
owner's dashboard links; see `.env.example`).

Base images are pinned by digest in `docker-compose.yml` and the Dockerfiles, and
Python packages come from `uv.lock` with their hashes checked, so a rebuild
installs exactly what was tested. Dependabot opens a PR when something has a
newer version; nothing changes on the server until that PR is merged and pulled.

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

The feedback form (`/feedback`, and the "Wrong score?", "Report score", "Wrong date?" and "Let us know" links) files
submissions into the moderation queue. Moderators review them at `/moderate`, and
a daily email lists what came in. Each piece below is off until it's configured.

### Moderation page (`/moderate`)

Moderators review submissions at `/moderate`, which signs in with its own Auth0 application: set it up, put its Client ID in `.env.local` as `AUTH0_SPA_CLIENT_ID`, and promote moderators, as [AUTH0_SETUP.md](AUTH0_SETUP.md#3-the-moderation-page-application-moderate) describes. The page shows the owner a **Prefect** link and sets the session cookie that lets it open.

### Turnstile (spam check on the form)

1. Cloudflare dashboard → **Turnstile** → **Add widget**. Hostname
   `mshsfootball.com`, widget mode **Managed** (the form keeps it invisible unless
   Cloudflare wants a click). The site doesn't have to be proxied by Cloudflare.
2. Set `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY` in `.env.local` and recreate
   the API. With no secret set, the form doesn't load the widget and the API
   doesn't check tokens.

If Cloudflare's verify endpoint is unreachable, submissions are refused with "try
again in a few minutes" (and an error is logged) rather than let through unchecked.
With `FRONTEND_ORIGIN` set, a token solved on any other hostname is refused. A visitor
whose content blocker stops the widget loading is told to allow
`challenges.cloudflare.com`.

### Daily digest email

The same SMTP settings send the owner an alert when the daily update stops itself (an AHSFHS
playoff game that disagrees with the bracket; see PIPELINES.md), to `ALERT_TO`, or `DIGEST_TO`
when that's empty.

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
