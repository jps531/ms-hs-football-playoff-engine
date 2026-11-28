// /moderate's Schools tab: find a school, then see and correct its look now (overrides), its past
// looks (school_looks), its logos (team_logos) and helmets (helmet_designs), and how the site draws it
// each season. Every change goes through the admin API; the page reloads the school after each.
// The pure pieces (labels, rows, forms) are exported for the tests.

import { combobox, comboboxForm } from "./combobox.js";
import { teamMark } from "./components.js";
import { escapeHtml as esc } from "./format.js";

/** The response's JSON, or an Error with the server's reason. */
export async function json(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `The server said ${res.status}.`);
  }
  return res.status === 204 ? null : res.json();
}

/**
 * A tab's school search (the site's search box, combobox.js): every school the site has, closed ones
 * too, each with its helmet and, if it's playing this season, its region. *form* is comboboxForm's
 * markup; *onPick(name)* opens one. Resolves to the names, once they're loaded.
 */
export async function schoolFinder(form, api, onPick) {
  let items = [];
  combobox(form, () => items, (school, input) => {
    input.value = school.school;
    onPick(school.school);
  }, { one: "school", many: "schools", meta: (t) => (t.region == null ? "" : `Region ${t.region}-${t.class_}A`) });
  const names = await api("/admin/schools").then(json);
  // The latest season's looks, for the helmets (a school that isn't in it gets its initials).
  const looks = await api("/seasons").then(json)
    .then((seasons) => api(`/teams?season=${Math.max(...seasons.map((s) => s.season))}`).then(json))
    .then((rows) => Object.fromEntries(rows.map((t) => [t.school, t])))
    .catch(() => ({}));
  items = names.map((n) => looks[n] ?? { school: n });
  return names;
}

/** "2015–2019", "Through 2019", "2020 on", "Every season": a span of seasons (null: open). */
export function spanLabel(first, last) {
  if (first == null && last == null) return "Every season";
  if (first == null) return `Through ${last}`;
  if (last == null) return `${first} on`;
  return first === last ? String(first) : `${first}–${last}`;
}

/** A field's value with its override: { value, stored, overridden }. */
export function withOverride(base, overrides, field) {
  const overridden = Object.prototype.hasOwnProperty.call(overrides ?? {}, field);
  return { value: overridden ? overrides[field] : base[field], stored: base[field], overridden };
}

/** A look's values with overrides (seasons as numbers or null; approximate a boolean). */
export function effectiveLook(look) {
  const out = {};
  for (const field of Object.keys(look.base)) out[field] = withOverride(look.base, look.overrides, field).value;
  for (const f of ["first_season", "last_season"]) out[f] = out[f] === "" || out[f] == null ? null : Number(out[f]);
  out.approximate = out.approximate === true || out.approximate === "true";
  return out;
}

/** A small color swatch and its name and hex: "■ Maroon #800000". */
export function colorText(name, hex) {
  const swatches = (hex ?? "").split(",").map((h) => h.trim()).filter(Boolean)
    .map((h) => `<i class="ms-swatch" style="background:${esc(h)}"></i>`).join("");
  return `${swatches}${esc(name || "—")}${hex ? ` <span class="ms-hex">${esc(hex)}</span>` : ""}`;
}

/** A /teams-like entry from a look, for its helmet in its colors (components.teamMark). */
export function lookTeam(hexPrimary, hexSecondary) {
  const variant = (raw) => ({ raw, light: { ui: raw, text: raw }, dark: { ui: raw, text: raw } });
  if (!hexPrimary) return null;
  const secondary = (hexSecondary ?? "").split(",").map((h) => h.trim()).filter(Boolean);
  return { color_variants: { primary: variant(hexPrimary), secondary: secondary.map(variant) }, secondary_color_hex: hexSecondary ?? "" };
}

// The school's own fields the Schools tab edits (SchoolOverrideField), in the order shown.
export const SCHOOL_FIELDS = [
  ["display_name", "Name shown", "text"],
  ["mascot", "Mascot", "text"],
  ["primary_color", "Primary color", "text"],
  ["primary_color_hex", "Primary hex", "hex"],
  ["secondary_color", "Secondary color", "text"],
  ["secondary_color_hex", "Secondary hex", "hexes"],
  ["latitude", "Latitude", "number"],
  ["longitude", "Longitude", "number"],
];

