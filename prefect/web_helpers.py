import json, re, time, requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from typing import Optional
from difflib import SequenceMatcher
from bs4 import BeautifulSoup

from data_helpers import SPACE_RE

# -------------------------
# Constants
# -------------------------


# --- WEB REQUEST CONFIG ---
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")


AHSFHS_EXPECTED_TEXT = re.compile(r"\bDate\s+Opponent\s+Score\b", re.I)

# -------------------------
# Helpers
# -------------------------


def fetch_article_text(url: str) -> str:
    """
    Use Playwright headless Chromium to retrieve the browser-rendered text
    of the main article body. This captures actual on-screen spacing.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ))
        page.goto(url, wait_until="networkidle")
        # try to focus on the main WordPress article content
        loc = page.locator("article .entry-content, .entry-content, article")
        if loc.count() == 0:
            text = page.inner_text("body")
        else:
            text = loc.first.inner_text()
        browser.close()

    # normalize whitespace
    lines = [SPACE_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return text


def _probe_exists(url: str, timeout=10) -> bool:
    """
    Light probe: HEAD (follow redirects) -> fallback GET(stream=True).
    Returns True if final status is 200.
    """
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return True
        # Some CDNs don’t like HEAD; try a tiny GET
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
        return r.status_code == 200
    except requests.RequestException:
        return False
    

def _ensure_trailing_slash(u: str) -> str:
  return u if u.endswith("/") else (u + "/")


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _extract_next_data(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        raise RuntimeError("Search page missing __NEXT_DATA__")
    return json.loads(script.string)


def _iter_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_dicts(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_dicts(v)


def fetch_article_text_from_ahsfhs(url: str, nav_timeout_ms: int = 60000, selector_timeout_ms: int = 20000, attempts: int = 3) -> Optional[str]:
    """
    Robust fetcher for AHSFHS schedule pages.
    - Avoids 'networkidle' (can hang forever).
    - Waits for schedule header text instead.
    - Blocks images/fonts/ads to speed up.
    - Retries with backoff.
    """
    last_err = None
    backoff = 2.0

    for attempt in range(1, attempts + 1):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=[
                    "--no-sandbox", "--disable-setuid-sandbox"
                ])
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HSFB-Scraper Safari/537.36",
                    java_script_enabled=True,
                )

                # Block heavy resources to avoid slow loads that postpone load events
                def _block(route, request):
                    rtype = request.resource_type
                    if rtype in ("image", "media", "font", "stylesheet"):
                        return route.abort()
                    return route.continue_()

                context.route("**/*", _block)

                page = context.new_page()
                page.set_default_navigation_timeout(nav_timeout_ms)
                page.set_default_timeout(selector_timeout_ms)

                # Navigate and wait for a stable event that will actually fire
                page.goto(url, wait_until="domcontentloaded")
                # Optional: ensure the main content rendered
                # Try to detect the schedule table header text
                page.wait_for_function(
                    """() => document.body && /\\bDate\\s+Opponent\\s+Score\\b/i.test(document.body.innerText)""",
                    timeout=selector_timeout_ms
                )

                html = page.content()
                browser.close()
                return html

        except PWTimeout as e:
            last_err = e
        except Exception as e:
            last_err = e

        # Backoff between attempts
        time.sleep(backoff)
        backoff *= 1.8

    # Final fallback: try simple requests (page appears mostly static text)
    try:
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 HSFB-Scraper"
        })
        if resp.ok:
            return resp.text
    except Exception as e:
        last_err = e

    # If everything failed, surface the most recent error
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")