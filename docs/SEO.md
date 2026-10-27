# Search engines

How the site presents itself to Google, Bing and the rest, and what to do
outside the code.

## In place

- **Every content page reads without JavaScript.** The About page is plain
  HTML. nginx puts the pipeline's copy of the others in the HTML (server-side
  includes, see `share_assets_pipeline.py`): the front page, every class and
  region page, and every bracket page. (`/feedback` and `/moderate` need
  JavaScript.) The
  app replaces it on load with the same markup, so nothing moves.
- **One address per page.** Each page names its canonical URL; query-string
  variants (`?week=`, `?odds=`, `?season=`) point at the plain path;
  `www.mshsfootball.com` and `http://` redirect to `https://mshsfootball.com`.
- **Real 404s.** Only real page routes get the app (`/standings/{1-7}a`,
  `/standings/{1-7}a/{region}`, `/brackets/{1-7}a`); anything else gets
  `nginx/html/404.html` with a 404 status. A well-formed address for something
  that doesn't exist (a region a class doesn't have) is caught by the app,
  which tells search engines `noindex`.
- **Links between pages.** Breadcrumbs (Home › Class 3A › Region 6-3A) on
  class, region, bracket and About pages, and the 1A–7A class picker in
  every page's HTML.
- **Structured data.** `BreadcrumbList` on each of those pages and `WebSite`
  (the site's name for search results) on the front page, as JSON-LD in the
  generated head tags.
- **`sitemap.xml`** (front page, About page, every class, region and bracket
  page, with the snapshot date as `lastmod`), linked from `robots.txt`.
- **Not indexed:** the API, its docs, `/moderate`, `/feedback` (an
  `X-Robots-Tag: noindex` header). `/api/` is deliberately *not* blocked in
  `robots.txt`: Google runs the app when it renders a page, and the app needs
  the API.
- **Speed:** fonts served from the site (no third-party font requests; helmet
  images come from Cloudinary), compressed
  text responses, fonts cached for a year and the app's files for 10 minutes.

## To do outside the code

1. **Google Search Console** (search.google.com/search-console): add the
   *Domain* property `mshsfootball.com`, verify it with the TXT record it gives
   you (Lightsail → Networking → DNS zones → add a TXT record), then
   **Sitemaps** → submit `https://mshsfootball.com/sitemap.xml`. Search
   Console then reports what's indexed, what isn't and why, and the searches
   that find the site.
2. **Bing Webmaster Tools** (bing.com/webmasters): sign in and import the site
   from Search Console. That also covers DuckDuckGo and Yahoo, which use Bing's
   index.
3. **www:** the redirect only works over HTTPS if the certificate covers
   `www.mshsfootball.com` (see [Adding www](VM_DEPLOYMENT.md#adding-www-optional)).
   Without a `www` DNS record nobody reaches it anyway, so this is only needed
   if you add one.
4. **Links from elsewhere** are what move a new site up: school and booster
   pages, local sports writers (the About page has a citation line),
   fan groups, your portfolio.

## Checking

- Google's [Rich Results Test](https://search.google.com/test/rich-results)
  on a region page should find a valid breadcrumb.
- `curl -s https://mshsfootball.com/standings/3a/6 | grep -c 'class="standings"'`
  should be 1 (the table is in the HTML).
- `curl -sI https://mshsfootball.com/standings/9a` should say `404`.
