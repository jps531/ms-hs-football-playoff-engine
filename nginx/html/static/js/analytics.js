// Visit and feature counts, through PostHog Cloud, as the methodology page's
// "What we measure" describes. Off unless the server has a PostHog project
// key (client-config's posthog_key). No cookies or browser storage
// (cookieless mode: PostHog counts unique visitors from a daily hash), no
// autocapture or session recording: only page views and the named events
// the app sends, which never carry form text or anything personal. The
// library is served from this site and events go out through nginx's
// /relay/, so no outside script runs here.
//
// Campaign tags (utm_source=facebook and the like) on the link a visit
// arrives by stay in the address bar until the first page view has counted
// them, then come off, so a copied link doesn't carry them on.

import { clientConfig } from "./config.js";

const CAMPAIGN_TAG = /^utm_/;
// Ad-click IDs (Facebook's fbclid, Google's gclid…) tie a visit to one person's click on another
// site, so they're dropped from every event; the referring site still says where a visit came from.
const CLICK_IDS = ["fbclid", "gclid", "gclsrc", "dclid", "gbraid", "wbraid", "gad_source", "msclkid", "twclid",
  "igshid", "ttclid", "li_fat_id", "rdt_cid", "epik", "qclid", "sccid", "mc_cid", "irclid", "_kx", "bfcid", "oppref"];

/** A URL without ad-click IDs in its query string (anything that isn't a URL comes back as is). */
export function urlWithoutClickIds(url) {
  if (typeof url !== "string" || !url.includes("?")) return url;
  try {
    const u = new URL(url);
    for (const k of CLICK_IDS) u.searchParams.delete(k);
    return u.toString();
  } catch {
    return url;
  }
}

/** An event's properties without ad-click IDs, in their own fields or in any URL they carry. */
export function withoutClickIds(props) {
  if (!props) return props;
  const out = {};
  for (const [k, v] of Object.entries(props)) if (!CLICK_IDS.includes(k)) out[k] = urlWithoutClickIds(v);
  return out;
}

let posthog = null;
let queue = []; // events sent before the library loads; null once analytics is off
let tagsCounted = false;

/** Whether the address bar should still carry the arrival link's campaign tags. */
export function keepCampaignTags() {
  return !tagsCounted;
}

/** The campaign tags in a query string, as [name, value] pairs. */
export function campaignTags(search) {
  return [...new URLSearchParams(search)].filter(([k]) => CAMPAIGN_TAG.test(k));
}

/** A query string without its campaign tags ("" when nothing else is left). */
export function withoutCampaignTags(search) {
  const q = new URLSearchParams(search);
  for (const k of [...q.keys()]) if (CAMPAIGN_TAG.test(k)) q.delete(k);
  const rest = q.toString();
  return rest ? `?${rest}` : "";
}

function dropCampaignTags() {
  tagsCounted = true;
  if (!campaignTags(location.search).length) return;
  history.replaceState(history.state, "", location.pathname + withoutCampaignTags(location.search) + location.hash);
}

/** Start counting, if this server is set up for it. */
export async function startAnalytics(api) {
  const cfg = await clientConfig(api);
  if (!cfg.posthog_key) {
    queue = null;
    dropCampaignTags();
    return;
  }
  const { default: ph } = await import("./vendor/posthog-js.js");
  ph.init(cfg.posthog_key, {
    api_host: "/relay",
    ui_host: cfg.posthog_ui_host || "https://us.posthog.com",
    cookieless_mode: "always",
    person_profiles: "never", // no person records; identify() becomes a no-op
    capture_pageview: "history_change",
    capture_pageleave: false,
    autocapture: false,
    capture_dead_clicks: false,
    capture_heatmaps: false,
    capture_exceptions: false,
    disable_session_recording: true,
    disable_surveys: true,
    disable_web_experiments: true,
    advanced_disable_flags: true,
    before_send: (event) => {
      if (!event) return event;
      // The arrival page view carries the campaign tags; once it's on its way they can go.
      if (event.event === "$pageview" && !tagsCounted) setTimeout(dropCampaignTags, 0);
      return { ...event, properties: withoutClickIds(event.properties), $set_once: withoutClickIds(event.$set_once) };
    },
    loaded: (instance) => {
      posthog = instance;
      for (const [name, props] of queue ?? []) instance.capture(name, props);
      queue = [];
    },
  });
}

/**
 * Count a feature being used. *props* say which, never who: no names, emails or typed text.
 * With *leaving*, the event goes out at once by beacon, since a link that loads a new page
 * would otherwise unload this one before the next batch is sent.
 */
export function track(name, props = {}, { leaving = false } = {}) {
  if (posthog) posthog.capture(name, props, leaving ? { transport: "sendBeacon", send_instantly: true } : undefined);
  else queue?.push([name, props]);
}
