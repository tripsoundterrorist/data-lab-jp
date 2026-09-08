import assert from "node:assert/strict";
import { assessAffiliateRateLimit } from "../runtime-candidates/affiliate-rate-limit-adapter.mjs";

const publicId = "itm_0123456789abcdef01234567";

let observedKey;
const allowed = await assessAffiliateRateLimit({
  async limit({ key }) {
    observedKey = key;
    return { success: true };
  },
}, publicId);
assert.equal(allowed.status, "ALLOWED");
assert.equal(allowed.allowed, true);
assert.equal(observedKey, `affiliate-route:${publicId}`);
assert.equal(JSON.stringify(allowed).includes(observedKey), false);

const blocked = await assessAffiliateRateLimit({
  async limit() { return { success: false }; },
}, publicId);
assert.equal(blocked.status, "BLOCKED");
assert.equal(blocked.allowed, false);

for (const value of [
  await assessAffiliateRateLimit(undefined, publicId),
  await assessAffiliateRateLimit({ limit: async () => ({}) }, publicId),
  await assessAffiliateRateLimit({ limit: async () => { throw new Error("secret detail"); } }, publicId),
  await assessAffiliateRateLimit({ limit: async () => ({ success: true }) }, "bad"),
]) {
  assert.equal(value.status, "FAIL_CLOSED");
  assert.equal(value.allowed, false);
  assert.equal(JSON.stringify(value).includes("secret detail"), false);
}
