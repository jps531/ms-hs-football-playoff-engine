# Auth Phase 2 — Deferred Features

Auth0 handles email verification, password reset, password change, and session
management. The items below are not covered by Auth0 and remain deferred.

---

## CORS Tightening

Once the SPA frontend has a stable origin, replace the wildcard CORS config in
`backend/api/main.py`:

```python
# Change from:
allow_origins=["*"]

# To:
allow_origins=[os.environ["FRONTEND_ORIGIN"]]
allow_credentials=True
```

Add to `.env.example`:
```
FRONTEND_ORIGIN=https://yourdomain.com
```

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

---

## Submission Linkage at Submit Time

Once users are authenticated via Auth0, link submissions to their account using
the Auth0 `sub` claim from the verified JWT.

Add an optional dependency to `auth.py`:

```python
def get_current_user_optional(
    token: str | None = Depends(OAuth2PasswordBearer(tokenUrl="token", auto_error=False)),
) -> dict | None:
    if token is None:
        return None
    try:
        return verify_auth0_token(token)  # your existing Auth0 JWT verifier
    except HTTPException:
        return None

CurrentUserOptional = Annotated[dict | None, Depends(get_current_user_optional)]
```

Update each `INSERT INTO submissions` to include `user_id` when a valid token
is present:

```python
async def submit_logo(
    ...,
    current_user: CurrentUserOptional,
) -> SubmissionCreatedResponse:
    user_id = current_user["sub"] if current_user else None
    await conn.execute(
        "INSERT INTO submissions (type, school, user_id, payload) VALUES ('logo', %s, %s, %s) ...",
        (school, user_id, json.dumps(payload)),
    )
```

Note: `user_id` here is the Auth0 `sub` string (e.g. `auth0|abc123`), not an
integer. Ensure the `submissions.user_id` column is `TEXT`, not `INTEGER`.
