# Configure Auth0

Auth0 issues the RS256 JWT tokens the API validates. You need two things: an **API resource** (sets the audience claim) and an **Application** (sets your domain and gives you Swagger UI login credentials).

**Step 1 — Create the API resource**

1. Log in to [manage.auth0.com](https://manage.auth0.com).
2. Go to **Applications → APIs → Create API**.
3. Set **Name** to anything descriptive (e.g. `mshsfbanalytics`).
4. Set **Identifier** to your chosen audience string — this becomes `AUTH0_AUDIENCE` in your `.env` files. You cannot change this after creation.
5. Leave **Signing Algorithm** as `RS256`. Click **Create**.

**Step 2 — Create the Application**

1. Go to **Applications → Applications → Create Application**.
2. Set **Name** to anything descriptive (e.g. `mshsfbanalytics-local`).
3. Select **Regular Web Application**. Click **Create**.
4. Open the **Settings** tab. Note these three values — you will need them shortly:
   - **Domain** → becomes `AUTH0_DOMAIN` (e.g. `yourapp.us.auth0.com`)
   - **Client ID**
   - **Client Secret** (click reveal)

**Step 3 — Allow localhost as an origin**

The Swagger UI uses Auth0's Universal Login and redirects back to Swagger UI after login, so Auth0 needs to allow both the origin and the redirect URI. Still on the Application Settings page, add the following values:

- **Allowed Callback URLs**: `http://localhost:8000/docs/oauth2-redirect`
- **Allowed Web Origins**: `http://localhost:8000`
- **Allowed Origins (CORS)**: `http://localhost:8000`

Click **Save Changes**.

**Step 4 — Authorize the Application to access the API**

1. Go to **Applications → APIs** and click on your API (`mshsfbanalytics`).
2. Open the **Application Access** tab.
3. Find your application (`mshsfbanalytics-local`) and toggle it **on**. Click **Update**.

**Step 5 — Copy credentials to your `.env` files**

In both `.env.local` and `.env.non-docker.local`:

```
AUTH0_DOMAIN=<Domain from Step 2>
AUTH0_AUDIENCE=<Identifier from Step 1>
```

Keep the **Client ID** and **Client Secret** from Step 2 handy — you'll enter them in the Swagger UI Authorize dialog when promoting yourself to owner.
