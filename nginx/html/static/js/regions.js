import { breadcrumbs } from "./components.js";
import { escapeHtml as esc } from "./format.js";

// The Regions page (/regions/5a): a class's schools on a map of Mississippi, each a dot numbered by
// its region, every region's shape, and the schools listed by region. The data is written by the
// share-assets step (backend/prefect/share_regions.py) to /static/regions/: map.json (the state and
// its counties, projected to Mississippi Transverse Mercator, in 100 m units), index.json (the
// seasons) and {season}.json (that season's schools and region shapes). The region shapes are drawn
// around each region's schools (backend/helpers/region_map.py); MHSAA draws no boundaries.
//
// The markup functions here are pure, so they run under node; static_pages-style twins in
// backend/helpers/region_pages.py write the same page for search engines (renderer_parity_test.py).

export const REGIONS_DATA = "/static/regions";

export const MAP_NOTE = "Each dot is a school, at the location the site has for it (for a public school, the federal NCES geocode "
  + "of its address). The shaded shapes are drawn around each region’s schools; MHSAA doesn’t draw region "
  + "boundaries. County lines: U.S. Census Bureau.";

/** The note under the map (a function, so the parity test can ask for it). */
export function mapNote() {
  return MAP_NOTE;
}

/** "/regions/5a". */
export function regionsPath(clazz) {
  return `/regions/${clazz}a`;
}

/** "Class 5A Regions". */
export function regionsTitle(clazz) {
  return `Class ${clazz}A Regions`;
}

/** "2027 and 2028 seasons", or "2026 season". */
export function seasonsLabel(seasons) {
  return `${seasons.join(" and ")} ${seasons.length > 1 ? "seasons" : "season"}`;
}

/** "Region 2-5A" (the site's {region}-{class}A). */
export function place(p) {
  return p ? `Region ${p.region}-${p.class}A` : "";
}

/** "2-5A". */
export function shortPlace(p) {
  return p ? `${p.region}-${p.class}A` : "";
}

/** Where a school was the season before, for its line in the list: "4-4A in 2026", "New school". */
export function teamNote(school, priorSeason) {
  if (priorSeason == null) return "";
  if (school.before) return `${shortPlace(school.before)} in ${priorSeason}`;
  if (school.successor_of) return "New school";
  return `Not in a region in ${priorSeason}`;
}

/** A team's line under the map once it's picked: "Region 2-5A · Moved up from Region 4-4A (2026)". */
export function teamChange(school, priorSeason) {
  if (priorSeason == null) return "";
  const was = school.before;
  if (!was) return school.successor_of ? `New school, on ${school.successor_of}’s campus` : `Not in a region in ${priorSeason}`;
  if (was.class !== school.class) return `Moved ${school.class > was.class ? "up" : "down"} from ${place(was)} (${priorSeason})`;
  if (was.region !== school.region) return `Moved from ${place(was)} (${priorSeason})`;
  return `Also ${place(was)} in ${priorSeason}`;
}

/**
 * Where a region's heading links: its standings in the newest of the choice's seasons that has
 * games, or nowhere while none has (the region has no standings yet).
 */
export function standingsHref(clazz, region, standingsSeason, currentSeason) {
  if (standingsSeason == null) return null;
  const path = `/standings/${clazz}a/${region}`;
  return standingsSeason === currentSeason ? path : `${path}?season=${standingsSeason}`;
}

/** Home › Class 5A (the class's standings, as on the bracket page) › Class 5A Regions. */
export function regionsTrail(clazz) {
  return [["Home", "/"], [`Class ${clazz}A`, `/standings/${clazz}a`], [regionsTitle(clazz), regionsPath(clazz)]];
}

/** The page's heading: breadcrumbs, title, and which seasons and cycle it shows. */
export function regionsHeader(clazz, payload) {
  return `${breadcrumbs(regionsTrail(clazz))}<h1 class="title">${esc(regionsTitle(clazz))}</h1>`
    + `<p class="regions-sub">${esc(seasonsLabel(payload.seasons))} · MHSAA ${esc(payload.cycle)} regions</p>`;
}

