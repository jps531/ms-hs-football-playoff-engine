# Local development

Locally, the database, the API and Prefect run in Docker. nginx is
production-only: its config answers only for `mshsfootball.com` over HTTPS,
so the local overlay (`docker-compose.local.yml`) leaves it out and publishes
the API and the Prefect UI directly. The site's pages need nginx, so they
aren't served locally; the JavaScript tests and the Python mirror tests cover
their logic ([FRONTEND.md](../architecture/FRONTEND.md)).

## 1. Auth0

You need the Auth0 **API resource** (the token's audience) and the **Swagger UI
application**: sections 1 and 2 of [AUTH0_SETUP.md](AUTH0_SETUP.md).

## 2. The environment file

```
cp .env.example .env.local
```

Four values must be filled in; everything else has a working default or turns
its feature off when blank:

| Variable | Value |
|---|---|
| `POSTGRES_PASSWORD` | Any strong password (`openssl rand -hex 32`). It's set when the database is first created; changing it later doesn't change an existing database's password. |
| `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` | From step 1 |
| `SESSION_SECRET_KEY` | `openssl rand -hex 32` |

Keep `ENVIRONMENT=local` (Swagger UI on, local CORS) and `POSTGRES_HOST=db` (the
database's name inside Docker). Leave `API_DB_*` and `PIPELINE_DB_*` blank unless
you've created those roles ([Database roles](VM_DEPLOYMENT.md#database-roles));
blank, the services connect as `POSTGRES_USER`. `CLOUDINARY_*` is only needed for
image uploads and image URLs.

## 3. Start the containers

```
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db up --build -d
```

`--profile local-db` starts the local PostgreSQL container (`db`). On a VM with an
external database, omit it.

| Service | Where |
|---|---|
| API | `http://localhost:8000`, Swagger UI at `http://localhost:8000/docs` |
| Prefect UI | `http://localhost:4200` |
| PostgreSQL | `localhost:5432` |
| Prefect worker | internal (runs the pipelines) |

All three are published on `127.0.0.1` only. Locally the Prefect UI needs no
sign-in, since only your machine can reach it; on the server it's behind nginx
at `/prefect/`, for the owner only: sign in at `/moderate` and use its
**Prefect** link, which sets the session cookie that lets it open.

```
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db logs -f api
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db up --build -d api prefect-worker
```

The first streams the API's logs. The second picks up a code change: the code is
copied into the images rather than mounted, so the API (`backend/api`,
`backend/helpers`) and the worker (the pipelines) need a rebuild to see it.

To load data, run the pipelines in the Prefect UI in the
[pre-season order](PIPELINES.md#pre-season-order).

> **Apple Silicon:** the overlay sets `OPENSSL_armcap=0` for the API and Prefect.
> Docker's Linux VM on Apple Silicon advertises CPU features that OpenSSL then
> tries to use but the VM can't run, so anything that loads it (the
> `cryptography` package, which the API's token checks and Prefect use) dies
> with "Illegal instruction" (exit code 132). The setting turns off OpenSSL's
> ARM feature detection; it's ignored on Intel, and production doesn't use it.

## 4. Promote yourself to owner

The owner role grants access to admin and moderation endpoints. Without it, your
account is a base `user` and you won't be able to approve submissions, manage
other users, or access the Prefect UI on the server.

User rows are created on the first authenticated API request, so you need to
sign in before the SQL update will find anything. Create your user in the Auth0
dashboard first (on the server, signing in once at `/moderate` does the same):

1. In the Auth0 dashboard, go to **User Management → Users → Create User**.
2. Enter an email and password. Leave **Connection** as `Username-Password-Authentication`. Click **Create**.

Then sign in through Swagger UI to create your row:

3. Open Swagger UI at `http://localhost:8000/docs`.
4. Click **Authorize** and fill in the dialog:
   - **client_id**: the Swagger application's Client ID ([AUTH0_SETUP.md](AUTH0_SETUP.md#2-the-swagger-ui-application-local-development), step 4)
   - **client_secret**: its Client Secret
   - Leave **scope** blank.
5. Click **Authorize**. Auth0's Universal Login page opens; sign in with the user you created.
6. Auth0 redirects back to Swagger UI. Click **Close**.
7. Call `GET /api/v1/users/me`, which creates your row.

Then run the promotion. Replace `auth0|YOUR_SUB_HERE` with your Auth0 user ID
(the `sub` claim): find it by decoding your JWT at jwt.io, or in the Auth0
dashboard under User Management → Users → User ID. The full `auth0|...` prefix
is required.

```
docker exec -it ms-hs-football-playoff-engine-db-1 psql -U postgres -d mshsfootball -c \
  "UPDATE users SET role = 'owner' WHERE auth0_id = 'auth0|YOUR_SUB_HERE';"
```

## Resetting the database

To start over from the schema (e.g. after a schema change):

```
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db down -v
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db up --build -d
```

`-v` removes the Postgres data volume, so the container runs `sql/init.sql` and
the seed files again on startup.
