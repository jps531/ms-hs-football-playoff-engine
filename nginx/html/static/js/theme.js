// Light / dark / system theme. The initial class is set by an inline snippet
// in <head> (to avoid a flash); this wires the header's three-way toggle.
// "System" (the default) follows the device setting and stores nothing;
// picking Light or Dark is remembered on this device.
//
// The toggle is a radiogroup with a roving tabindex, like the class
// scrubber: one tab stop, arrow keys move between (and select) the choices.
(() => {
  const KEY = "mshsf.theme";
  const root = document.documentElement;
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const stored = () => {
    try {
      const v = localStorage.getItem(KEY);
      return v === "light" || v === "dark" ? v : null;
    } catch {
      return null;
    }
  };
  const apply = () => {
    const choice = stored();
    root.classList.toggle("dark", choice ? choice === "dark" : media.matches);
  };

  const group = document.querySelector(".theme-toggle");
  const items = group ? [...group.querySelectorAll("[data-theme]")] : [];
  const mark = (choice) => {
    for (const item of items) {
      const on = item.dataset.theme === choice;
      item.setAttribute("aria-checked", String(on));
      item.tabIndex = on ? 0 : -1;
    }
  };
  const choose = (choice) => {
    try {
      if (choice === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, choice);
    } catch { /* storage unavailable: the choice lasts for this page only */ }
    root.classList.toggle("dark", choice === "system" ? media.matches : choice === "dark");
    mark(choice);
  };

  mark(stored() ?? "system");
  apply();
  media.addEventListener("change", apply);

  group?.addEventListener("click", (e) => {
    const item = e.target.closest("[data-theme]");
    if (item) choose(item.dataset.theme);
  });
  group?.addEventListener("keydown", (e) => {
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    const moves = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    let next;
    if (e.key in moves) next = (i + moves[e.key] + items.length) % items.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    else return;
    e.preventDefault();
    choose(items[next].dataset.theme);
    items[next].focus();
  });
})();