// A past look's fields (SchoolLookOverrideField).
export const LOOK_FIELDS = [
  ["first_season", "First season", "season"],
  ["last_season", "Last season", "season"],
  ["mascot", "Mascot", "text"],
  ["primary_color", "Primary color", "text"],
  ["primary_color_hex", "Primary hex", "hex"],
  ["secondary_color", "Secondary color", "text"],
  ["secondary_color_hex", "Secondary hex", "hexes"],
];

const HEX = /^#[0-9A-Fa-f]{6}$/;

/** What's wrong with a form value for *kind*, or "" (a blank season is allowed: open). */
export function invalid(kind, value) {
  const v = String(value ?? "").trim();
  if (kind === "season") return v === "" || (/^\d{4}$/.test(v) && Number(v) >= 1900 && Number(v) <= 2100) ? "" : "A year, or blank";
  if (kind === "hex") return v === "" || HEX.test(v) ? "" : "A color like #00843D";
  if (kind === "hexes") return v === "" || v.split(",").every((h) => HEX.test(h.trim())) ? "" : "Colors like #FFD700, #000000";
  if (kind === "number") return v === "" || Number.isFinite(Number(v)) ? "" : "A number";
  if (kind === "region") return /^[1-8]$/.test(v) ? "" : "A region, 1 to 8";
  if (kind === "count") return v === "" || /^\d{1,3}$/.test(v) ? "" : "A whole number";
  if (kind === "required") return v ? "" : "Required";
  return "";
}

/**
 * The override calls a form's changes take: for each field, set it (a value other than the stored one),
 * or clear its override (back to the stored value, or emptied when the stored value is empty too).
 * [{ field, value } | { field, clear: true }]
 */
export function overrideChanges(fields, base, overrides, values) {
  const out = [];
  for (const [field] of fields) {
    if (!(field in values)) continue;
    const now = withOverride(base, overrides, field);
    const next = String(values[field] ?? "").trim();
    const stored = base[field] == null ? "" : String(base[field]);
    if (next === String(now.value ?? "")) continue;
    if (next === stored) out.push({ field, clear: true });
    else out.push({ field, value: next });
  }
  return out;
}

/** The sentence a row shows for where its value comes from. */
const sourceTag = (overridden, from) => (overridden
  ? `<span class="ms-tag ms-tag--override">override</span>`
  : `<span class="ms-src">· ${esc(from)}</span>`);

/** A labeled input for a form. */
export function input(field, label, kind, value, note = "") {
  const type = kind === "number" ? "text" : "text";
  const placeholder = kind === "season" ? (field === "first_season" ? "As far back as known" : "Still in use") : "";
  return `<label class="fb-field"><span>${esc(label)}</span>`
    + `<input name="${esc(field)}" type="${type}" value="${esc(value ?? "")}" data-kind="${kind}"${placeholder ? ` placeholder="${esc(placeholder)}"` : ""} autocomplete="off">`
    + (note ? `<small>${note}</small>` : "") + "</label>";
}

/** The school's look now: each field, where it comes from, and an Edit (or the open form). */
export function nowSection(school, editing) {
  const { base, overrides } = school;
  if (editing === "now") {
    const fields = SCHOOL_FIELDS.map(([f, label, kind]) => {
      const v = withOverride(base, overrides, f);
      return input(f, label, kind, v.value, v.overridden ? `Stored: ${esc(base[f] ?? "none")}` : "");
    }).join("");
    return `<section class="ms-sec"><h3>Its look now</h3><form class="fb-form ms-form" data-form="now">${fields}`
      + `<div class="ms-save"><button class="fb-submit" type="submit">Save</button><button type="button" class="mod-button" data-cancel>Cancel</button></div>`
      + `<p class="ms-src ms-wide">A value other than the stored one is kept as an override, which wins until you change it back.</p></form></section>`;
  }
  const row = (label, html, overridden) => `<div class="ms-row"><span class="ms-k">${esc(label)}</span><span>${html} ${sourceTag(overridden, "school data")}</span></div>`;
  const v = (f) => withOverride(base, overrides, f);
  const coords = v("latitude").value != null && v("longitude").value != null ? `${v("latitude").value}, ${v("longitude").value}` : "None";
  return `<section class="ms-sec"><h3>Its look now <button type="button" class="mod-button" data-edit="now">Edit</button></h3>`
    + row("Name shown", esc(v("display_name").value || school.school), v("display_name").overridden)
    + row("Mascot", esc(v("mascot").value || "—"), v("mascot").overridden)
    + row("Primary", colorText(v("primary_color").value, v("primary_color_hex").value), v("primary_color").overridden || v("primary_color_hex").overridden)
    + row("Secondary", colorText(v("secondary_color").value, v("secondary_color_hex").value), v("secondary_color").overridden || v("secondary_color_hex").overridden)
    + row("Campus", esc(coords), v("latitude").overridden || v("longitude").overridden)
    + "</section>";
}

