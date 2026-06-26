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

Run once after DNS is resolving to your static IP. Bring the stack down first to free port 80:

```
docker compose --env-file .env.local --profile local-db down
sudo apt install certbot -y
sudo certbot certonly --standalone -d mshsfootball.com
```

Set up an auto-renewal hook so nginx reloads when the cert renews (every 90 days):
```
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh << 'EOF'
#!/bin/bash
docker exec nginx_local nginx -s reload
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

Bring the stack back up — nginx will now serve HTTPS and redirect HTTP to HTTPS:
```
docker compose --env-file .env.local --profile local-db up --build -d
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

Required env vars: `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, all `POSTGRES_*`, `CLOUDINARY_*`, `FRONTEND_ORIGIN`.
