import assert from "node:assert/strict";
import { runRateLimitedAffiliateRuntimeCandidate } from
  "../runtime-candidates/affiliate-runtime-rate-limited-composition.mjs";

const publicId = "itm_0123456789abcdef01234567";
const facts = {
  officialAnswerCandidate: true,
  publicationGateEligible: true,
  runtimeChainConnected: true,
  prDisclosureAvailable: true,
};

async function run({ path = `/go/${publicId}`, rateResponse = { success: true },
  rows = [], rateThrows = false } = {}) {
  let rateCalls = 0;
  let queries = 0;
  let pipelineCalls = 0;
  const env = {
    DMM_API_ID: "fixture-api",
    DMM_AFFILIATE_ID: "fixture-affiliate",
    AFFILIATE_ROUTE_RATE_LIMITER: { async limit() {
      rateCalls += 1;
      if (rateThrows) throw new Error("private rate error");
      return rateResponse;
    } },
    AFFILIATE_ITEM_LOOKUP: { prepare() { queries += 1; return { bind() { return {
      async all() { return { success: true, results: rows }; },
    }; } }; } },
  };
  const result = await runRateLimitedAffiliateRuntimeCandidate(
    new Request(`https://candidate.invalid${path}`), env, facts,
    async () => { pipelineCalls += 1; return { status: "PIPELINE_SENTINEL" }; },
  );
  return { result, rateCalls, queries, pipelineCalls };
}

const invalid = await run({ path: `/go/${publicId}?unexpected=1` });
assert.equal(invalid.rateCalls, 0);
assert.equal(invalid.queries, 0);

const exceeded = await run({ rateResponse: { success: false } });
assert.equal(exceeded.result.response_status, 429);
assert.equal(exceeded.rateCalls, 1);
assert.equal(exceeded.queries, 0);

for (const failed of [
  await run({ rateResponse: {} }),
  await run({ rateThrows: true }),
]) {
  assert.equal(failed.result.status, "FAIL_CLOSED");
  assert.equal(failed.result.response_status, 404);
  assert.equal(failed.queries, 0);
  assert.equal(JSON.stringify(failed.result).includes("private rate error"), false);
}

const ineligible = await run();
assert.equal(ineligible.rateCalls, 1);
assert.equal(ineligible.queries, 1);
assert.equal(ineligible.pipelineCalls, 0);

const eligible = await run({ rows: [{ content_id: "fixture-content" }] });
assert.equal(eligible.result.status, "PIPELINE_SENTINEL");
assert.equal(eligible.rateCalls, 1);
assert.equal(eligible.queries, 1);
assert.equal(eligible.pipelineCalls, 1);