/** A past look's row, or its open form. */
export function lookRow(look, editing) {
  const e = effectiveLook(look);
  const mark = teamMark("", lookTeam(e.primary_color_hex, e.secondary_color_hex), { size: 32 });
  if (editing === `look-${look.id}`) {
    const fields = LOOK_FIELDS.map(([f, label, kind]) => {
      const v = withOverride(look.base, look.overrides, f);
      const from = look.source === "file" ? "From the file" : "Added here";
      return input(f, label, kind, v.value, v.overridden ? `${from}: ${esc(look.base[f] ?? "blank")} <span class="ms-tag ms-tag--override">override</span>` : "");
    }).join("");
    return `<div class="ms-look ms-look--open">${mark}<form class="fb-form ms-form" data-form="look" data-id="${look.id}">${fields}`
      + `<label class="ms-check ms-wide"><input type="checkbox" name="approximate"${e.approximate ? " checked" : ""}> Approximate colors (standard shades, not the school’s own)</label>`
      + `<div class="ms-save"><button class="fb-submit" type="submit">Save</button><button type="button" class="mod-button" data-cancel>Cancel</button>`
      + (Object.keys(look.overrides).length ? `<button type="button" class="mod-button" data-reset-look="${look.id}">Reset to ${look.source === "file" ? "the file" : "as added"}</button>` : "")
      + (look.source === "moderator" ? `<button type="button" class="mod-button ms-danger" data-delete-look="${look.id}">Delete</button>` : "")
      + `</div><p class="ms-src ms-wide">${look.source === "file"
        ? "Your changes are kept as overrides of the looks file’s values. To remove this look, take it out of backend/data/school_looks.csv."
        : "Added here: the looks file’s pipeline leaves it alone."}</p></form></div>`;
  }
  const over = Object.keys(look.overrides).length ? `<span class="ms-tag ms-tag--override">overrides</span>` : "";
  return `<div class="ms-look">${mark}<span><span class="ms-when">${esc(spanLabel(e.first_season, e.last_season))}</span> · ${esc(e.mascot || "—")}`
    + `${e.approximate ? `<span class="ms-tag">approximate colors</span>` : ""}${over}<br>`
    + `<span class="ms-src">${colorText(e.primary_color, e.primary_color_hex)} · ${colorText(e.secondary_color, e.secondary_color_hex)} · ${look.source === "file" ? "from the file" : "added here"}</span></span>`
    + `<button type="button" class="mod-button" data-edit="look-${look.id}">Edit</button></div>`;
}

/** The form for a new past look. */
export function newLookForm() {
  return `<div class="ms-look ms-look--open"><form class="fb-form ms-form" data-form="new-look">`
    + LOOK_FIELDS.map(([f, label, kind]) => input(f, label, kind, "")).join("")
    + `<label class="ms-check ms-wide"><input type="checkbox" name="approximate"> Approximate colors (standard shades, not the school’s own)</label>`
    + input("note", "Note", "text", "")
    + `<div class="ms-save"><button class="fb-submit" type="submit">Add the look</button><button type="button" class="mod-button" data-cancel>Cancel</button></div></form></div>`;
}

/** An image path as a URL (*base*: where stored paths are served from; a full URL passes through). */
export function imageUrl(base, path) {
  if (!path) return "";
  return /^https?:/.test(path) ? path : `${base}/${path}`;
}

/** A logo's row, or its open form. */
export function logoRow(logo, base, editing) {
  const img = logo.image_url ? `<img class="ms-thumb" src="${esc(imageUrl(base, logo.image_url))}" alt="" width="40" height="40" loading="lazy">` : `<span class="ms-thumb ms-thumb--none">No image</span>`;
  const label = `<span><span class="ms-when">${esc(logo.logo_type[0].toUpperCase() + logo.logo_type.slice(1))}</span> · ${esc(spanLabel(logo.year_start, logo.year_end))}`
    + `${logo.is_primary ? `<span class="ms-tag">primary</span>` : ""}${logo.has_keyline ? `<span class="ms-tag">keyline</span>` : ""}`
    + (logo.notes ? `<br><span class="ms-src">${esc(logo.notes)}</span>` : "") + "</span>";
  if (editing !== `logo-${logo.id}`) return `<div class="ms-look">${img}${label}<button type="button" class="mod-button" data-edit="logo-${logo.id}">Edit</button></div>`;
  return `<div class="ms-look ms-look--open">${img}<form class="fb-form ms-form" data-form="logo" data-id="${logo.id}">`
    + input("year_start", "First season", "season", logo.year_start ?? "") + input("year_end", "Last season", "season", logo.year_end ?? "")
    + input("notes", "Notes", "text", logo.notes ?? "")
    + `<label class="ms-check"><input type="checkbox" name="is_primary"${logo.is_primary ? " checked" : ""}> Primary</label>`
    + `<label class="ms-check"><input type="checkbox" name="has_keyline"${logo.has_keyline ? " checked" : ""}> Has its keyline</label>`
    + `<label class="ms-field ms-wide"><span>${logo.image_url ? "Replace the image" : "Upload the image"}</span><input type="file" name="image" accept="image/*"></label>`
    + `<div class="ms-save"><button class="fb-submit" type="submit">Save</button><button type="button" class="mod-button" data-cancel>Cancel</button><button type="button" class="mod-button ms-danger" data-delete-logo="${logo.id}">Delete</button></div></form></div>`;
}

/** The form for a new logo. */
export function newLogoForm() {
  return `<div class="ms-look ms-look--open"><form class="fb-form ms-form" data-form="new-logo">`
    + `<label class="fb-field"><span>Type</span><select name="logo_type"><option value="primary">Primary</option><option value="secondary">Secondary</option><option value="tertiary">Tertiary</option></select></label>`
    + `<span></span>` + input("year_start", "First season", "season", "") + input("year_end", "Last season", "season", "")
    + input("notes", "Notes", "text", "")
    + `<label class="ms-check"><input type="checkbox" name="is_primary"> Primary</label>`
    + `<label class="ms-field ms-wide"><span>Image</span><input type="file" name="image" accept="image/*"></label>`
    + `<div class="ms-save"><button class="fb-submit" type="submit">Add the logo</button><button type="button" class="mod-button" data-cancel>Cancel</button></div></form></div>`;
}

