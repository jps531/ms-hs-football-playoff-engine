from __future__ import annotations

import re

from playwright.sync_api import sync_playwright
import psycopg2

# -------------------------
# Constants
# -------------------------

SPACE_RE = re.compile(r"\s+")

# -------------------------
# Helpers
# -------------------------

def to_normal_case(s: str) -> str:
    """
    Convert a string to normal case (title case with special handling for "Mc" and possessives like "'s").
    """
    if not s:
        return s
    t = s.title()
    t = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), t)
    t = re.sub(r"(['’])S\b", r"\1s", t)
    t = re.sub(r"\bDiber", "D'Iber", t)
    t = re.sub(r"\bSt\b(?!\.)", "St.", t)
    return t


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



def get_conn(DB_HOST: str, DB_PORT: int, DB_NAME: str, DB_USER: str, DB_PASSWORD: str):
    """
    Get a connection to the PostgreSQL database.
    """
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )