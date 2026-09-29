import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import worker, {
  ACTIVATION_SCOPE,
  RELEASE_FACTS,
} from "../deployment-candidates/affiliate-worker/src/index.mjs";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

assert.deepEqual(RELEASE_FACTS, {
  officialAnswerCandidate: true,
  publicationGateEligible: true,
  runtimeChainConnected: true,
  rateLimitAllowed: true,
  prDisclosureAvailable: true,
});
assert.equal(ACTIVATION_SCOPE.candidateSha256, "854ecb10bdc751d08cdd554894d3143b05f7f3a01be979ca3ce6a6553009f740");
assert.equal(ACTIVATION_SCOPE.artifactSha256, "854ecb10bdc751d08cdd554894d3143b05f7f3a01be979ca3ce6a6553009f740");
assert.equal(ACTIVATION_SCOPE.sourceSha256, "564bbeaf628de624e816ff8f2b4a3824119e338d3052e8d2594a084f06ef2e85");
assert.equal(ACTIVATION_SCOPE.publicSurface, "/items/");
assert.equal(ACTIVATION_SCOPE.routePrefix, "/go/");
assert.equal(ACTIVATION_SCOPE.maximumCtaCount, 74);
assert.equal(ACTIVATION_SCOPE.itemCount, 100);
assert.equal(ACTIVATION_SCOPE.relayOperationGuaranteed, false);
assert.equal(ACTIVATION_SCOPE.affiliateOutcomeGuaranteed, false);

let queries = 0;
let upstream = 0;
const env = {
  DMM_API_ID: "fixture-api",
  DMM_AFFILIATE_ID: "fixture-affiliate",
  AFFILIATE_CLIENT_KEY_SECRET: "fixture-secret-with-at-least-32-characters",
  AFFILIATE_CLIENT_RATE_LIMITER: {
    async limit() { return { success: true }; },
  },
  AFFILIATE_ITEM_LOOKUP: {
    prepare() {
      queries += 1;
      return { bind() { return { async all() { return { success: true, results: [] }; } }; } };
    },
  },
};
const request = new Request("https://candidate.invalid/go/itm_0123456789abcdef01234567", {
  headers: { "CF-Connecting-IP": "203.0.113.10" },
});
const response = await worker.fetch(request, env, {
  fetcher: async () => { upstream += 1; throw new Error("must not fetch"); },
});
assert.equal(response.status, 404);
assert.equal(response.headers.get("Location"), null);
assert.equal(queries, 1);
assert.equal(upstream, 0);