/** A helmet design's row, or its open form. */
export function helmetRow(helmet, base, editing) {
  const path = helmet.image_right || helmet.image_left || helmet.photo;
  const img = path ? `<img class="ms-thumb" src="${esc(imageUrl(base, path))}" alt="" width="40" height="40" loading="lazy">` : `<span class="ms-thumb ms-thumb--none">No image</span>`;
  const what = [helmet.color, helmet.finish, helmet.logo, helmet.stripe].filter(Boolean).join(" · ");
  const label = `<span><span class="ms-when">${esc(spanLabel(helmet.year_first_worn, helmet.year_last_worn))}</span>`
    + `${helmet.is_primary ? `<span class="ms-tag">primary</span>` : ""}${what ? `<br><span class="ms-src">${esc(what)}</span>` : ""}</span>`;
  if (editing !== `helmet-${helmet.id}`) return `<div class="ms-look">${img}${label}<button type="button" class="mod-button" data-edit="helmet-${helmet.id}">Edit</button></div>`;
  return `<div class="ms-look ms-look--open">${img}<form class="fb-form ms-form" data-form="helmet" data-id="${helmet.id}">`
    + input("year_first_worn", "First season worn", "year", helmet.year_first_worn ?? "") + input("year_last_worn", "Last season worn", "season", helmet.year_last_worn ?? "")
    + input("color", "Color", "text", helmet.color ?? "") + input("finish", "Finish", "text", helmet.finish ?? "")
    + input("facemask_color", "Facemask", "text", helmet.facemask_color ?? "") + input("logo", "Logo", "text", helmet.logo ?? "")
    + input("stripe", "Stripe", "text", helmet.stripe ?? "") + input("notes", "Notes", "text", helmet.notes ?? "")
    + `<label class="ms-check ms-wide"><input type="checkbox" name="is_primary"${helmet.is_primary ? " checked" : ""}> Primary</label>`
    + ["right", "left", "photo"].map((t) => `<label class="fb-field"><span>${t === "photo" ? "Photo" : `Facing ${t}`}</span><input type="file" name="image_${t}" accept="image/*"></label>`).join("")
    + `<div class="ms-save"><button class="fb-submit" type="submit">Save</button><button type="button" class="mod-button" data-cancel>Cancel</button><button type="button" class="mod-button ms-danger" data-delete-helmet="${helmet.id}">Delete</button></div></form></div>`;
}

/** The form for a new helmet design. */
export function newHelmetForm() {
  return `<div class="ms-look ms-look--open"><form class="fb-form ms-form" data-form="new-helmet">`
    + input("year_first_worn", "First season worn", "year", "") + input("year_last_worn", "Last season worn", "season", "")
    + input("color", "Color", "text", "") + input("finish", "Finish", "text", "")
    + `<label class="ms-check ms-wide"><input type="checkbox" name="is_primary"> Primary</label>`
    + ["right", "left", "photo"].map((t) => `<label class="fb-field"><span>${t === "photo" ? "Photo" : `Facing ${t}`}</span><input type="file" name="image_${t}" accept="image/*"></label>`).join("")
    + `<div class="ms-save"><button class="fb-submit" type="submit">Add the helmet</button><button type="button" class="mod-button" data-cancel>Cancel</button></div></form></div>`;
}

/** A season's place: "Region 6-1A", "1A Independent", or "Independent". */
export function seasonPlace(row) {
  if (row.region == null) return row.class ? `${row.class}A Independent` : "Independent";
  return `Region ${row.region}-${row.class}A`;
}

/**
 * The school's seasons (school_seasons), newest first: each one's class and region and whether it's
 * playing, with an Edit (a quick fix until the season's region file has the change).
 */
export function seasonsSection(rows, editing) {
  const items = rows.map((r) => {
    if (editing !== `season-${r.season}`) {
      return `<div class="ms-row ms-row--action"><span class="ms-k">${esc(r.season)}</span>`
        + `<span>${esc(seasonPlace(r))}${r.is_active ? "" : ` <span class="ms-tag">not playing</span>`}</span>`
        + `<button type="button" class="mod-button" data-edit="season-${r.season}">Edit</button></div>`;
    }
    // An independent's class and region come from the region file only (this API can't clear a region).
    const fixed = r.region == null;
    return `<form class="fb-form ms-form" data-form="season" data-season="${r.season}"><p class="ms-when ms-wide">${esc(r.season)}</p>`
      + (fixed ? `<p class="ms-src ms-wide">${esc(seasonPlace(r))}: an independent’s class and region come from the region file.</p>`
        : `<label class="fb-field"><span>Class</span><select name="class">${[1, 2, 3, 4, 5, 6, 7].map((c) => `<option value="${c}"${c === r.class ? " selected" : ""}>${c}A</option>`).join("")}</select></label>`
          + input("region", "Region", "region", r.region))
      + `<label class="ms-check ms-wide"><input type="checkbox" name="is_active"${r.is_active ? " checked" : ""}> Playing this season</label>`
      + `<div class="ms-save"><button class="fb-submit" type="submit">Save</button><button type="button" class="mod-button" data-cancel>Cancel</button></div>`
      + `<p class="ms-src ms-wide">The next regions load writes the season’s region file over a class or region set here. A school not playing is left out of that season’s standings and odds.</p></form>`;
  }).join("");
  return `<section class="ms-sec"><h3>Seasons</h3>${items || `<p class="ms-src">None yet.</p>`}</section>`;
}

