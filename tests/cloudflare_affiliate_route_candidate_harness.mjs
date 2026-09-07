import assert from "node:assert/strict";
import { assessCloudflareCandidate } from "../runtime-candidates/cloudflare-affiliate-route.mjs";

const id = "itm_0123456789abcdef01234567";
const env = {
  DMM_API_ID: "dummy-api",
  DMM_AFFILIATE_ID: "dummy-affiliate",
  AFFILIATE_ITEM_LOOKUP: { prepare() {} },
};
const facts = {
  officialAnswerCandidate: true,
  publicationGateEligible: true,
  runtimeChainConnected: true,
  rateLimitAllowed: true,
  prDisclosureAvailable: true,
};
const run = (changes = {}) => assessCloudflareCandidate(
  changes.request || new Request(`https://candidate.invalid/go/${id}`),
  changes.env || env,
  { ...facts, ...(changes.facts || {}) },
);

const eligible = run();
assert.equal(eligible.status, "ROUTE_CANDIDATE");
assert.equal(eligible.response_status, 302);
assert.equal(eligible.invoke_pipeline, true);
assert.equal(eligible.redirect_location_present, false);
assert.equal(eligible.response_headers["Cache-Control"], "no-store, max-age=0");

for (const method of ["POST", "PUT", "DELETE", "OPTIONS"]) {
  const actual = run({ request: new Request(`https://candidate.invalid/go/${id}`, { method }) });
  assert.equal(actual.response_status, 405);
  assert.equal(actual.invoke_pipeline, false);
}
for (const suffix of ["?x=1", "#x", "/extra"]) {
  const actual = run({ request: new Request(`https://candidate.invalid/go/${id}${suffix}`) });
  assert.equal(actual.response_status, 404);
  assert.equal(actual.invoke_pipeline, false);
}
for (const field of ["officialAnswerCandidate", "publicationGateEligible", "runtimeChainConnected", "prDisclosureAvailable"]) {
  const actual = run({ facts: { [field]: false } });
  assert.equal(actual.response_status, 404);
  assert.equal(actual.invoke_pipeline, false);
}
assert.equal(run({ facts: { rateLimitAllowed: false } }).response_status, 429);
for (const missing of ["DMM_API_ID", "DMM_AFFILIATE_ID", "AFFILIATE_ITEM_LOOKUP"]) {
  const candidateEnv = { ...env };
  delete candidateEnv[missing];
  const actual = run({ env: candidateEnv });
  assert.equal(actual.invoke_pipeline, false);
  assert.deepEqual(actual.reason_codes, ["REQUIRED_BINDINGS_UNAVAILABLE"]);
}
const serialized = JSON.stringify(eligible);
assert.equal(serialized.includes(id), false);
assert.equal(serialized.includes("dummy-api"), false);
assert.equal(serialized.includes("dummy-affiliate"), false);
assert.equal(serialized.includes("https://"), false);
