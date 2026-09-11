import assert from "node:assert/strict";
import { fetchAndDeliverDmmAffiliateUrl } from "../runtime-candidates/affiliate-workers-dmm-provider.mjs";

const contentId = "fixture-content-001";
const affiliateUrl = "https://al.dmm.co.jp/?fixture=1";
const env = { DMM_API_ID: "fixture-api", DMM_AFFILIATE_ID: "fixture-affiliate" };
const response = (item, init = {}) => new Response(JSON.stringify({ result: { items: [item] } }), {
  status: 200, headers: { "Content-Type": "application/json" }, ...init,
});

let received = null;
let requested = null;
const success = await fetchAndDeliverDmmAffiliateUrl(env, contentId, async (url) => { received = url; }, async (url, options) => {
  requested = { url, options };
  return response({ content_id: contentId, affiliateURL: affiliateUrl });
});
assert.equal(success.status, "DELIVERED");
assert.equal(received, affiliateUrl);
assert.equal(requested.options.method, "GET");
assert.equal(requested.options.redirect, "error");
assert.equal(JSON.stringify(success).includes(affiliateUrl), false);
assert.equal(JSON.stringify(success).includes(contentId), false);

for (const item of [
  { content_id: "other", affiliateURL: affiliateUrl },
  { content_id: contentId },
  { content_id: contentId, affiliateURL: "http://al.dmm.co.jp/unsafe" },
  { content_id: contentId, affiliateURL: "https://dmm.com.example.invalid/unsafe" },
]) {
  let calls = 0;
  const result = await fetchAndDeliverDmmAffiliateUrl(env, contentId, async () => { calls += 1; }, async () => response(item));
  assert.equal(result.status, "FAIL_CLOSED");
  assert.equal(calls, 0);
}

for (const candidateEnv of [{}, null]) {
  let requests = 0;
  const result = await fetchAndDeliverDmmAffiliateUrl(candidateEnv, contentId, async () => {}, async () => { requests += 1; });
  assert.equal(result.status, "FAIL_CLOSED");
  assert.equal(requests, 0);
}

const upstream = await fetchAndDeliverDmmAffiliateUrl(env, contentId, async () => {}, async () => new Response("no", { status: 503 }));
assert.equal(upstream.status, "FAIL_CLOSED");
assert.equal(JSON.stringify(upstream).includes("503"), false);

const deliveryFailure = await fetchAndDeliverDmmAffiliateUrl(env, contentId, async () => { throw Error("private URL"); }, async () => response({ content_id: contentId, affiliateURL: affiliateUrl }));
assert.equal(deliveryFailure.status, "FAIL_CLOSED");
assert.equal(deliveryFailure.delivery_attempted, true);
assert.equal(JSON.stringify(deliveryFailure).includes("private"), false);