/** The season strip: each season's helmet as the site draws it (*seasons*: [{ season, team }]). */
export function seasonStrip(seasons) {
  if (!seasons.length) return `<p class="ms-src">No seasons on the site yet.</p>`;
  return `<div class="ms-strip">${seasons.map(({ season, team }) => `<span title="${esc(`${team.mascot || ""} ${season}`.trim())}">`
    + `${teamMark(team.school, team, { size: 32 })}${esc(season)}</span>`).join("")}</div>`
    + `<p class="ms-src">Each season as the site draws it: its helmet (or a plain one in its colors that season).</p>`;
}

/** The whole school: its heading and every section (*data*: what load() fetched; *editing*: the open form). */
export function schoolHtml(data, editing) {
  const { school, looks, logos, helmets, seasons } = data;
  const now = seasons[seasons.length - 1]?.team;
  const section = (title, add, rows, empty) => `<section class="ms-sec"><h3>${esc(title)}${add}</h3>${rows || `<p class="ms-src">${esc(empty)}</p>`}</section>`;
  return `<div class="ms-head">${teamMark(school.school, now, { size: 48 })}<h2>${esc(school.school)}</h2></div>`
    + (now ? `<p class="ms-sub">${esc(now.city || "")}${now.city ? " · " : ""}${now.region == null ? `${now.class_ ? `${now.class_}A ` : ""}Independent` : `Region ${now.region}-${now.class_}A`} in ${now.season}</p>` : "")
    + nowSection(school, editing)
    + section("Past looks", ` <button type="button" class="mod-button" data-edit="new-look">Add a look</button>`,
      (editing === "new-look" ? newLookForm() : "") + looks.map((l) => lookRow(l, editing)).join(""), "None: every season has its look now.")
    + section("Logos", ` <button type="button" class="mod-button" data-edit="new-logo">Add a logo</button>`,
      (editing === "new-logo" ? newLogoForm() : "") + logos.map((l) => logoRow(l, school.image_base, editing)).join(""), "None yet.")
    + section("Helmets", ` <button type="button" class="mod-button" data-edit="new-helmet">Add a helmet</button>`,
      (editing === "new-helmet" ? newHelmetForm() : "") + helmets.map((h) => helmetRow(h, school.image_base, editing)).join(""), "None yet: a plain helmet in its colors.")
    + `<section class="ms-sec"><h3>How it looks each season</h3>${seasonStrip(seasons)}</section>`
    + seasonsSection(data.seasonRows ?? [], editing)
    + `<section class="ms-sec"><h3>Maintenance</h3><div class="ms-row ms-row--action"><span class="ms-k">Colors</span>`
    + `<span>Work out ${esc(school.school)}’s color variants again from its colors</span>`
    + `<button type="button" class="mod-button" data-recompute>Recompute colors</button></div></section>`;
}

// ------------------------------------------------------------ the page

/**
 * The Schools tab in *root* (a container), calling the API with *api(path, opts)* (moderate.js's,
 * JSON) and *upload(path, file)* (multipart). Opens *start* (a school's name) when given.
 */
