// The front page ("/") is drawn once, by the pipeline (backend/helpers/static_pages.py,
// landing_body), from the same morning snapshot as everything else. nginx puts
// it in the page on a first visit; after navigating here within the site, the
// app fetches the same file. One renderer, so the page never changes under the
// reader and there's no second copy to keep in step.

export const FRONT_PAGE_URL = "/share/front.html";

const CLASSES = [1, 2, 3, 4, 5, 6, 7];

/** What "/" shows when the pipeline's page isn't there (a fresh install, or it failed to load). */
export const LANDING_FALLBACK = '<div class="page landing landing--fallback"><div class="landing-intro">'
  + '<p class="landing-kicker">Welcome to</p><h1 class="landing-title">Mississippi High School Football</h1>'
  + '<p>Standings, playoff odds, and exactly what each team needs to happen, for every MHSAA region.</p>'
  + `<p class="landing-links">Standings: ${CLASSES.map((c) => `<a href="/standings/${c}a">${c}A</a>`).join(" ")}</p>`
  + `<p class="landing-links">Brackets: ${CLASSES.map((c) => `<a href="/brackets/${c}a">${c}A</a>`).join(" ")}</p>`
  + '<p><a href="/methodology">How it works</a></p></div></div>';

/** Is this the pipeline's front page (and not, say, an error page)? */
export function isFrontPage(html) {
  return typeof html === "string" && html.includes('<div class="page landing">');
}
