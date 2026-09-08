import assert from "node:assert/strict";
import { runPerClientAffiliateRuntimeCandidate } from
  "../runtime-candidates/affiliate-runtime-per-client-composition.mjs";

const publicId = "itm_0123456789abcdef01234567";
const clientKey = `clt_${"a".repeat(64)}`;
const facts = {
  officialAnswerCandidate: true,
  publicationGateEligible: true,
  runtimeChainConnected: true,
  prDisclosureAvailable: true,
};

async function run({ key = clientKey, path = `/go/${publicId}`,
  rateResponse = { success: true }, rows = [] } = {}) {
  let rateCalls = 0;
  let queries = 0;
  let pipelineCalls = 0;
  const env = {
    DMM_API_ID: "fixture-api",
    DMM_AFFILIATE_ID: "fixture-affiliate",
    AFFILIATE_CLIENT_RATE_LIMITER: { async limit() {
      rateCalls += 1;
      return rateResponse;
    } },
    AFFILIATE_ITEM_LOOKUP: { prepare() { queries += 1; return { bind() { return {
      async all() { return { success: true, results: rows }; },
    }; } }; } },
  };
  const result = await runPerClientAffiliateRuntimeCandidate(
    new Request(`https://candidate.invalid${path}`), env, facts, key,
    async () => { pipelineCalls += 1; return { status: "PIPELINE_SENTINEL" }; },
  );
  return { result, rateCalls, queries, pipelineCalls };
}

for (const rejected of [
  await run({ key: "" }),
  await run({ key: "203.0.113.1" }),
  await run({ path: `/go/${publicId}?unexpected=1` }),
]) {
  assert.equal(rejected.result.response_status, 404);
  assert.equal(rejected.queries, 0);
  assert.equal(rejected.pipelineCalls, 0);
}

const invalidKey = await run({ key: "" });
assert.equal(invalidKey.rateCalls, 0);
const invalidRoute = await run({ path: `/go/${publicId}?unexpected=1` });
assert.equal(invalidRoute.rateCalls, 0);

const exceeded = await run({ rateResponse: { success: false } });
assert.equal(exceeded.result.response_status, 429);
assert.equal(exceeded.rateCalls, 1);
assert.equal(exceeded.queries, 0);

const ineligible = await run();
assert.equal(ineligible.rateCalls, 1);
assert.equal(ineligible.queries, 1);
assert.equal(ineligible.pipelineCalls, 0);

const eligible = await run({ rows: [{ content_id: "fixture-content" }] });
assert.equal(eligible.result.status, "PIPELINE_SENTINEL");
assert.equal(eligible.rateCalls, 1);
assert.equal(eligible.queries, 1);
assert.equal(eligible.pipelineCalls, 1);
