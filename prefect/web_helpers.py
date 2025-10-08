import json, re, time
from playwright.sync_api import sync_playwright
import requests
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