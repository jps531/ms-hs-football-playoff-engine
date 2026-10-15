// Cloudflare Turnstile on the feedback forms.
//
// The server says whether Turnstile is on (GET /client-config gives the site
// key). When it is, each form gets a widget that stays invisible unless
// Cloudflare wants an interaction, and its token rides along with the
// submission. Tokens are single-use, so the widget resets after every attempt.

import { clientConfig } from "./config.js";

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=__mshsfTurnstileReady";
const WAIT_MS = 5000; // how long a send waits for a token still on its way

let script = null;
const widgets = new WeakMap(); // form -> widget id

/** Widget options for a form: invisible unless needed, themed to the page. */
export function widgetOptions(siteKey, { dark = false, action = "feedback" } = {}) {
  return {
    sitekey: siteKey,
    action,
    theme: dark ? "dark" : "light",
    size: "flexible",
    appearance: "interaction-only",
  };
}

function loadScript() {
  script ??= new Promise((resolve, reject) => {
    window.__mshsfTurnstileReady = () => resolve(window.turnstile);
    const tag = document.createElement("script");
    tag.src = SCRIPT;
    tag.async = true;
    tag.onerror = () => {
      script = null; // a later form can try again
      tag.remove();
      reject(new Error("Turnstile didn't load"));
    };
    document.head.append(tag);
  });
  return script;
}

/** Put a widget in the form's .fb-turnstile slot, if Turnstile is on. */
export async function mountTurnstile(form, api) {
  const slot = form?.querySelector(".fb-turnstile");
  if (!slot) return;
  const { turnstile_site_key: siteKey } = await clientConfig(api);
  if (!siteKey) return;
  form.dataset.turnstile = "loading";
  try {
    const turnstile = await loadScript();
    if (!form.isConnected) return;
    const dark = document.documentElement.classList.contains("dark");
    widgets.set(form, turnstile.render(slot, widgetOptions(siteKey, { dark, action: form.dataset.mode })));
    form.dataset.turnstile = "ready";
  } catch {
    form.dataset.turnstile = "unavailable";
  }
}

/**
 * The token to send with the form: { token } when there is one (or Turnstile is
 * off, token null), else { problem } as a sentence for the form. Waits briefly
 * for a token that's still being worked out.
 */
export async function turnstileToken(form) {
  const state = form.dataset.turnstile;
  if (!state) return { token: null };
  if (state === "unavailable") {
    return { problem: "Our spam check couldn’t load. If you use a content blocker, allow challenges.cloudflare.com and try again." };
  }
  const deadline = Date.now() + WAIT_MS;
  while (Date.now() < deadline) {
    const id = widgets.get(form);
    const token = id !== undefined ? window.turnstile?.getResponse(id) : null;
    if (token) return { token };
    await new Promise((r) => setTimeout(r, 250));
  }
  return { problem: "We’re still checking you’re not a bot. If a box appeared below, complete it, then send again." };
}

/** Clear a used token so the next attempt gets a fresh one. */
export function resetTurnstile(form) {
  const id = widgets.get(form);
  if (id !== undefined) window.turnstile?.reset(id);
}

/** Remove a form's widget before the form leaves the page. */
export function removeTurnstile(form) {
  const id = form && widgets.get(form);
  if (id === undefined || id === null) return;
  window.turnstile?.remove(id);
  widgets.delete(form);
}