/** Schools by name, letter case aside, as Python's sorted(key=str.lower) puts them. */
const byName = (a, b) => {
  const [x, y] = [a.toLowerCase(), b.toLowerCase()];
  return x < y ? -1 : x > y ? 1 : 0;
};

/** The class's schools by region, each region's heading linking to its standings when it has some. */
export function regionsLists(clazz, payload, currentSeason) {
  const schools = payload.schools.filter((s) => s.class === clazz);
  const regions = [...new Set(schools.map((s) => s.region))].sort((a, b) => a - b);
  return regions.map((g) => {
    const href = standingsHref(clazz, g, payload.standings_season, currentSeason);
    const heading = href ? `<a href="${esc(href)}">Region ${g}</a>` : `Region ${g}`;
    const items = schools.filter((s) => s.region === g)
      .sort((a, b) => byName(a.school, b.school))
      .map((s) => {
        const note = teamNote(s, payload.prior_season);
        return `<li><a href="${esc(regionsPath(clazz))}?team=${esc(s.slug)}" data-team="${esc(s.slug)}">${esc(s.school)}</a>`
          + (note ? ` <span class="regions-list__was">${esc(note)}</span>` : "")
          + "</li>";
      });
    return `<section class="regions-list__region"><h2 class="regions-list__name">`
      + `<span class="region-chip region-chip--${g}" aria-hidden="true">${g}</span>${heading}</h2>`
      + `<ul>${items.join("")}</ul></section>`;
  }).join("");
}

// ------------------------------------------------------------- the map

/** The SVG: land, the region shapes, county lines and names, the state's outline, then the dots. */
export function mapSvg(base, payload, clazz) {
  const counties = base.counties.map((c) => `<path class="map-county" d="${c.d}"/>`).join("");
  const names = base.counties.map((c) => `<text class="map-county-name" x="${c.label[0]}" y="${c.label[1]}">${esc(c.name)}</text>`).join("");
  const shapes = Object.entries(payload.regions[String(clazz)] ?? {})
    .map(([g, r]) => `<path class="map-region map-region--${g}" data-region="${g}" d="${r.d}"/>`).join("");
  const dots = payload.schools.filter((s) => s.class === clazz && s.x != null)
    .map((s) => `<g class="map-dot map-dot--${s.region}" data-team="${esc(s.slug)}" data-region="${s.region}" tabindex="-1">`
      + `<circle cx="${s.x}" cy="${s.y}" r="34"/><text x="${s.x}" y="${s.y}">${s.region}</text></g>`).join("");
  return `<svg class="regions-map__svg" viewBox="0 0 ${base.width} ${base.height}" role="img" `
    + `aria-label="Map of Mississippi with each Class ${clazz}A school as a dot numbered by its region">`
    + `<path class="map-land" d="${base.state}"/><g class="map-regions">${shapes}</g>`
    + `<g class="map-counties">${counties}</g><g class="map-county-names">${names}</g>`
    + `<path class="map-state" d="${base.state}"/><g class="map-dots">${dots}</g></svg>`;
}

/** The whole page: heading and controls, the map (with its zoom buttons and tooltip), the lists. */
export function regionsPage(clazz, base, payload, currentSeason, { controls = "", share = "" } = {}) {
  return `<div class="page regions-page"><header class="entry-head">${regionsHeader(clazz, payload)}${share}${controls}</header>`
    + `<div class="regions-layout"><figure class="regions-map"><div class="regions-map__frame" data-map>`
    + mapSvg(base, payload, clazz)
    + `<div class="regions-map__zoom"><button type="button" data-zoom="in" aria-label="Zoom in">+</button>`
    + `<button type="button" data-zoom="out" aria-label="Zoom out">−</button>`
    + `<button type="button" data-zoom="reset" aria-label="Show the whole state">⤢</button></div>`
    + `<div class="regions-map__hover" aria-hidden="true" hidden></div></div>`
    + `<figcaption class="regions-map__picked" aria-live="polite"></figcaption></figure>`
    + `<div class="regions-list">${regionsLists(clazz, payload, currentSeason)}</div></div>`
    + `<p class="regions-note">${esc(MAP_NOTE)}</p></div>`;
}

