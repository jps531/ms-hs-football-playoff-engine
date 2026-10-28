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
    """The bodies of a page's inline <script> elements (not src=, not JSON-LD data blocks).

    Any attributes and any case: an inline script missed here would pass this test and then be
    blocked by the browser.
    """
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script\b[^>]*>", html, re.S | re.I)
    return [
        body
        for attrs, body in scripts
        if not re.search(r"\bsrc\s*=", attrs, re.I) and not re.search(r"application/ld\+json", attrs, re.I)
    ]


def test_inline_scripts_are_found_whatever_their_attributes_or_case():
    """Only external scripts and JSON-LD data blocks are left out."""
    html = (
        '<script>a()</script><SCRIPT>b()</SCRIPT><script type="module">c()</script foo>'
        '<script src="/x.js"></script><script type="application/ld+json">{}</script>'
    )
    assert _inline_scripts(html) == ["a()", "b()", "c()"]


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


def _service(name: str) -> str:
    """One service's block in docker-compose.yml."""
    return re.search(rf"^  {name}:\n(.*?)(?=^  \S|^\S)", COMPOSE, re.M | re.S).group(1)


def test_prefect_is_reachable_only_through_the_owner_check():
    """Prefect 2's server has no login of its own, so the owner check is all that keeps its API from the internet.

    That's why Prefect's advisories about bypassing its built-in auth, or about endpoints that skip
    it, can't be exploited here. Publish a Prefect port, or proxy to Prefect without asking the API,
    and they can.
    """
    for service in ("prefect-server", "prefect-worker"):
        assert "ports:" not in _service(service), f"{service} publishes a port"
    config = re.sub(r"#.*", "", NGINX)
    blocks = re.findall(r"location ([^{]+)\{(.*?)\n        \}", config, re.S)
    to_prefect = {path.strip(): body for path, body in blocks if re.search(r"proxy_pass\s+http://prefect\b", body)}
    assert set(to_prefect) == {"/prefect/api/", "/prefect/"}
    for path, body in to_prefect.items():
        assert re.search(r"^\s*auth_request\s+/internal/auth/verify-moderator;", body, re.M), path
    # The check itself: internal-only, and the API endpoint that lets only the owner through.
    check = re.search(r"location = /internal/auth/verify-moderator \{(.*?)\n        \}", config, re.S).group(1)
    assert re.search(r"^\s*internal;", check, re.M)
    assert re.search(r"proxy_pass\s+http://api/api/v1/auth/verify-moderator;", check)


def test_the_worker_has_a_memory_limit():
    """A flow that runs out of control is stopped by itself, not with the database and site beside it."""
    worker = _service("prefect-worker")
    assert re.search(r"^\s*mem_limit: 2g$", worker, re.M)
    assert re.search(r"^\s*memswap_limit: 2g$", worker, re.M)


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


def test_every_image_runs_the_python_the_project_targets():
    """The API image, the worker's Prefect image and ruff all say 3.11; a jump (say, to 3.14) needs every
    locked wheel to exist for it, so it's a deliberate change, not a Dependabot merge."""
    pyproject = (ROOT / "pyproject.toml").read_text()
    target = re.search(r'target-version = "py3(\d+)"', pyproject).group(1)
    api = re.search(r"^FROM python:3\.(\d+)\.", (ROOT / "Dockerfile.api").read_text(), re.M).group(1)
    worker = re.search(r"^FROM prefecthq/prefect:\S+-python3\.(\d+)@", (ROOT / "Dockerfile.prefect").read_text(), re.M)
    assert api == worker.group(1) == target
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text()
    assert 'dependency-name: "python"' in dependabot


