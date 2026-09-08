import assert from "node:assert/strict";
import { createAffiliateBlockedResponse } from
  "../runtime-candidates/affiliate-blocked-response-adapter.mjs";

for (const status of [404, 405, 429]) {
  const actual = createAffiliateBlockedResponse({
    invoke_pipeline: false,
    response_status: status,
    reason_codes: ["PRIVATE_DETAIL_MUST_NOT_APPEAR"],
  });
  assert.equal(actual.status, status);
  assert.equal(await actual.text(), "");
  assert.equal(actual.headers.get("Cache-Control"), "no-store, max-age=0");
  assert.equal(actual.headers.get("X-Robots-Tag"), "noindex, nofollow, noarchive");
  assert.equal(actual.headers.has("Location"), false);
}

for (const unsafe of [
  null,
  {},
  { invoke_pipeline: true, response_status: 302 },
  { invoke_pipeline: false, response_status: 302 },
  { invoke_pipeline: false, response_status: 200 },
  { invoke_pipeline: false, response_status: "404" },
]) {
  const actual = createAffiliateBlockedResponse(unsafe);
  assert.equal(actual.status, 404);
  assert.equal(await actual.text(), "");
  assert.equal(actual.headers.has("Location"), false);
  assert.equal(JSON.stringify([...actual.headers]).includes("PRIVATE_DETAIL"), false);
}
