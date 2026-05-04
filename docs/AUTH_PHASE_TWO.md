# Auth Phase 2 — Deferred Features

Auth0 handles email verification, password reset, password change, and session
management. The item below are not covered by Auth0 and remain deferred.

---

## HTTPS / SSL in nginx

Add to `nginx/nginx.conf`:

```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
}

server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

Add to `docker-compose.yml` nginx service:

```yaml
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
  - /etc/letsencrypt/live/yourdomain.com:/etc/nginx/certs:ro
ports:
  - "80:80"
  - "443:443"
```
