// Pure formatting helpers. No DOM access, so they run under `node --test`.

// Odds are float sums over enumerated outcomes; certainty can land a hair off
// 0 or 1, so anything this close counts as mathematically certain.
const EPS = 1e-9;

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

/**
 * Honest percentage text for a probability in [0, 1].
 * "0%" and "100%" are reserved for mathematical certainty; anything that
 * would round to them without being certain reads "<1%" / ">99%".
 */
export function formatPct(p) {
  if (p == null || Number.isNaN(p)) return "—";
  if (p <= EPS) return "0%";
  if (p >= 1 - EPS) return "100%";
  const rounded = Math.round(p * 100);
  if (rounded < 1) return "<1%";
  if (rounded > 99) return ">99%";
  return `${rounded}%`;
}

/**
 * Odds-ramp slot (1-5) for a probability, bucketed on the *displayed*
 * value so "79%" never lands in the 80s color.
 */
export function oddsBucket(p) {
  const text = formatPct(p);
  let shown;
  if (text === "—" || text === "<1%") shown = 0;
  else if (text === ">99%") shown = 99;
  else shown = Number.parseInt(text, 10);
  if (shown >= 80) return 5;
  return Math.floor(shown / 20) + 1;
}

export function isCertain(p) {
  return p != null && p >= 1 - EPS;
}

const DROPPED_WORDS = new Set(["county", "high", "school", "academy"]);

/** Fallback initials: first letters of significant words, max two. */
export function initials(name) {
  const words = String(name ?? "").split(/[\s\-/]+/).filter(Boolean);
  const significant = words.filter((w) => !DROPPED_WORDS.has(w.toLowerCase()));
  const pool = significant.length ? significant : words;
  return pool.slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}

/** Newspaper-style list: "A", "A and B", "A, B and C". */
export function joinNames(names) {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** Region record as W–L, adding –T only when there's a tie. */
export function recordText(w, l, t) {
  return t ? `${w}–${l}–${t}` : `${w}–${l}`;
}

/**
 * Winning-margin suffix for a chip. max is exclusive, null = unbounded.
 * Threshold form "by 11+", bounded range "by 8–10".
 */
export function marginText(min, max) {
  const lo = min ?? 1;
  if (lo <= 1 && max == null) return "";
  if (max == null) return ` by ${lo}+`;
  if (max === lo + 1) return ` by exactly ${lo}`;
  return ` by ${lo}–${max - 1}`;
}

const ORDINAL_WORDS = { 1: "first", 2: "second", 3: "third", 4: "fourth" };
export function ordinalWord(n) {
  return ORDINAL_WORDS[n] ?? `${n}th`;
}

/** "Oct 24" from an ISO date string, without timezone drift. */
export function shortDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ------------------------------------------------------------ color contrast

function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex ?? "").trim());
  if (!m) return null;
  const n = Number.parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function luminance([r, g, b]) {
  const lin = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function contrastRatio(hexA, hexB) {
  const a = hexToRgb(hexA);
  const b = hexToRgb(hexB);
  if (!a || !b) return 1;
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Text color (white or neutral-900) that reads best on a filled swatch. */
export function inkFor(bgHex) {
  return contrastRatio(bgHex, "#FFFFFF") >= contrastRatio(bgHex, "#272727") ? "#FFFFFF" : "#272727";
}

function rgbToHsl([r, g, b]) {
  const [rn, gn, bn] = [r / 255, g / 255, b / 255];
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h;
  if (max === rn) h = (gn - bn) / d + (gn < bn ? 6 : 0);
  else if (max === gn) h = (bn - rn) / d + 2;
  else h = (rn - gn) / d + 4;
  return [h / 6, s, l];
}

function hslToHex([h, s, l]) {
  const hue = (p, q, t) => {
    let u = t;
    if (u < 0) u += 1;
    if (u > 1) u -= 1;
    if (u < 1 / 6) return p + (q - p) * 6 * u;
    if (u < 1 / 2) return q;
    if (u < 2 / 3) return p + (q - p) * (2 / 3 - u) * 6;
    return p;
  };
  let rgb;
  if (s === 0) rgb = [l, l, l];
  else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    rgb = [hue(p, q, h + 1 / 3), hue(p, q, h), hue(p, q, h - 1 / 3)];
  }
  return `#${rgb.map((c) => Math.round(c * 255).toString(16).padStart(2, "0")).join("").toUpperCase()}`;
}

/**
 * Client-side fallback for a team color the backend hasn't clamped yet:
 * step lightness only (hue and saturation kept) toward whichever direction
 * gains contrast against the surface, until it reaches `target`.
 */
export function clampToSurface(hex, surfaceHex, target) {
  const rgb = hexToRgb(hex);
  if (!rgb) return null;
  if (contrastRatio(hex, surfaceHex) >= target) return hex.toUpperCase();
  const [h, s, l0] = rgbToHsl(rgb);
  const darken = luminance(hexToRgb(surfaceHex)) > 0.5;
  for (let i = 1; i <= 100; i += 1) {
    const l = darken ? l0 * (1 - i / 100) : l0 + (1 - l0) * (i / 100);
    const candidate = hslToHex([h, s, l]);
    if (contrastRatio(candidate, surfaceHex) >= target) return candidate;
  }
  return darken ? "#000000" : "#FFFFFF";
}

const LIGHT_SURFACE = "#FFFFFF";
const DARK_SURFACE = "#272727";

/**
 * UI-element team color for each theme (3:1 against the card surface).
 * Uses the backend's precomputed `color_variants` when present, else clamps
 * the raw primary hex once here.
 */
export function teamUiColors(team) {
  const primary = team?.color_variants?.primary;
  if (primary?.light?.ui && primary?.dark?.ui) {
    return { light: primary.light.ui, dark: primary.dark.ui };
  }
  const raw = primary?.raw ?? team?.primary_color_hex ?? null;
  if (!hexToRgb(raw)) return null;
  return {
    light: clampToSurface(raw, LIGHT_SURFACE, 3),
    dark: clampToSurface(raw, DARK_SURFACE, 3),
  };
}
