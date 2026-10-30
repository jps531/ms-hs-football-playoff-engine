import { test } from "node:test";
import assert from "node:assert/strict";
import {
  canApprove, canReject, decisionLabels, payloadValue, feedbackAbout, itemHtml, pageLink, relativeTime, scoreChange, typeFilters, typeLabel,
} from "../html/static/js/moderation.js";
import {
  authorizeUrl, base64url, challengeFor, completeSignIn, explainAuthError, logoutUrl, saveToken, storedToken, tokenRequest,
} from "../html/static/js/auth.js";

const SCORE = {
  id: 7, type: "score", status: "pending", school: "Oxford", submitted_at: "2026-10-14T12:00:00Z", reviewed_at: null,
  payload: { date: "2026-10-10", points_for: 21, points_against: 16, note: "MaxPreps", page: "/standings/7a/2" },
  moderator_notes: null,
  current_game: { opponent: "Tupelo", location: "away", points_for: 14, points_against: 16, result: "L" },
};
const FEEDBACK = {
  id: 8, type: "feedback", status: "pending", school: null, submitted_at: "2026-10-14T11:00:00Z", reviewed_at: null,
  payload: { subject: "Odds or scenarios · Region 2-7A · Oxford", message: "Line one\n<b>two</b>", category: "odds", email: "a@b.co", page: "//evil.example" },
  moderator_notes: null, current_game: null,
};

test("score change: current vs reported, from the school's side", () => {
  const s = scoreChange(SCORE);
  assert.deepEqual(s.current, { for: 14, against: 16, result: "L" });
  assert.deepEqual(s.reported, { for: 21, against: 16, result: "W" });
  assert.deepEqual(s.changed, { for: true, against: false });
  assert.equal(scoreChange({ ...SCORE, current_game: null }).current, null);
});

test("labels follow the type", () => {
  assert.equal(typeLabel(SCORE), "Score correction");
  assert.equal(typeLabel(FEEDBACK), "Feedback · Odds or scenarios");
  assert.equal(typeLabel({ type: "feedback", payload: { category: "other" } }), "Feedback");
  assert.equal(typeLabel({ type: "helmet_assignment" }), "Helmet worn");
  assert.equal(typeLabel({ type: "new_thing" }), "New thing");
  assert.deepEqual(decisionLabels("score"), { approve: "Apply correction", reject: "Reject" });
  assert.deepEqual(decisionLabels("feedback"), { approve: "Mark handled", reject: "Dismiss" });
  assert.equal(feedbackAbout(FEEDBACK.payload), "Region 2-7A · Oxford");
  assert.equal(feedbackAbout({ subject: "Feedback" }), "");
});

test("only pending can be approved; a logo awaiting its asset can still be rejected", () => {
  assert.ok(canApprove(SCORE) && canReject(SCORE));
  assert.ok(!canApprove({ status: "accepted_pending_asset" }) && canReject({ status: "accepted_pending_asset" }));
  assert.ok(!canReject({ status: "approved" }));
});

test("relative times", () => {
  const now = Date.parse("2026-10-14T12:00:00Z");
  assert.equal(relativeTime("2026-10-14T11:59:40Z", now), "just now");
  assert.equal(relativeTime("2026-10-14T11:48:00Z", now), "12 min ago");
  assert.equal(relativeTime("2026-10-14T09:00:00Z", now), "3 hr ago");
  assert.equal(relativeTime("2026-10-13T12:00:00Z", now), "1 day ago");
  assert.match(relativeTime("2026-09-01T12:00:00Z", now), /2026/);
});

test("page links stay on this site", () => {
  assert.match(pageLink("/standings/7a/2"), /^<a href="\/standings\/7a\/2"/);
  assert.equal(pageLink("//evil.example"), "//evil.example");
  assert.equal(pageLink("javascript:alert(1)"), "javascript:alert(1)");
  assert.equal(pageLink(undefined), "");
});

test("cards escape everything a visitor wrote", () => {
  const html = itemHtml(FEEDBACK, Date.parse("2026-10-14T12:00:00Z"));
  assert.ok(!html.includes("<b>two</b>"));
  assert.ok(html.includes("&lt;b&gt;two&lt;/b&gt;"));
  assert.ok(!html.includes('href="//evil.example"'));
  assert.ok(html.includes('href="mailto:a@b.co"'));
  assert.ok(html.includes("Mark handled"));
});

test("score cards show both rows and what changed; reviewed cards have no buttons", () => {
  const html = itemHtml(SCORE);
  assert.match(html, /On the site/);
  assert.match(html, /class="is-changed"><span>21<\/span>/);
  assert.match(html, /at Tupelo/);
  const done = itemHtml({ ...SCORE, status: "approved", reviewed_at: "2026-10-14T12:05:00Z", moderator_notes: "Checked MaxPreps" });
  assert.ok(!done.includes("data-decide"));
  assert.match(done, /Checked MaxPreps/);
});

test("type filter chips: all types first, then pending types by name, with counts", () => {
  const chips = typeFilters({ score: 2, logo: 1, colors: 0 }, "");
  assert.deepEqual(chips.map((c) => [c.value, c.label, c.count]), [
    ["", "All types", 3],
    ["feedback", "Feedback", 0],
    ["logo", "Logo", 1],
    ["score", "Score correction", 2],
  ]);
  assert.ok(typeFilters({}, "helmet").some((c) => c.value === "helmet"));
});

