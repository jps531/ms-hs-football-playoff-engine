"""FastAPI application for the MS High School Football Playoff Engine.

Startup and shutdown lifecycle are handled via the ``lifespan`` context manager,
which opens and closes the async psycopg v3 connection pool.  CORS is configured
to allow any origin for local development; restrict in production.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import db
from backend.api.routers import admin, bracket, games, hosting, images, meta, ratings, standings


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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(standings.router)
app.include_router(hosting.router)
app.include_router(bracket.router)
app.include_router(games.router)
app.include_router(ratings.router)
app.include_router(admin.router)
app.include_router(images.router)
