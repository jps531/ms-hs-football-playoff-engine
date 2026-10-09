// Light / dark / system theme. The initial class is set by an inline snippet
// in <head> (to avoid a flash); this wires the header dropdown. "System"
// (the default) follows the device setting and stores nothing; picking Light
// or Dark is remembered on this device.
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
  const select = document.getElementById("theme-select");
  if (select) select.value = stored() ?? "system";
  apply();
  media.addEventListener("change", apply);
  select?.addEventListener("change", () => {
    try {
      if (select.value === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, select.value);
    } catch { /* storage unavailable: the choice lasts for this page only */ }
    if (select.value === "system") root.classList.toggle("dark", media.matches);
    else root.classList.toggle("dark", select.value === "dark");
  });
})();