// ------------------------------------------------------------ sign-in

const CFG = { auth0_domain: "x.us.auth0.com", auth0_audience: "https://api.example", auth0_client_id: "spa123" };

class MemoryStorage {
  constructor() { this.map = new Map(); }
  getItem(k) { return this.map.get(k) ?? null; }
  setItem(k, v) { this.map.set(k, String(v)); }
  removeItem(k) { this.map.delete(k); }
}

test("PKCE: the RFC 7636 example challenge", async () => {
  assert.equal(await challengeFor("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"), "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
  assert.equal(base64url(new Uint8Array([251, 255])), "-_8");
});

test("Auth0 URLs carry the app, audience and challenge", () => {
  const url = new URL(authorizeUrl(CFG, { redirectUri: "https://site/moderate", state: "s1", challenge: "c1" }));
  assert.equal(url.origin + url.pathname, "https://x.us.auth0.com/authorize");
  assert.equal(url.searchParams.get("client_id"), "spa123");
  assert.equal(url.searchParams.get("audience"), "https://api.example");
  assert.equal(url.searchParams.get("code_challenge_method"), "S256");
  assert.equal(new URL(logoutUrl(CFG, "https://site/moderate")).searchParams.get("returnTo"), "https://site/moderate");
  assert.equal(tokenRequest(CFG, { code: "c", verifier: "v", redirectUri: "r" }).body.code_verifier, "v");
});

test("stored tokens expire a minute early", () => {
  const storage = new MemoryStorage();
  saveToken(storage, "tok", 3600, 0);
  assert.equal(storedToken(storage, 1000), "tok");
  assert.equal(storedToken(storage, 3600_000 - 30_000), null);
  storage.setItem("mshsf.mod.token", "{not json");
  assert.equal(storedToken(storage), null);
});

test("completing sign-in checks the state, then trades the code", async () => {
  const storage = new MemoryStorage();
  storage.setItem("mshsf.mod.pkce", JSON.stringify({ verifier: "v1", state: "s1" }));
  const calls = [];
  const fetcher = async (url, init) => {
    calls.push([url, JSON.parse(init.body)]);
    return { ok: true, json: async () => ({ access_token: "AT", expires_in: 86400 }) };
  };
  const token = await completeSignIn(CFG, "https://site/moderate", "https://site/moderate?code=C1&state=s1", storage, fetcher);
  assert.equal(token, "AT");
  assert.equal(calls[0][0], "https://x.us.auth0.com/oauth/token");
  assert.equal(calls[0][1].code_verifier, "v1");
  assert.equal(storage.getItem("mshsf.mod.pkce"), null);
  assert.equal(storedToken(storage), "AT");
});

test("a mismatched state or an Auth0 error is refused", async () => {
  const storage = new MemoryStorage();
  storage.setItem("mshsf.mod.pkce", JSON.stringify({ verifier: "v1", state: "s1" }));
  await assert.rejects(completeSignIn(CFG, "r", "https://site/moderate?code=C1&state=other", storage, () => assert.fail()), /stale/);
  await assert.rejects(completeSignIn(CFG, "r", "https://site/moderate?error=access_denied&error_description=Nope", storage), /Nope/);
});

test("payload values read as text", () => {
  assert.equal(payloadValue({ name: "Blue", hex: "#0033A0" }), "Blue #0033A0");
  assert.equal(payloadValue([{ name: "Gold", hex: "#FFC72C" }, { hex: "#000000" }]), "Gold #FFC72C, #000000");
  assert.equal(payloadValue({ a: 1 }), '{"a":1}');
  assert.equal(payloadValue(null), "");
  assert.equal(payloadValue(3), "3");
});

test("an unauthorized-client error says where to fix it", () => {
  const raw = 'Client "abc" is not authorized to access resource server "mshsfbanalytics".';
  assert.match(explainAuthError(raw), /Application Access/);
  assert.equal(explainAuthError("Nope"), "Nope");
  assert.equal(explainAuthError(undefined), undefined);
});

test("a date report shows the date on the site now and the reported one, and approving applies it", () => {
  const item = {
    id: 9, type: "date", status: "pending", school: "Oxford", submitted_at: "2026-10-14T12:00:00Z", reviewed_at: null,
    payload: { date: "2026-10-09", game_id: 77, new_date: "2026-10-10", note: "Moved for weather" },
    current_game: { opponent: "Tupelo", location: "home", points_for: null, points_against: null, result: null, date: "2026-10-09" },
  };
  const html = itemHtml(item);
  assert.match(html, />Date correction</);
  assert.match(html, /Oxford vs Tupelo · reported while shown on Fri, Oct 9/);
  assert.match(html, /On the site<\/th><td>Fri, Oct 9</);
  assert.match(html, /Reported<\/th><td class="is-changed"><span>Sat, Oct 10</);
  assert.match(html, /Moved for weather/);
  assert.equal(decisionLabels("date").approve, "Apply correction");
  assert.match(itemHtml({ ...item, current_game: null }), /no longer on the schedule/);
});
