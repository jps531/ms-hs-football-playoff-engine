// The About page's "On this page" (about.html's .toc): on a wide screen, a list beside the text that
// marks the section you're reading; on a phone, a bar under the header that says it, and opens to the
// list. Each heading also gets a link to itself, to share a section.
(() => {
  const toc = document.querySelector(".toc");
  const details = toc?.querySelector(".toc__details");
  if (!toc || !details) return;
  const current = toc.querySelector(".toc__current");
  const links = [...toc.querySelectorAll(".toc__list a")];
  const heads = links.map((a) => document.getElementById(decodeURIComponent(a.hash.slice(1)))).filter(Boolean);
  const names = new Map(heads.map((h) => [h, h.textContent.trim()]));

  // Wide: the list stays open beside the text. Narrow: the bar, closed until tapped.
  const wide = matchMedia("(min-width: 1100px)");
  const layout = () => {
    toc.classList.add("is-ready");
    toc.classList.toggle("is-bar", !wide.matches);
    details.open = wide.matches;
  };
  wide.addEventListener("change", layout);
  layout();
  details.querySelector("summary").addEventListener("click", (e) => { if (wide.matches) e.preventDefault(); });
  // The bar closes once a section's picked, or on Escape or a tap elsewhere.
  toc.addEventListener("click", (e) => { if (!wide.matches && e.target.closest(".toc__list a, .toc__top a")) details.open = false; });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !wide.matches && details.open) {
      details.open = false;
      details.querySelector("summary").focus();
    }
  });
  document.addEventListener("click", (e) => { if (!wide.matches && details.open && !toc.contains(e.target)) details.open = false; });

  // The section you're reading: the last heading above the line under the header (and the bar).
  const spy = () => {
    const line = toc.classList.contains("is-bar") ? toc.getBoundingClientRect().bottom + 32 : 120; // below where a jump puts a heading (scroll-margin-top)
    let on = null;
    for (const h of heads) if (h.getBoundingClientRect().top <= line) on = h;
    for (const a of links) {
      if (on && a.hash === `#${on.id}`) a.setAttribute("aria-current", "location");
      else a.removeAttribute("aria-current");
    }
    current.textContent = on ? names.get(on) : "";
  };
  let frame = 0;
  addEventListener("scroll", () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; spy(); }); }, { passive: true });
  addEventListener("resize", spy);
  spy();

  // Each heading's link to itself ("#"), shown on hover or focus (always, on a touch screen).
  for (const h of heads) {
    const a = document.createElement("a");
    a.className = "heading-link";
    a.href = `#${h.id}`;
    a.setAttribute("aria-label", `Link to “${names.get(h)}”`);
    a.textContent = "#";
    h.append(a);
  }
})();
