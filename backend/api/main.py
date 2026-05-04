"""FastAPI application for the MS High School Football Playoff Engine.

Startup and shutdown lifecycle are handled via the ``lifespan`` context manager,
which opens and closes the async psycopg v3 connection pool.  CORS origin is
controlled by the FRONTEND_ORIGIN env var (defaults to ``*`` for local dev).

Swagger UI and ReDoc are only served when ENVIRONMENT=local (the default).
In production the docs URL is disabled to prevent public schema exposure.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.api import db
from backend.api.limiter import limiter
from backend.api.routers import (
    admin,
    auth_router,
    bracket,
    games,
    hosting,
    images,
    meta,
    moderation,
    ratings,
    standings,
    submissions,
    users,
)

_ENV = os.getenv("ENVIRONMENT", "local")
_FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")

if _ENV != "local" and _FRONTEND_ORIGIN == "*":
    raise RuntimeError(
        "FRONTEND_ORIGIN env var must be set to a specific origin (e.g. https://yourdomain.com) "
        "in non-local environments. Refusing to start with wildcard CORS."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open DB pool on startup; close it on shutdown."""
    await db.open_pool()
    yield
    await db.close_pool()


app = FastAPI(
    title="MS HS Football Playoff Engine API",
    description="Playoff scenarios, seeding odds, win probabilities, and bracket advancement for Mississippi high school football.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _ENV == "local" else None,
    redoc_url="/redoc" if _ENV == "local" else None,
    openapi_url="/openapi.json" if _ENV == "local" else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]  # slowapi handler typed narrower than Starlette's ExceptionHandler protocol

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_FRONTEND_ORIGIN],
    allow_credentials=_FRONTEND_ORIGIN != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(users.router)
app.include_router(meta.router)
app.include_router(standings.router)
app.include_router(hosting.router)
app.include_router(bracket.router)
app.include_router(games.router)
app.include_router(ratings.router)
app.include_router(admin.router)
app.include_router(images.router)
app.include_router(submissions.router)
app.include_router(moderation.router)
