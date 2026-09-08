import assert from "node:assert/strict";
import { createAffiliateSafeAuditEvent } from "../runtime-candidates/affiliate-safe-audit-event.mjs";

const safe = createAffiliateSafeAuditEvent({
  event: "RATE_LIMIT_ASSESSED",
  status: "BLOCKED",
  reasonCodes: ["RATE_LIMIT_EXCEEDED"],
});
assert.equal(safe.status, "AUDIT_EVENT_CANDIDATE");
assert.equal(safe.event_allowed, true);

for (const unsafe of [
  null,
  { event: "RATE_LIMIT_ASSESSED", status: "BLOCKED", reasonCodes: [] },
  { event: "RATE_LIMIT_ASSESSED", status: "BLOCKED", reasonCodes: ["https://secret.invalid"] },
  { event: "RATE_LIMIT_ASSESSED", status: "ALLOWED", reasonCodes: ["RATE_LIMIT_EXCEEDED"] },
  { event: "RATE_LIMIT_ASSESSED", status: "BLOCKED", reasonCodes: ["RATE_LIMIT_EXCEEDED"], publicId: "itm_secret" },
  { event: "ROUTE_ASSESSED", status: "ERROR: credential", reasonCodes: ["ROUTE_BLOCKED"] },
]) {
  const result = createAffiliateSafeAuditEvent(unsafe);
  assert.equal(result.status, "FAIL_CLOSED");
  assert.equal(result.event_allowed, false);
  const serialized = JSON.stringify(result);
  assert.equal(serialized.includes("secret"), false);
  assert.equal(serialized.includes("credential"), false);
  assert.equal(serialized.includes("https://"), false);
}