export function schoolsTab(root, { api, upload, start = null, onSchool = () => {} }) {
  let names = [];
  let data = null;
  let editing = null;

  const status = (text, bad = false) => {
    const el = root.querySelector("[data-ms-status]");
    if (el) {
      el.textContent = text;
      el.classList.toggle("is-error", bad);
    }
  };
  const draw = () => {
    const body = root.querySelector("[data-ms-school]");
    body.innerHTML = data ? schoolHtml(data, editing) : "";
    body.querySelector("form input:not([type=checkbox]):not([type=file])")?.focus();
  };

  async function load(name) {
    status(`Loading ${name}…`);
    const enc = encodeURIComponent(name);
    const [school, looks, logos, helmets, seasonList, seasonRows] = await Promise.all([
      api(`/admin/schools/${enc}`).then(json), api(`/admin/schools/${enc}/looks`).then(json),
      api(`/teams/${enc}/logos`).then(json), api(`/teams/${enc}/helmets`).then(json),
      api("/seasons").then(json), api(`/admin/school-seasons/${enc}`).then(json),
    ]);
    const all = await Promise.all(seasonList.map((s) => api(`/teams/${enc}?season=${s.season}`).then((r) => (r.ok ? r.json() : null))));
    const seasons = all.filter(Boolean).map((team) => ({ season: team.season, team })).sort((a, b) => a.season - b.season);
    data = { school, looks, logos, helmets, seasons, seasonRows };
    editing = null;
    draw();
    status("");
    onSchool(name);
  }

  const values = (form) => Object.fromEntries([...form.elements].filter((el) => el.name && el.type !== "file" && el.type !== "checkbox").map((el) => [el.name, el.value.trim()]));
  const checked = (form, name) => Boolean(form.elements[name]?.checked);
  const nullable = (v) => (v === "" ? null : v);
  const year = (v) => (v === "" ? null : Number(v));

  function check(form) {
    for (const el of form.querySelectorAll("input[data-kind]")) {
      const kind = el.dataset.kind === "year" ? (el.value.trim() ? "season" : "required") : el.dataset.kind;
      const problem = kind === "required" ? "A year" : invalid(kind, el.value);
      el.setCustomValidity(problem);
      if (problem) {
        el.reportValidity();
        return false;
      }
    }
    return true;
  }

  async function save(form) {
    const name = data.school.school;
    const enc = encodeURIComponent(name);
    const v = values(form);
    const kind = form.dataset.form;
    const id = form.dataset.id;
    if (kind === "season") {
      const season = form.dataset.season;
      const row = data.seasonRows.find((r) => String(r.season) === season);
      const active = checked(form, "is_active");
      const clazz = form.elements.class ? Number(form.elements.class.value) : row.class;
      const region = form.elements.region ? Number(v.region) : row.region;
      if (row.region != null && (clazz !== row.class || region !== row.region)) {
        await json(await api(`/admin/school-seasons/${enc}/${season}`, { method: "PUT", body: { class: clazz, region, is_active: active } }));
      } else if (active !== row.is_active) {
        await json(await api(`/admin/school-seasons/${enc}/${season}`, { method: "PATCH", body: { is_active: active } }));
      }
    } else if (kind === "now") {
      for (const c of overrideChanges(SCHOOL_FIELDS, data.school.base, data.school.overrides, v)) {
        await json(c.clear ? await api(`/admin/schools/${enc}/overrides/${c.field}`, { method: "DELETE" })
          : await api(`/admin/schools/${enc}/overrides`, { method: "PUT", body: { field: c.field, value: c.value } }));
      }
    } else if (kind === "look") {
      const look = data.looks.find((l) => String(l.id) === id);
      const base = { ...look.base, approximate: look.base.approximate ? "true" : "false" };
      const changes = overrideChanges([...LOOK_FIELDS, ["approximate"]], base, look.overrides, { ...v, approximate: checked(form, "approximate") ? "true" : "false" });
      for (const c of changes) {
        await json(c.clear ? await api(`/admin/looks/${id}/overrides/${c.field}`, { method: "DELETE" })
          : await api(`/admin/looks/${id}/overrides`, { method: "PUT", body: { field: c.field, value: c.value } }));
      }
    } else if (kind === "new-look") {
      await json(await api(`/admin/schools/${enc}/looks`, { method: "POST", body: {
        first_season: year(v.first_season), last_season: year(v.last_season), mascot: nullable(v.mascot),
        primary_color: nullable(v.primary_color), secondary_color: nullable(v.secondary_color),
        primary_color_hex: nullable(v.primary_color_hex), secondary_color_hex: nullable(v.secondary_color_hex),
        approximate: checked(form, "approximate"), note: nullable(v.note) } }));
    } else if (kind === "logo" || kind === "new-logo") {
      const body = { year_start: year(v.year_start), year_end: year(v.year_end), is_primary: checked(form, "is_primary"), notes: nullable(v.notes) };
      const logo = kind === "logo"
        ? await json(await api(`/admin/logos/${id}`, { method: "PATCH", body: { ...body, has_keyline: checked(form, "has_keyline") } }))
        : await json(await api("/admin/logos", { method: "POST", body: { ...body, school: name, logo_type: v.logo_type } }));
      const file = form.elements.image?.files?.[0];
      if (file) await json(await upload(`/images/team-logos/${logo.id}`, file));
    } else if (kind === "helmet" || kind === "new-helmet") {
      const body = { year_first_worn: Number(v.year_first_worn), year_last_worn: year(v.year_last_worn), color: nullable(v.color),
        finish: nullable(v.finish), is_primary: checked(form, "is_primary") };
      if (kind === "helmet") Object.assign(body, { facemask_color: nullable(v.facemask_color), logo: nullable(v.logo), stripe: nullable(v.stripe), notes: nullable(v.notes) });
      const helmet = kind === "helmet"
        ? await json(await api(`/admin/helmets/${id}`, { method: "PATCH", body }))
        : await json(await api("/admin/helmets", { method: "POST", body: { ...body, school: name } }));
      for (const t of ["right", "left", "photo"]) {
        const file = form.elements[`image_${t}`]?.files?.[0];
        if (file) await json(await upload(`/images/helmets/${helmet.id}/${t}`, file));
      }
    }
  }

  root.innerHTML = `<div class="ms-find">${comboboxForm({ id: "ms-school", placeholder: "Find a school", list: "Schools", attrs: " data-ms-find" })}</div>`
    + `<p class="fb-status" data-ms-status role="status"></p><div data-ms-school></div>`;

  root.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (e.target.matches("[data-ms-find]")) return; // the search box picks (schoolFinder)
    const form = e.target.closest("form[data-form]");
    if (!form || !check(form)) return;
    const buttons = form.querySelectorAll("button");
    buttons.forEach((b) => { b.disabled = true; });
    status("Saving…");
    try {
      await save(form);
      await load(data.school.school);
      status("Saved. The images redraw at the next share-assets run.");
    } catch (err) {
      buttons.forEach((b) => { b.disabled = false; });
      status(err.message, true);
    }
  });

  // A value refused is fixed by typing: its message goes (or the browser would block every later submit).
  root.addEventListener("input", (e) => {
    if (e.target.matches("input[data-kind]")) e.target.setCustomValidity("");
  });

  root.addEventListener("click", async (e) => {
    const edit = e.target.closest("[data-edit]");
    if (edit) {
      editing = edit.dataset.edit;
      draw();
      return;
    }
    if (e.target.closest("[data-recompute]")) {
      status("Recomputing…");
      try {
        await json(await api(`/admin/schools/${encodeURIComponent(data.school.school)}/recompute-colors`, { method: "POST" }));
        await load(data.school.school);
        status("Colors recomputed.");
      } catch (err) {
        status(err.message, true);
      }
      return;
    }
    if (e.target.closest("[data-cancel]")) {
      editing = null;
      draw();
      return;
    }
    const del = e.target.closest("[data-delete-look], [data-delete-logo], [data-delete-helmet], [data-reset-look]");
    if (!del) return;
    const [what, id] = Object.entries(del.dataset)[0];
    const words = { deleteLook: "Delete this look?", deleteLogo: "Delete this logo?", deleteHelmet: "Delete this helmet design?", resetLook: "Remove every override of this look?" };
    if (!window.confirm(words[what])) return;
    status("Saving…");
    try {
      if (what === "resetLook") {
        const look = data.looks.find((l) => String(l.id) === id);
        for (const field of Object.keys(look.overrides)) await json(await api(`/admin/looks/${id}/overrides/${field}`, { method: "DELETE" }));
      } else {
        const path = { deleteLook: `/admin/looks/${id}`, deleteLogo: `/admin/logos/${id}`, deleteHelmet: `/admin/helmets/${id}` }[what];
        await json(await api(path, { method: "DELETE" }));
      }
      await load(data.school.school);
      status("Saved.");
    } catch (err) {
      status(err.message, true);
    }
  });

  schoolFinder(root.querySelector("[data-ms-find]"), api, (name) => load(name).catch((err) => status(err.message, true))).then((list) => {
    names = list;
    if (start && names.includes(start)) {
      root.querySelector("#ms-school").value = start;
      load(start).catch((err) => status(err.message, true));
    }
  }).catch((err) => status(err.message, true));
}
