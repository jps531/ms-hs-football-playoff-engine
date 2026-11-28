// The site's search box: a combobox that lists matches under the field as you type (best first, the
// top one highlighted, each with its helmet); arrow keys move the highlight, and Enter or a tap picks.
// Nothing happens until the reader commits. The header's, the Maps' and /moderate's use it.

import { escapeHtml as esc } from "./format.js";
import { teamMark } from "./components.js";
import { matchTeams } from "./search.js";

// Whether the last thing the reader did was a tap or click (not a key): a tap's pick lets go of the field.
// (Not under node --test, where the pure pieces of the modules that use this are tested.)
let byPointer = false;
if (typeof document !== "undefined") {
  document.addEventListener("pointerdown", () => { byPointer = true; }, true);
  document.addEventListener("keydown", () => { byPointer = false; }, true);
}

/**
 * A search box's markup: the field (id *id*), its results list and a status line for screen readers.
 * *list* names the list for a screen reader; *page*: the in-page look (team-search--page), not the header's.
 */
export function comboboxForm({ id, placeholder, label = placeholder, list = "Teams", page = true, attrs = "" }) {
  return `<form class="team-search${page ? " team-search--page" : ""}" role="search"${attrs}>`
    + `<label for="${esc(id)}" class="visually-hidden">${esc(label)}</label>`
    + `<input id="${esc(id)}" type="search" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${esc(id)}-results"`
    + ` placeholder="${esc(placeholder)}" autocomplete="off" autocapitalize="words" autocorrect="off" spellcheck="false" enterkeyhint="search">`
    + `<div class="team-results" hidden><ul id="${esc(id)}-results" role="listbox" aria-label="${esc(list)}"></ul><p class="team-results__empty" hidden></p></div>`
    + `<p class="visually-hidden" role="status"></p></form>`;
}

/**
 * Make a search box work: *form* holds the input, the results popup (its list
 * and empty note) and a status line for screen readers (comboboxForm's markup);
 * *teams()* is what can be found (objects with a school name); *onPick(team)*
 * commits. *options* (or a function returning them): one/many (what it finds),
 * meta(t) and mark(t) (a result's second line and helmet), and inPlace() (true
 * when a pick happens on the page, not away from it).
 */
export function combobox(form, teams, onPick, options = {}) {
  // What it finds and how a result reads; *options* can be a function, for a box that finds different
  // things at different times (the header's, while a map is in full screen).
  const words = () => ({
    one: "team", many: "teams", meta: () => "", mark: (t) => teamMark(t.school, t), inPlace: () => false,
    ...(typeof options === "function" ? options() : options),
  });
  const input = form?.querySelector("input[role=combobox]");
  if (!input) return null;
  const popup = form.querySelector(".team-results");
  const list = popup.querySelector("[role=listbox]");
  const empty = popup.querySelector(".team-results__empty");
  const status = form.querySelector("[role=status]");
  const prefix = `${list.id}-opt`;
  let matches = [];
  let active = -1;

  const open = (on) => {
    popup.hidden = !on;
    input.setAttribute("aria-expanded", String(on && matches.length > 0));
    if (!on) input.removeAttribute("aria-activedescendant");
  };
  const setActive = (i) => {
    active = i;
    list.querySelectorAll("[role=option]").forEach((el, k) => el.setAttribute("aria-selected", String(k === i)));
    const el = i >= 0 ? document.getElementById(`${prefix}-${i}`) : null;
    if (el) {
      input.setAttribute("aria-activedescendant", el.id);
      el.scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  };
  const update = () => {
    const query = input.value.trim();
    if (!query) {
      matches = [];
      status.textContent = "";
      open(false);
      return;
    }
    const all = teams();
    const loaded = all.length > 0;
    const { one, many, meta, mark } = words();
    matches = matchTeams(all, query);
    list.innerHTML = matches.map((t, i) => `<li id="${prefix}-${i}" role="option" aria-selected="false" data-index="${i}">
      ${mark(t)}<span class="team-results__name">${esc(t.school)}</span>
      <span class="team-results__meta">${esc(meta(t))}</span>
    </li>`).join("");
    empty.hidden = matches.length > 0;
    empty.textContent = loaded ? `No ${one} matches “${query}”.` : `Loading ${many}…`;
    status.textContent = !loaded ? ""
      : matches.length ? `${matches.length} ${matches.length === 1 ? one : many} found. Press Enter to pick ${matches[0].school}.`
        : `No ${many} found.`;
    open(true);
    setActive(matches.length ? 0 : -1);
  };
  const pick = (team) => {
    matches = [];
    open(false);
    // A box that picks in place (a map's): from the keyboard, focus stays in the field (the pick is
    // announced); a tap lets go of it, closing a phone's keyboard over the map.
    if (byPointer || !words().inPlace()) input.blur();
    onPick(team, input);
  };

  input.addEventListener("input", update);
  input.addEventListener("focus", () => { if (input.value.trim()) update(); });
  input.addEventListener("blur", () => open(false));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (popup.hidden) update();
      if (!matches.length) return;
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((active + step + matches.length) % matches.length);
    } else if (e.key === "Escape" && !popup.hidden) {
      e.preventDefault();
      open(false);
    }
  });
  // Enter (or the keyboard's Search key) commits the highlighted team.
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!input.value.trim()) return;
    if (popup.hidden) update();
    const team = matches[active] ?? matches[0];
    if (team) pick(team);
  });
  // Pressing a result mustn't blur the field first (that would close the list
  // before the tap lands); the click then picks the team.
  list.addEventListener("pointerdown", (e) => e.preventDefault());
  list.addEventListener("click", (e) => {
    const option = e.target.closest("[role=option]");
    if (option) pick(matches[Number(option.dataset.index)]);
  });
  list.addEventListener("pointermove", (e) => {
    const option = e.target.closest("[role=option]");
    if (option && Number(option.dataset.index) !== active) setActive(Number(option.dataset.index));
  });
  return { update, input };
}
