import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { deriveAffiliateOpaqueClientKey } from "../runtime-candidates/affiliate-client-key-derivation.mjs";

if (!globalThis.crypto) globalThis.crypto = webcrypto;
const secret = "fixture-secret-with-at-least-32-characters";
const request = (address) => new Request("https://candidate.invalid/go/itm_0123456789abcdef01234567", {
  headers: address === null ? {} : { "CF-Connecting-IP": address },
});

const first = await deriveAffiliateOpaqueClientKey(request("203.0.113.10"), secret);
const repeated = await deriveAffiliateOpaqueClientKey(request("203.0.113.10"), secret);
const other = await deriveAffiliateOpaqueClientKey(request("203.0.113.11"), secret);
assert.equal(first.status, "DERIVED");
assert.match(first.opaque_client_key, /^clt_[0-9a-f]{64}$/u);
assert.equal(first.opaque_client_key, repeated.opaque_client_key);
assert.notEqual(first.opaque_client_key, other.opaque_client_key);

for (const [address, candidateSecret] of [
  [null, secret], ["203.0.113.10, 198.51.100.2", secret], ["999.0.0.1", secret],
  ["not-an-address", secret], ["203.0.113.10", "short"],
]) {
  const result = await deriveAffiliateOpaqueClientKey(request(address), candidateSecret);
  assert.equal(result.status, "FAIL_CLOSED");
  const serialized = JSON.stringify(result);
  assert.equal(serialized.includes("203.0.113"), false);
  assert.equal(serialized.includes(candidateSecret), false);
}
