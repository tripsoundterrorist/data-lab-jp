import assert from "node:assert/strict";
import { runEligibleAffiliateItemLookup, AFFILIATE_D1_ELIGIBLE_LOOKUP_SQL as SQL }
  from "../runtime-candidates/affiliate-d1-runtime-adapter.mjs";

const publicId = "itm_0123456789abcdef01234567";
const contentId = "lookup-content-001";
async function run(query, changes = {}) {
  let calls = 0;
  let received = null;
  const observed = {};
  const database = { prepare(sql) { observed.sql = sql; if (changes.throwAt === "prepare") throw Error("hidden"); return {
    bind(value) { observed.bound = value; if (changes.throwAt === "bind") throw Error("hidden"); return {
      async all() { if (changes.throwAt === "all") throw Error("hidden"); return query; },
    }; },
  }; } };
  const sentinel = { trusted: true };
  const pipeline = async (value) => { calls += 1; received = value;
    if (changes.throwAt === "pipeline") throw Error("hidden"); return sentinel; };
  const result = await runEligibleAffiliateItemLookup(
    changes.env ?? { AFFILIATE_ITEM_LOOKUP: database },
    changes.publicId ?? publicId,
    changes.pipeline === null ? null : pipeline,
  );
  return { result, calls, received, observed, sentinel };
}

const ok = await run({ success: true, results: [{ content_id: contentId }] });
assert.equal(ok.result, ok.sentinel);
assert.equal(ok.calls, 1);
assert.equal(ok.received, contentId);
assert.equal(ok.observed.sql, SQL);
assert.equal(ok.observed.bound, publicId);
assert.equal(SQL.startsWith("SELECT content_id FROM affiliate_runtime_eligible_lookup "), true);

for (const query of [{ success: true, results: [] },
  { success: true, results: [{ content_id: contentId }, { content_id: "other" }] }]) {
  const actual = await run(query);
  assert.equal(actual.result.status, "BLOCKED");
  assert.equal(actual.calls, 0);
}
for (const query of [null, { success: false, results: [] }, { success: true, results: null },
  { success: true, results: [{}] }, { success: true, results: [{ content_id: "bad/content" }] },
  { success: true, results: [{ content_id: contentId, extra: true }] }]) {
  const actual = await run(query);
  assert.equal(actual.result.status, "FAIL_CLOSED");
  assert.equal(actual.calls, 0);
}
for (const changes of [{ publicId: "../secret" }, { env: {} }, { pipeline: null }]) {
  const actual = await run({ success: true, results: [{ content_id: contentId }] }, changes);
  assert.equal(actual.result.status, "BLOCKED");
  assert.equal(actual.calls, 0);
}
for (const throwAt of ["prepare", "bind", "all", "pipeline"]) {
  const actual = await run({ success: true, results: [{ content_id: contentId }] }, { throwAt });
  assert.equal(actual.result.status, "FAIL_CLOSED");
  const safe = JSON.stringify(actual.result);
  assert.equal(safe.includes(publicId) || safe.includes(contentId) || safe.includes("hidden"), false);
}
