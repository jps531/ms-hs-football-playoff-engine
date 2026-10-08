// Light/dark theme. The initial class is set by an inline snippet in <head>
// (to avoid a flash); this wires the header toggle and follows the system
// setting until the reader picks one.
(() => {
  const KEY = "mshsf.theme";
  const root = document.documentElement;
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const stored = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
  const apply = (dark) => {
    root.classList.toggle("dark", dark);
    const button = document.getElementById("theme-toggle");
    if (button) button.textContent = dark ? "Light theme" : "Dark theme";
  };
  apply(root.classList.contains("dark"));
  media.addEventListener("change", (e) => { if (!stored()) apply(e.matches); });
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const dark = !root.classList.contains("dark");
    try { localStorage.setItem(KEY, dark ? "dark" : "light"); } catch { /* storage unavailable */ }
    apply(dark);
  });
})();
