"""Shared pytest fixtures/config for backend.tests.

Sets defaults for env vars that backend.api.auth reads at import time, so
the test suite doesn't require real Auth0/session credentials to run.
setdefault() means real exported values (e.g. in CI) still win.
"""

import os

os.environ.setdefault("AUTH0_DOMAIN", "test.auth0.local")
os.environ.setdefault("AUTH0_AUDIENCE", "test-audience")
os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret-key-not-for-production")