/** The box (in map units) that shows a region whole, with room around it, in the map's shape. */
export function regionView(box, base, pad = 0.3) {
  const [x0, y0, x1, y1] = box;
  let w = (x1 - x0) * (1 + 2 * pad);
  let h = (y1 - y0) * (1 + 2 * pad);
  const shape = base.width / base.height;
  if (w / h > shape) h = w / shape;
  else w = h * shape;
  w = Math.min(w, base.width);
  h = Math.min(h, base.height);
  return { x: (x0 + x1) / 2 - w / 2, y: (y0 + y1) / 2 - h / 2, w, h };
}

/**
 * Make the map on the page work: zoom (wheel, pinch, buttons), pan (drag), a name on hover, and a
 * team picked (from the map, the list or the page's link) highlighted with its region and zoomed
 * to. onPick(slug or null) tells the page, to keep the address in step.
 */
export function wireRegionsMap(root, base, payload, clazz, { picked = null, onPick = () => {} } = {}) {
  const frame = root.querySelector("[data-map]");
  const svg = frame?.querySelector("svg");
  if (!svg) return null;
  const hover = frame.querySelector(".regions-map__hover");
  const caption = root.querySelector(".regions-map__picked");
  const whole = { x: 0, y: 0, w: base.width, h: base.height };
  let view = { ...whole };
  const bySlug = new Map(payload.schools.filter((s) => s.class === clazz).map((s) => [s.slug, s]));

  const apply = () => {
    svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.w} ${view.h}`);
    const zoom = base.width / view.w;
    const px = view.w / (svg.getBoundingClientRect().width || 600);
    const r = 11 * px; // dots keep their size on screen at any zoom
    for (const g of svg.querySelectorAll(".map-dot")) {
      g.firstChild.setAttribute("r", r);
      g.lastChild.setAttribute("font-size", r * 1.2);
    }
    svg.classList.toggle("is-zoomed", zoom >= 2.2); // county names once there's room for them
    for (const t of svg.querySelectorAll(".map-county-name")) t.setAttribute("font-size", 40 / Math.max(1, zoom / 2.2));
  };
  const zoomAt = (factor, cx, cy) => {
    const w = Math.min(base.width, Math.max(base.width / 40, view.w / factor));
    const k = w / view.w;
    view = { x: cx - (cx - view.x) * k, y: cy - (cy - view.y) * k, w, h: view.h * k };
    apply();
  };
  const toMap = (clientX, clientY) => {
    const box = svg.getBoundingClientRect();
    return [view.x + ((clientX - box.left) / box.width) * view.w, view.y + ((clientY - box.top) / box.height) * view.h];
  };
  const middle = () => [view.x + view.w / 2, view.y + view.h / 2];

  const pick = (slug, { zoom = true } = {}) => {
    const school = slug ? bySlug.get(slug) : null;
    for (const g of svg.querySelectorAll(".map-dot")) {
      g.classList.toggle("is-picked", Boolean(school) && g.dataset.team === school.slug);
      g.classList.toggle("is-dim", Boolean(school) && Number(g.dataset.region) !== school.region);
    }
    for (const p of svg.querySelectorAll(".map-region")) p.classList.toggle("is-dim", Boolean(school) && Number(p.dataset.region) !== school.region);
    for (const a of root.querySelectorAll(".regions-list [data-team]")) {
      if (school && a.dataset.team === school.slug) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    }
    if (caption) {
      caption.textContent = school
        ? [`${school.school}: ${place(school)}`, teamChange(school, payload.prior_season), school.county ? `${school.city}, ${school.county} County` : ""].filter(Boolean).join(" · ")
        : "";
    }
    const box = school && payload.regions[String(clazz)]?.[String(school.region)]?.box;
    if (zoom) {
      view = box ? regionView(box, base) : { ...whole };
      apply();
    }
    return school;
  };

  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const [x, y] = toMap(e.clientX, e.clientY);
    zoomAt(e.deltaY < 0 ? 1.25 : 0.8, x, y);
  }, { passive: false });
  const pointers = new Map();
  let spread = null;
  let dragged = false;
  svg.addEventListener("pointerdown", (e) => {
    pointers.set(e.pointerId, e);
    dragged = false;
  });
  svg.addEventListener("pointermove", (e) => {
    const dot = e.target.closest?.(".map-dot");
    const school = dot && bySlug.get(dot.dataset.team);
    if (school && e.pointerType === "mouse") {
      const box = frame.getBoundingClientRect();
      hover.textContent = school.school;
      hover.style.left = `${e.clientX - box.left}px`;
      hover.style.top = `${e.clientY - box.top}px`;
      hover.hidden = false;
    } else hover.hidden = true;
    if (!pointers.has(e.pointerId)) return;
    const before = pointers.get(e.pointerId);
    pointers.set(e.pointerId, e);
    const box = svg.getBoundingClientRect();
    if (pointers.size === 1) {
      const dx = e.clientX - before.clientX;
      const dy = e.clientY - before.clientY;
      if (Math.abs(dx) + Math.abs(dy) > 2) {
        dragged = true;
        svg.setPointerCapture?.(e.pointerId);
      }
      view = { ...view, x: view.x - (dx / box.width) * view.w, y: view.y - (dy / box.height) * view.h };
      apply();
    } else if (pointers.size === 2) {
      dragged = true;
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      if (spread) zoomAt(d / spread, ...toMap((a.clientX + b.clientX) / 2, (a.clientY + b.clientY) / 2));
      spread = d;
    }
  });
  for (const type of ["pointerup", "pointercancel", "pointerleave"]) {
    svg.addEventListener(type, (e) => {
      pointers.delete(e.pointerId);
      spread = null;
      if (type === "pointerleave") hover.hidden = true;
    });
  }
  svg.addEventListener("click", (e) => {
    if (dragged) return;
    const dot = e.target.closest(".map-dot");
    const school = pick(dot ? dot.dataset.team : null, { zoom: Boolean(dot) });
    onPick(school?.slug ?? null);
  });
  frame.querySelector(".regions-map__zoom")?.addEventListener("click", (e) => {
    const b = e.target.closest("[data-zoom]");
    if (!b) return;
    if (b.dataset.zoom === "reset") {
      view = { ...whole };
      apply();
    } else zoomAt(b.dataset.zoom === "in" ? 1.6 : 1 / 1.6, ...middle());
  });
  root.querySelector(".regions-list")?.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-team]");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    pick(a.dataset.team);
    onPick(a.dataset.team);
    frame.scrollIntoView?.({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  });
  addEventListener("resize", apply);
  apply();
  if (picked) pick(picked);
  return { pick };
}

// ------------------------------------------------------------- data

const cache = new Map();

/** A file under /static/regions/, fetched once per page load. */
export function regionsFile(name) {
  if (!cache.has(name)) {
    cache.set(name, fetch(`${REGIONS_DATA}/${name}`).then((res) => {
      if (!res.ok) throw Object.assign(new Error(String(res.status)), { status: res.status });
      return res.json();
    }).catch((err) => {
      cache.delete(name);
      throw err;
    }));
  }
  return cache.get(name);
}

/** The choice a season belongs to (2028 is in "2027 and 2028"), or the default. */
export function pickOption(index, season) {
  return index.options.find((o) => o.seasons.includes(season)) ?? index.options.find((o) => o.season === index.default) ?? index.options[0];
}
