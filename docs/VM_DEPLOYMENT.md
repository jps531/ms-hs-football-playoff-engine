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
