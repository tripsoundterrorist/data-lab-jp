import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { handleAffiliatePagesCandidate } from
  "../runtime-candidates/affiliate-pages-entrypoint-candidate.mjs";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

const secret = "diagnostic-fixture-secret-at-least-32";
const facts = {
  officialAnswerCandidate: true,
  publicationGateEligible: true,
  runtimeChainConnected: true,
  rateLimitAllowed: true,
  prDisclosureAvailable: true,
};
const baseEnv = {
  DMM_API_ID: "fixture-api",
  DMM_AFFILIATE_ID: "fixture-affiliate",
  AFFILIATE_ITEM_LOOKUP: { prepare() {} },
  AFFILIATE_CLIENT_RATE_LIMITER: { async limit() { return { success: true }; } },
  AFFILIATE_DIAGNOSTIC_SECRET: secret,
};

function request(method = "HEAD", key = secret) {
  return new Request("https://candidate.invalid/go/itm_0123456789abcdef01234567", {
    method,
    headers: {
      "CF-Connecting-IP": "203.0.113.10",
      "X-Data-Lab-Diagnostic-Key": key,
    },
  });
}

const authorized = await handleAffiliatePagesCandidate(
  { request: request(), env: baseEnv }, facts,
);
assert.equal(authorized.status, 404);
assert.equal(authorized.headers.get("X-Data-Lab-Diagnostic"), "CLIENT_KEY_INPUT_INVALID");

for (const [method, key] of [["GET", secret], ["HEAD", "wrong-key-with-at-least-32-characters"]]) {
  const response = await handleAffiliatePagesCandidate(
    { request: request(method, key), env: baseEnv }, facts,
  );
  assert.equal(response.status, 404);
  assert.equal(response.headers.get("X-Data-Lab-Diagnostic"), null);
}
