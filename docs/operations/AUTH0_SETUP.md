# Configure Auth0

Auth0 issues the RS256 JWT tokens the API validates. There are three pieces:

- an **API resource**, which sets the token's audience (`AUTH0_AUDIENCE`);
- a **Regular Web Application**, for signing in to Swagger UI during local development;
- a **Single Page Application**, for the `/moderate` page.

All three live in one Auth0 tenant, for local development and production alike.

## 1. The API resource

1. Log in to [manage.auth0.com](https://manage.auth0.com).
2. Go to **Applications → APIs → Create API**.
3. Set **Name** to anything descriptive (e.g. `mshsfbanalytics`).
4. Set **Identifier** to your chosen audience string — this becomes `AUTH0_AUDIENCE` in `.env.local`. You cannot change this after creation.
5. Leave **Signing Algorithm** as `RS256`. Click **Create**.

## 2. The Swagger UI application (local development)

1. Go to **Applications → Applications → Create Application**.
2. Set **Name** to anything descriptive (e.g. `mshsfbanalytics-local`).
3. Select **Regular Web Application**. Click **Create**.
4. Open the **Settings** tab. Note these three values:
   - **Domain** → becomes `AUTH0_DOMAIN` (e.g. `yourapp.us.auth0.com`)
   - **Client ID**
   - **Client Secret** (click reveal)
5. Swagger UI uses Auth0's Universal Login and redirects back to Swagger UI afterwards, so allow both the origin and the redirect. Still in Settings:
   - **Allowed Callback URLs**: `http://localhost:8000/docs/oauth2-redirect`
   - **Allowed Web Origins**: `http://localhost:8000`
   - **Allowed Origins (CORS)**: `http://localhost:8000`

   Click **Save Changes**.
6. Authorize it for the API: **Applications → APIs →** your API → **Application Access**, find the application and set **User Access** to **Authorized** (older dashboards: turn its toggle on, then click **Update**).

In `.env.local`:

```
AUTH0_DOMAIN=<Domain from step 2.4>
AUTH0_AUDIENCE=<Identifier from step 1.4>
```

Keep the **Client ID** and **Client Secret** handy: you type them into Swagger UI's **Authorize** dialog (see [Promote yourself to owner](LOCAL_DEVELOPMENT.md#4-promote-yourself-to-owner)).

Swagger UI is only served with `ENVIRONMENT=local`. Production turns it off, so this application needs no production URLs.

## 3. The moderation page application (`/moderate`)

The page signs in with Auth0 directly from the browser (authorization code + PKCE), so it needs its own application:

1. **Applications → Create Application → Single Page Web Applications** (name it e.g. "MSHSF moderation").
2. In its Settings:
   - **Allowed Callback URLs:** `https://mshsfootball.com/moderate`
   - **Allowed Logout URLs:** `https://mshsfootball.com/moderate`
   - **Allowed Web Origins:** `https://mshsfootball.com`

   Locally nginx isn't run, so `/moderate` is only served on the server.
3. Authorize it for the API: **Applications → APIs →** your API → **Application Access** (older dashboards: **Machine to Machine Applications**), find the new app and set **User Access** to **Authorized** (older dashboards: turn its toggle on). No scopes are needed. Skipping this gives `Client "…" is not authorized to access resource server "…"` on sign-in.
4. Put its **Client ID** in the server's `.env.local` as `AUTH0_SPA_CLIENT_ID` and recreate the API.

## 4. Roles

A `users` row is created on a person's first authenticated request (signing in at `/moderate`, or calling `GET /api/v1/users/me` from Swagger UI). Everyone starts as `user`.

- **Owner:** set once, by SQL. [Promote yourself to owner](LOCAL_DEVELOPMENT.md#4-promote-yourself-to-owner) has the steps.
- **Moderator:** promote by Auth0 user ID (Auth0 → User Management → Users → the person → **user_id**, e.g. `auth0|65f…` or `google-oauth2|10…`), not by email: the stored email is only kept once Auth0 has verified it, and anyone can type someone else's address when signing up. On the server:

  ```
  docker compose --env-file .env.local --profile local-db exec -T db \
    psql -U postgres -d mshsfootball -c "UPDATE users SET role = 'moderator' WHERE auth0_id = 'auth0|65f0c0ffee…';"
  ```

  The owner can also change roles through `PATCH /api/v1/users/{user_id}/role` ([API_REFERENCE.md](../reference/API_REFERENCE.md)).

Only moderators and the owner see the moderation queue. The Prefect UI is the owner's only: `/moderate` shows its **Prefect** link, and sets the session cookie that lets it open, only for the owner.

## What Auth0 covers vs. what this app builds

Auth0 handles email verification, password reset, password change, and Universal Login session management out of the box, so none of that is built here. The app's own auth code (`backend/api/auth.py`) only:

- validates the RS256 JWT against Auth0's JWKS endpoint;
- lazy-provisions `users` rows;
- checks roles (`user`/`moderator`/`owner`);
- issues the first-party session cookie that opens the Prefect UI for the owner.
