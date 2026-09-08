import assert from "node:assert/strict";
import { runAffiliateRuntimeCandidate } from
  "../runtime-candidates/affiliate-runtime-composition.mjs";

const publicId = "itm_0123456789abcdef01234567";
const contentId = "lookup-content-001";
const facts = {
  officialAnswerCandidate: true,
  publicationGateEligible: true,
  runtimeChainConnected: true,
  rateLimitAllowed: true,
  prDisclosureAvailable: true,
};

async function run({ results = [], factChanges = {}, path = `/go/${publicId}`,
  method = "GET", throwQuery = false } = {}) {
  let queries = 0;
  let pipelineCalls = 0;
  let received = null;
  const database = { prepare() { queries += 1; return { bind() { return {
    async all() { if (throwQuery) throw Error("private query error");
      return { success: true, results }; },
  }; } }; } };
  const sentinel = { status: "PIPELINE_SENTINEL" };
  const result = await runAffiliateRuntimeCandidate(
    new Request(`https://candidate.invalid${path}`, { method }),
    { DMM_API_ID: "dummy-api", DMM_AFFILIATE_ID: "dummy-affiliate",
      AFFILIATE_ITEM_LOOKUP: database },
    { ...facts, ...factChanges },
    async (value) => { pipelineCalls += 1; received = value; return sentinel; },
  );
  return { result, queries, pipelineCalls, received, sentinel };
}

const blocked = await run();
assert.equal(blocked.result.status, "BLOCKED");
assert.deepEqual(blocked.result.reason_codes, ["AFFILIATE_ITEM_NOT_ELIGIBLE"]);
assert.equal(blocked.queries, 1);
assert.equal(blocked.pipelineCalls, 0);

const eligible = await run({ results: [{ content_id: contentId }] });
assert.equal(eligible.result, eligible.sentinel);
assert.equal(eligible.pipelineCalls, 1);
assert.equal(eligible.received, contentId);

for (const changes of [
  { factChanges: { officialAnswerCandidate: false } },
  { factChanges: { publicationGateEligible: false } },
  { factChanges: { runtimeChainConnected: false } },
  { factChanges: { prDisclosureAvailable: false } },
  { path: `/go/${publicId}?unexpected=1` },
  { method: "POST" },
]) {
  const actual = await run({ ...changes, results: [{ content_id: contentId }] });
  assert.equal(actual.pipelineCalls, 0);
  assert.equal(actual.queries, 0);
}

const failed = await run({ throwQuery: true });
assert.equal(failed.result.status, "FAIL_CLOSED");
assert.equal(failed.pipelineCalls, 0);
const serialized = JSON.stringify(failed.result);
assert.equal(serialized.includes(publicId), false);
assert.equal(serialized.includes(contentId), false);
assert.equal(serialized.includes("private query error"), false);
