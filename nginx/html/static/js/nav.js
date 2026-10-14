// Main nav (header links on wide screens, tab bar on phones): point
// Standings and Bracket at the class last viewed on this device. On the
// standings and bracket pages app.js keeps these links current as you move
// around (class, region, season, week, odds, picked team).
(() => {
  let clazz = null;
  try { clazz = Number(localStorage.getItem("mshsf.class")); } catch { /* storage unavailable */ }
  if (!(clazz >= 1 && clazz <= 7)) clazz = 1;
  for (const a of document.querySelectorAll('[data-nav="standings"]')) a.href = `/standings/${clazz}a`;
  for (const a of document.querySelectorAll('[data-nav="bracket"]')) a.href = `/brackets/${clazz}a`;
})();
