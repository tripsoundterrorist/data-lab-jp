const EVENTS = new Set([
  "ROUTE_ASSESSED",
  "RATE_LIMIT_ASSESSED",
  "LOOKUP_ASSESSED",
  "PIPELINE_ASSESSED",
]);
const DECISIONS = new Set([
  "ROUTE_ASSESSED|ALLOWED|ROUTE_ALLOWED",
  "ROUTE_ASSESSED|BLOCKED|ROUTE_BLOCKED",
  "ROUTE_ASSESSED|FAIL_CLOSED|INTERNAL_ERROR_REDACTED",
  "RATE_LIMIT_ASSESSED|ALLOWED|RATE_LIMIT_ALLOWED",
  "RATE_LIMIT_ASSESSED|BLOCKED|RATE_LIMIT_EXCEEDED",
  "RATE_LIMIT_ASSESSED|FAIL_CLOSED|INTERNAL_ERROR_REDACTED",
  "LOOKUP_ASSESSED|ALLOWED|LOOKUP_ELIGIBLE",
  "LOOKUP_ASSESSED|BLOCKED|LOOKUP_BLOCKED",
  "LOOKUP_ASSESSED|FAIL_CLOSED|INTERNAL_ERROR_REDACTED",
  "PIPELINE_ASSESSED|ALLOWED|PIPELINE_ALLOWED",
  "PIPELINE_ASSESSED|BLOCKED|PIPELINE_BLOCKED",
  "PIPELINE_ASSESSED|FAIL_CLOSED|INTERNAL_ERROR_REDACTED",
]);

function rejected() {
  return Object.freeze({
    adapter_version: "0.1",
    status: "FAIL_CLOSED",
    event_allowed: false,
    reason_codes: Object.freeze(["UNSAFE_AUDIT_EVENT_REJECTED"]),
  });
}

// Accept only bounded classifications. Identifiers, URLs, request data,
// credentials, provider payloads, and exception text are not part of the API.
export function createAffiliateSafeAuditEvent(candidate) {
  try {
    if (!candidate || Object.getPrototypeOf(candidate) !== Object.prototype) {
      return rejected();
    }
    if (!EVENTS.has(candidate.event)) {
      return rejected();
    }
    if (!Array.isArray(candidate.reasonCodes) || candidate.reasonCodes.length !== 1) {
      return rejected();
    }
    const decision = `${candidate.event}|${candidate.status}|${candidate.reasonCodes[0]}`;
    if (!DECISIONS.has(decision)) {
      return rejected();
    }
    if (Object.keys(candidate).sort().join(",") !== "event,reasonCodes,status") {
      return rejected();
    }

    return Object.freeze({
      adapter_version: "0.1",
      status: "AUDIT_EVENT_CANDIDATE",
      event_allowed: true,
      event: candidate.event,
      outcome: candidate.status,
      reason_codes: Object.freeze([...candidate.reasonCodes]),
    });
  } catch (_) {
    return rejected();
  }
}

export const AFFILIATE_SAFE_AUDIT_EVENT_VERSION = "0.1";
