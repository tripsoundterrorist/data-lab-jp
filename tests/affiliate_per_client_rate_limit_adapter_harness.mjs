import assert from "node:assert/strict";
import { assessAffiliatePerClientRateLimit } from
  "../runtime-candidates/affiliate-per-client-rate-limit-adapter.mjs";

const clientKey = `clt_${"a".repeat(64)}`;
const publicId = "itm_0123456789abcdef01234567";
let observedKey;
const allowed = await assessAffiliatePerClientRateLimit({
  async limit({ key }) { observedKey = key; return { success: true }; },
}, clientKey, publicId);
assert.equal(allowed.status, "ALLOWED");
assert.equal(allowed.allowed, true);
assert.equal(observedKey, `affiliate-client:${clientKey}:${publicId}`);
assert.equal(JSON.stringify(allowed).includes(clientKey), false);
assert.equal(JSON.stringify(allowed).includes(publicId), false);

const blocked = await assessAffiliatePerClientRateLimit({
  async limit() { return { success: false }; },
}, clientKey, publicId);
assert.equal(blocked.status, "BLOCKED");
assert.equal(blocked.allowed, false);

for (const [binding, key, item] of [
  [undefined, clientKey, publicId],
  [{ limit: async () => ({}) }, clientKey, publicId],
  [{ limit: async () => { throw new Error("private detail"); } }, clientKey, publicId],
  [{ limit: async () => ({ success: true }) }, "203.0.113.1", publicId],
  [{ limit: async () => ({ success: true }) }, "", publicId],
  [{ limit: async () => ({ success: true }) }, clientKey, "bad"],
]) {
  const result = await assessAffiliatePerClientRateLimit(binding, key, item);
  assert.equal(result.status, "FAIL_CLOSED");
  assert.equal(result.allowed, false);
  assert.equal(JSON.stringify(result).includes("private detail"), false);
  assert.equal(JSON.stringify(result).includes("203.0.113.1"), false);
}
