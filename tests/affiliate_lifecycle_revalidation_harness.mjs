import assert from "node:assert/strict";
import {
  AFFILIATE_LIFECYCLE_REVALIDATION_BATCH_SIZE,
  AFFILIATE_LIFECYCLE_REVALIDATION_SELECT_SQL,
  runAffiliateLifecycleRevalidation,
} from "../runtime-candidates/affiliate-lifecycle-revalidation.mjs";

const rows = [
  { public_id: "itm_000000000000000000000001", content_id: "valid001" },
  { public_id: "itm_000000000000000000000002", content_id: "missing002" },
];
const batches = [];
const database = {
  prepare(sql) {
    return {
      sql,
      bind(...args) { return { sql, args }; },
      async all() { return { success: true, results: rows }; },
    };
  },
  async batch(statements) {
    batches.push(statements);
    return statements.map(() => ({ success: true }));
  },
};
const env = {
  AFFILIATE_ITEM_LOOKUP: database,
  DMM_API_ID: "fixture-api",
  DMM_AFFILIATE_ID: "fixture-affiliate",
};
const fetcher = async (url) => {
  const cid = new URL(url).searchParams.get("cid");
  const items = cid === "valid001" ? [{
    content_id: cid,
    affiliateURL: "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fexample.invalid",
  }] : [];
  return new Response(JSON.stringify({ result: { items } }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
};

const checkedAt = "2026-09-29T14:00:00.000Z";
const outcome = await runAffiliateLifecycleRevalidation(env, fetcher, checkedAt);
assert.equal(AFFILIATE_LIFECYCLE_REVALIDATION_BATCH_SIZE, 5);
assert.match(AFFILIATE_LIFECYCLE_REVALIDATION_SELECT_SQL, /ORDER BY updated_at ASC/);
assert.match(AFFILIATE_LIFECYCLE_REVALIDATION_SELECT_SQL, /LIMIT 5/);
assert.deepEqual(outcome, {
  revalidation_version: "0.1",
  status: "COMPLETED",
  checked: 2,
  valid: 1,
  disabled: 1,
  reason_codes: ["BOUNDED_REVALIDATION_COMPLETED"],
});
assert.equal(batches.length, 2);
assert.equal(batches[0].length, 3);
assert.match(batches[0][0].sql, /INSERT INTO affiliate_redirect_target/);
assert.match(batches[0][1].sql, /affiliate_enabled = 1/);
assert.match(batches[0][2].sql, /'VALID', 1/);
assert.equal(batches[1].length, 2);
assert.match(batches[1][0].sql, /affiliate_enabled = 0/);
assert.deepEqual(batches[1][0].args.slice(0, 2), ["FAILED", checkedAt]);
assert.deepEqual(batches[1][1].args.slice(2), ["NOT_AVAILABLE", "PROVIDER_RESPONSE_INVALID"]);

const blocked = await runAffiliateLifecycleRevalidation(
  { AFFILIATE_ITEM_LOOKUP: database }, fetcher, checkedAt,
);
assert.equal(blocked.status, "FAIL_CLOSED");
assert.equal(blocked.checked, 0);