def test_only_real_pages_get_the_app_and_everything_else_404s():
    """Page routes are validated in nginx; other addresses get the 404 page, not the API's JSON or a 200 shell."""
    route = re.search(r"location ~ (\S+) \{\n\s+root /usr/share/nginx/html;\n\s+ssi on;", NGINX).group(1)
    pattern = re.compile(route.strip("^$").join("^$"))
    for path in ("/standings/3a", "/standings/3a/", "/standings/3a/6", "/brackets/7a"):
        assert pattern.match(path), path
    for path in ("/standings/9a", "/standings/3a/12", "/standings/3a/6/x", "/brackets/8a", "/brackets/7a/1"):
        assert not pattern.match(path), path
    assert "error_page 404 /404.html;" in NGINX
    assert "location ^~ /standings/" not in NGINX  # ^~ would stop the route regex from ever matching
    assert re.search(r"location / \{\n\s+return 404;", NGINX)
    page = (ROOT / "nginx" / "html" / "404.html").read_text()
    assert '<meta name="robots" content="noindex">' in page


def test_api_responses_are_noindexed_but_still_crawlable():
    """Google renders the app, which needs /api/, so robots.txt mustn't block it; a header keeps it out of results."""
    robots = (ROOT / "nginx" / "html" / "robots.txt").read_text()
    assert "Disallow: /api" not in robots
    assert '"noindex"' in NGINX and "add_header X-Robots-Tag $x_robots_tag" in NGINX


def test_www_redirects_to_the_bare_domain():
    """One address per page for search engines."""
    assert "return 301 https://mshsfootball.com$request_uri;" in NGINX
    assert "if ($host = www.mshsfootball.com)" in NGINX


def test_the_main_nav_is_in_the_page_from_the_start():
    """Standings and Bracket point at the page's class, and the current section is marked, before the app loads."""
    shell = (ROOT / "nginx" / "html" / "index.html").read_text()
    for cls in ("site-nav__item", "tab-bar__item"):
        assert f'<a class="{cls}" href="/brackets/<!--# if expr="$page_class" -->' in shell
        assert '<!--# if expr="$nav_section = bracket" --> aria-current="page"' in shell
    assert "map $request_uri $nav_section" in NGINX


def test_the_front_page_marks_home_and_has_no_class_picker():
    """ "/" is Home on the phone tab bar (neither Standings nor Bracket), and has its own class grid
    instead of the picker."""
    section = re.search(r"map \$request_uri \$nav_section \{(.*?)\}", NGINX, re.S).group(1)
    assert '"~^/(?:\\?|$)"   "home"' in section
    shell = (ROOT / "nginx" / "html" / "index.html").read_text()
    assert '<a class="tab-bar__item" href="/" data-nav="home"<!--# if expr="$nav_section = home" -->' in shell
    picker = re.search(r"map \$request_uri \$show_class_picker \{(.*?)\}", NGINX, re.S).group(1)
    assert '"no"' in picker
    shell = (ROOT / "nginx" / "html" / "index.html").read_text()
    assert '<div class="scrubber-bar"<!--# if expr="$show_class_picker = no" --> hidden<!--# endif -->>' in shell


def test_visit_counts_go_out_through_this_site_and_carry_nothing_of_the_visitors():
    """The analytics relay: PostHog's events leave through nginx, so the CSP stays 'self'; nginx still starts
    when PostHog can't be resolved; cookies and auth never go either way; the visitor's address is passed on for
    cookieless counting; and the vendored library is the only PostHog code the page loads."""
    block = re.search(r"location \^~ /relay/ \{(.*?)\n        \}", NGINX, re.S).group(1)
    # A variable host, resolved per request.
    assert "resolver" in block and "proxy_pass         https://$posthog_host" in block
    assert "proxy_ssl_verify   on" in block
    for header in ('Cookie          ""', 'Authorization   ""', "X-Forwarded-For $remote_addr"):
        assert f"proxy_set_header   {header}" in block
    assert "proxy_hide_header  Set-Cookie" in block
    assert "posthog" not in _csp()
    analytics = (ROOT / "nginx" / "html" / "static" / "js" / "analytics.js").read_text()
    assert 'api_host: "/relay"' in analytics and 'cookieless_mode: "always"' in analytics
    assert 'import("./vendor/posthog-js.js")' in analytics
