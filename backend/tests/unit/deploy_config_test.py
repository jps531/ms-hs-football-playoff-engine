"""Deployment configuration that's easy to undo by accident: nginx's security headers and CSP, the
database's exposure, and the pinned, hash-checked builds. Each test names what a change would break."""

import base64
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NGINX = (ROOT / "nginx" / "nginx.conf").read_text()
COMPOSE = (ROOT / "docker-compose.yml").read_text()
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")


def _csp() -> str:
    """The default Content-Security-Policy nginx sends."""
    return re.search(r'default "(default-src[^"]+)";', NGINX).group(1)


def _inline_scripts(html: str) -> list[str]:
    """The bodies of a page's inline <script> elements (not src=, not JSON-LD data blocks)."""
    return re.findall(r"<script>(.*?)</script>", html, re.S)


def test_every_inline_script_is_allowed_by_its_hash():
    """Edit the <head> theme script and its CSP hash must change too, or the browser blocks it."""
    pages = sorted((ROOT / "nginx" / "html").glob("*.html"))
    assert pages
    for page in pages:
        for body in _inline_scripts(page.read_text()):
            digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
            assert f"'sha256-{digest}'" in _csp(), f"{page.name}: inline script not in the CSP (sha256-{digest})"


def test_the_csp_keeps_its_safeguards():
    """No unsafe-inline or eval for scripts, no plugins, no framing, no <base> hijack."""
    csp = _csp()
    script_src = re.search(r"script-src ([^;]+)", csp).group(1)
    assert "'unsafe-inline'" not in script_src and "'unsafe-eval'" not in script_src
    for directive in ("object-src 'none'", "frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'"):
        assert directive in csp


def test_no_location_drops_the_security_headers():
    """An add_header inside a location replaces every server-level one there, CSP and HSTS included."""
    server = re.sub(r"#.*", "", NGINX[NGINX.index("listen 443 ssl;") :])
    blocks = re.findall(r"location [^{]+\{(.*?)\n        \}", server, re.S)
    assert blocks
    for block in blocks:
        assert "add_header" not in block


def test_nginx_hides_its_version_and_refuses_unknown_hosts():
    """No version in headers; requests for other hostnames get nothing."""
    assert "server_tokens off;" in NGINX
    assert "listen 443 ssl default_server;" in NGINX and "ssl_reject_handshake on;" in NGINX
    assert "HIGH:!aNULL:!MD5" not in NGINX


def test_postgres_is_loopback_only_and_has_no_default_password():
    """Docker's port rules bypass ufw, so a published 5432 is the internet's; a default password is public."""
    assert '"127.0.0.1:${POSTGRES_PORT:-5432}:5432"' in COMPOSE
    assert not re.search(r'^\s*- "\$\{POSTGRES_PORT:-5432\}:5432"', COMPOSE, re.M)
    assert "POSTGRES_PASSWORD:-postgres" not in COMPOSE
    assert "${POSTGRES_PASSWORD:?" in COMPOSE


def test_app_roles_cannot_alter_the_schema():
    """The API and pipeline roles get row access only; fresh databases create them too."""
    roles = (ROOT / "sql" / "app_roles.sql").read_text()
    for role in ("mshsfootball_api", "mshsfootball_pipeline"):
        assert f"ALTER ROLE {role} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE" in roles
    assert "GRANT ALL" not in roles and "TRUNCATE" not in roles
    assert "init_app_roles.sh:/docker-entrypoint-initdb.d/08_app_roles.sh" in COMPOSE
    assert "app_roles.sql:/docker-entrypoint-initdb.d/app_roles.sql.inc" in COMPOSE


def test_images_are_pinned_by_digest():
    """Every image in compose and every FROM in the Dockerfiles names an exact digest."""
    images = re.findall(r"^\s*image: (\S+)", COMPOSE, re.M)
    assert images
    for image in images:
        assert DIGEST.search(image), image
    for dockerfile in ("Dockerfile.api", "Dockerfile.prefect"):
        for line in re.findall(r"^FROM (\S+)", (ROOT / dockerfile).read_text(), re.M):
            assert DIGEST.search(line), f"{dockerfile}: {line}"


def test_builds_install_the_lockfile_with_hashes_and_bake_in_no_secrets():
    """Dependencies come from uv.lock, hash-checked; no env file is copied into an image."""
    for dockerfile in ("Dockerfile.api", "Dockerfile.prefect"):
        text = (ROOT / dockerfile).read_text()
        assert "uv export --frozen" in text and "--require-hashes" in text
        assert not re.search(r"^COPY .*\.env", text, re.M)
    ignore = (ROOT / ".dockerignore").read_text().split()
    assert ".env.*" in ignore and ".git" in ignore
