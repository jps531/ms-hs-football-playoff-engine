// /moderate: sign in with Auth0, then review the submission queue.
// The pieces that don't touch the page are in moderation.js and auth.js.

import { clientConfig } from "./config.js";
import { completeSignIn, forgetToken, logoutUrl, signIn, storedToken } from "./auth.js";
import { escapeHtml as esc } from "./format.js";
import { STATUSES, itemHtml, typeFilters } from "./moderation.js";

const API = "/api/v1";
const PAGE_SIZE = 50;
const RETURN_KEY = "mshsf.mod.return"; // the filters to come back to after signing in
const TITLE = "Moderation — Mississippi High School Football";

const root = document.getElementById("mod");
const redirectUri = `${location.origin}/moderate`;
const store = (() => {
  try {
    return window.sessionStorage;
  } catch {
    const memory = new Map();
    return { getItem: (k) => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v), removeItem: (k) => memory.delete(k) };
  }
})();

const state = { cfg: null, token: null, status: "pending", type: "", items: [], counts: {}, more: false };

class SignedOut extends Error {}

// ------------------------------------------------------------ data

async function api(path, { method = "GET", body } = {}) {
  const headers = { Accept: "application/json", Authorization: `Bearer ${state.token}` };
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(API + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (res.status === 401) {
    forgetToken(store);
    state.token = null;
    throw new SignedOut("Your sign-in has expired. Please sign in again.");
  }
  return res;
}

function readFilters() {
  const q = new URLSearchParams(location.search);
  const status = q.get("status");
  state.status = STATUSES.some((s) => s.value === status) ? status : "pending";
  state.type = /^[a-z_]{1,40}$/.test(q.get("type") ?? "") ? q.get("type") : "";
}

function writeFilters() {
  const q = new URLSearchParams();
  if (state.status !== "pending") q.set("status", state.status);
  if (state.type) q.set("type", state.type);
  const query = q.toString();
  history.replaceState(null, "", `/moderate${query ? `?${query}` : ""}`);
}

// ------------------------------------------------------------ views

function message(title, text, actions = "") {
  root.innerHTML = `<section class="mod-message-card">
      <h2 class="sub-title">${esc(title)}</h2>
      ${text ? `<p class="prose muted">${esc(text)}</p>` : ""}
      ${actions}
    </section>`;
  root.querySelector("button")?.focus({ preventScroll: true });
}

function showSignedOut(note = "") {
  document.title = TITLE;
  message("Sign in to review submissions", note || "Moderators and owners only.",
    '<button type="button" class="fb-submit" data-signin>Sign in</button>');
}

const REFRESH_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>';

function chip(name, value, label, count, checked) {
  const badge = count ? ` <span class="mod-count">${count}<span class="visually-hidden"> pending</span></span>` : "";
  return `<label class="fb-cat"><input type="radio" name="${name}" value="${esc(value)}"${checked ? " checked" : ""}><span>${esc(label)}${badge}</span></label>`;
}

function shell() {
  const docs = state.cfg.api_docs_url
    ? `<a class="mod-button" href="${esc(state.cfg.api_docs_url)}" target="_blank" rel="noopener">API Docs</a>`
    : "";
  // The owner's links: the pipeline (Prefect) and, when this server sends visit counts, its PostHog
  // dashboards (web analytics, and the "Site activity" one of feature use).
  const ownerLink = (url, label) => (url
    ? `<a class="mod-button" href="${esc(url)}" target="_blank" rel="noopener" data-owner-only hidden>${label}</a>`
    : "");
  const analytics = ownerLink(state.cfg.posthog_dashboard_url, "Analytics")
    + ownerLink(state.cfg.posthog_activity_url, "Activity");
  root.innerHTML = `<div class="mod-account">
      <a class="mod-button" href="/prefect/" target="_blank" rel="noopener" data-prefect data-owner-only hidden>Prefect</a>
      ${analytics}
      ${docs}
      <button type="button" class="mod-button" data-signout>Sign out</button>
    </div>
    <div class="mod-filters">
      <fieldset class="mod-filter">
        <legend>Status</legend>
        <div class="fb-cats" data-filter="status"></div>
      </fieldset>
      <button type="button" class="mod-refresh" data-refresh aria-label="Refresh the queue" title="Refresh">${REFRESH_ICON}</button>
      <fieldset class="mod-filter">
        <legend>Type</legend>
        <div class="fb-cats" data-filter="type"></div>
      </fieldset>
    </div>
    <div class="mod-list" aria-live="polite"></div>
    <div class="mod-more"></div>`;
}

/** Redraw both chip rows (keeping focus on the chosen chip) and the tab title's count. */
function renderCounts() {
  const pending = Object.values(state.counts).reduce((a, b) => a + b, 0);
  const focused = document.activeElement?.name;
  const statusRow = root.querySelector('[data-filter="status"]');
  const typeRow = root.querySelector('[data-filter="type"]');
  if (statusRow) {
    statusRow.innerHTML = STATUSES.map((s) => chip("status", s.value, s.label, s.value === "pending" ? pending : 0, s.value === state.status)).join("");
  }
  if (typeRow) {
    // Counts are pending ones, so they only show while looking at pending.
    typeRow.innerHTML = typeFilters(state.counts, state.type)
      .map((t) => chip("type", t.value, t.label, state.status === "pending" ? t.count : 0, t.value === state.type))
      .join("");
  }
  if (focused === "status" || focused === "type") root.querySelector(`input[name="${focused}"]:checked`)?.focus();
  document.title = pending ? `(${pending}) ${TITLE}` : TITLE;
}

function renderList() {
  const list = root.querySelector(".mod-list");
  const now = Date.now();
  list.innerHTML = state.items.length
    ? state.items.map((item) => itemHtml(item, now)).join("")
    : `<p class="mod-empty muted">${state.status === "pending" ? "Nothing waiting. All caught up." : "Nothing here."}</p>`;
  root.querySelector(".mod-more").innerHTML = state.more
    ? '<button type="button" class="link-button" data-more>Load more</button>'
    : "";
}

// ------------------------------------------------------------ actions

async function load({ append = false } = {}) {
  const list = root.querySelector(".mod-list");
  const refresh = root.querySelector("[data-refresh]");
  list.setAttribute("aria-busy", "true");
  refresh?.classList.add("is-loading");
  const q = new URLSearchParams({
    status_filter: state.status,
    limit: String(PAGE_SIZE),
    offset: String(append ? state.items.length : 0),
  });
  if (state.type) q.set("type", state.type);
  try {
    const res = await api(`/moderation/queue?${q}`);
    if (res.status === 403) {
      message("This account isn’t a moderator", "Ask the site owner to give your account the moderator role, then sign in again.",
        '<button type="button" class="fb-submit" data-signout>Sign out</button>');
      return;
    }
    if (!res.ok) throw new Error(`The queue didn’t load (HTTP ${res.status}).`);
    const page = await res.json();
    state.items = append ? [...state.items, ...page.items] : page.items;
    state.counts = page.pending_counts;
    state.more = page.items.length === PAGE_SIZE;
    renderCounts();
    renderList();
  } catch (err) {
    if (err instanceof SignedOut) return showSignedOut(err.message);
    list.innerHTML = `<p class="fb-status is-error">${esc(err.message || "The queue didn’t load.")}</p>`;
  } finally {
    list.removeAttribute("aria-busy");
    refresh?.classList.remove("is-loading");
  }
}

async function decide(form, decision) {
  const id = Number(form.dataset.decide);
  const status = form.querySelector(".fb-status");
  const buttons = form.querySelectorAll("button");
  const notes = form.querySelector("textarea").value.trim() || null;
  buttons.forEach((b) => (b.disabled = true));
  status.classList.remove("is-error");
  status.textContent = decision === "approve" ? "Applying…" : "Saving…";
  try {
    const res = await api(`/moderation/submissions/${id}/${decision}`, { method: "POST", body: { notes } });
    if (!res.ok) {
      const detail = (await res.json().catch(() => null))?.detail;
      throw new Error(res.status === 409 ? `Already reviewed: ${detail ?? ""}`.trim() : detail || `That didn’t work (HTTP ${res.status}).`);
    }
    const updated = await res.json();
    const index = state.items.findIndex((i) => i.id === id);
    const before = state.items[index];
    state.items[index] = { ...before, ...updated };
    if (before.status === "pending" && state.counts[before.type]) state.counts[before.type] -= 1;
    renderCounts();
    const card = document.getElementById(`submission-${id}`);
    card.outerHTML = itemHtml(state.items[index]);
    const next = document.getElementById(`submission-${id}`)?.nextElementSibling?.querySelector("textarea");
    (next ?? document.getElementById(`submission-${id}-title`))?.focus({ preventScroll: false });
  } catch (err) {
    if (err instanceof SignedOut) return showSignedOut(err.message);
    status.classList.add("is-error");
    status.textContent = err.message;
    buttons.forEach((b) => (b.disabled = false));
  }
}

function signOut() {
  forgetToken(store);
  fetch(`${API}/auth/session`, { method: "DELETE" }).catch(() => {});
  location.assign(logoutUrl(state.cfg, redirectUri));
}

root.addEventListener("click", (e) => {
  if (e.target.closest("[data-signin]")) {
    store.setItem(RETURN_KEY, location.search);
    signIn(state.cfg, redirectUri, store);
  } else if (e.target.closest("[data-signout]")) signOut();
  else if (e.target.closest("[data-refresh]")) load();
  else if (e.target.closest("[data-more]")) load({ append: true });
});

root.addEventListener("change", (e) => {
  if (e.target.name === "status") state.status = e.target.value;
  else if (e.target.name === "type") state.type = e.target.value;
  else return;
  writeFilters();
  load();
});

root.addEventListener("submit", (e) => {
  const form = e.target.closest("[data-decide]");
  if (!form) return;
  e.preventDefault();
  decide(form, e.submitter?.value === "approve" ? "approve" : "reject");
});

// ------------------------------------------------------------ boot

async function boot() {
  state.cfg = await clientConfig(API);
  if (!state.cfg.auth0_client_id || !state.cfg.auth0_domain || !state.cfg.auth0_audience) {
    message("Sign-in isn’t set up on this server", "Set AUTH0_SPA_CLIENT_ID for the API (see docs/operations/VM_DEPLOYMENT.md).");
    return;
  }
  const params = new URLSearchParams(location.search);
  if (params.has("code") || params.has("error")) {
    const back = store.getItem(RETURN_KEY) ?? "";
    store.removeItem(RETURN_KEY);
    try {
      await completeSignIn(state.cfg, redirectUri, location.href, store);
    } catch (err) {
      history.replaceState(null, "", `/moderate${back}`);
      showSignedOut(err.message);
      return;
    }
    history.replaceState(null, "", `/moderate${back}`);
  }
  readFilters();
  state.token = storedToken(store);
  if (!state.token) {
    showSignedOut();
    return;
  }
  shell();
  await load();
  // Prefect is the owner's alone (the API refuses anyone else), so only the
  // owner sees its link (and the analytics dashboard's), and only the owner
  // needs the first-party cookie that lets the link open without a Bearer header.
  api("/users/me")
    .then((res) => (res.ok ? res.json() : null))
    .then((me) => {
      if (me?.role !== "owner") return;
      for (const link of root.querySelectorAll("[data-owner-only]")) link.removeAttribute("hidden");
      return api("/auth/session", { method: "POST" });
    })
    .catch(() => {});
}

boot();
