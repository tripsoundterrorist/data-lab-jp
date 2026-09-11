import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { handleAffiliatePagesCandidate } from "../runtime-candidates/affiliate-pages-entrypoint-candidate.mjs";

if (!globalThis.crypto) globalThis.crypto = webcrypto;
const publicId = "itm_0123456789abcdef01234567";
const contentId = "fixture-content-001";
const affiliateUrl = "https://al.dmm.co.jp/?fixture=1";
const facts = { officialAnswerCandidate: true, publicationGateEligible: true, runtimeChainConnected: true, rateLimitAllowed: true, prDisclosureAvailable: true };

function context({ eligible = true, limited = false, method = "GET", address = "203.0.113.10" } = {}) {
  let queries = 0;
  let limits = 0;
  const database = { prepare() { queries += 1; return { bind() { return { async all() { return { success: true, results: eligible ? [{ content_id: contentId }] : [] }; } }; } }; } };
  const rate = { async limit() { limits += 1; return { success: !limited }; } };
  return {
    value: {
      request: new Request(`https://candidate.invalid/go/${publicId}`, { method, headers: { "CF-Connecting-IP": address } }),
      env: { DMM_API_ID: "fixture-api", DMM_AFFILIATE_ID: "fixture-affiliate", AFFILIATE_CLIENT_KEY_SECRET: "fixture-secret-with-at-least-32-characters", AFFILIATE_ITEM_LOOKUP: database, AFFILIATE_CLIENT_RATE_LIMITER: rate },
    },
    counts: () => ({ queries, limits }),
  };
}

let upstreamCalls = 0;
const allowed = context();
const response = await handleAffiliatePagesCandidate(allowed.value, facts, { fetcher: async () => {
  upstreamCalls += 1;
  return new Response(JSON.stringify({ result: { items: [{ content_id: contentId, affiliateURL: affiliateUrl }] } }), { status: 200 });
} });
assert.equal(response.status, 302);
assert.equal(response.headers.get("Location"), affiliateUrl);
assert.equal(response.headers.get("Cache-Control"), "no-store, max-age=0");
assert.deepEqual(allowed.counts(), { queries: 1, limits: 1 });
assert.equal(upstreamCalls, 1);

for (const scenario of [
  { options: { eligible: false }, status: 404 },
  { options: { limited: true }, status: 429 },
  { options: { method: "POST" }, status: 405 },
  { options: { address: "invalid" }, status: 404 },
]) {
  const candidate = context(scenario.options);
  let requests = 0;
  const blocked = await handleAffiliatePagesCandidate(candidate.value, facts, { fetcher: async () => { requests += 1; throw Error("must not fetch"); } });
  assert.equal(blocked.status, scenario.status);
  assert.equal(blocked.headers.get("Location"), null);
  assert.equal(requests, 0);
}

const closed = context();
const closedResponse = await handleAffiliatePagesCandidate(closed.value, { ...facts, publicationGateEligible: false }, { fetcher: async () => { throw Error("must not fetch"); } });
assert.equal(closedResponse.status, 404);
assert.deepEqual(closed.counts(), { queries: 0, limits: 0 });
