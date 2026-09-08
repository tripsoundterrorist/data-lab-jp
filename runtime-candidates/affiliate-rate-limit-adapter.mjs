const PUBLIC_ID = /^itm_[0-9a-f]{24}$/u;

function outcome(status, allowed, reason) {
  return Object.freeze({
    adapter_version: "0.1",
    status,
    allowed,
    reason_codes: Object.freeze([reason]),
  });
}

// This is a non-deployed, coarse upstream-protection candidate. Cloudflare's
// counters are location-local and eventually consistent, so this must not be
// treated as accounting or as the only abuse-control boundary.
export async function assessAffiliateRateLimit(rateLimiter, publicId) {
  try {
    if (!PUBLIC_ID.test(publicId)) {
      return outcome("FAIL_CLOSED", false, "INVALID_RATE_LIMIT_SCOPE");
    }
    if (!rateLimiter || typeof rateLimiter.limit !== "function") {
      return outcome("FAIL_CLOSED", false, "RATE_LIMIT_BINDING_UNAVAILABLE");
    }

    const response = await rateLimiter.limit({ key: `affiliate-route:${publicId}` });
    if (!response || typeof response.success !== "boolean") {
      return outcome("FAIL_CLOSED", false, "INVALID_RATE_LIMIT_RESPONSE");
    }
    if (!response.success) {
      return outcome("BLOCKED", false, "RATE_LIMIT_EXCEEDED");
    }
    return outcome("ALLOWED", true, "RATE_LIMIT_ALLOWED");
  } catch (_) {
    return outcome("FAIL_CLOSED", false, "RATE_LIMIT_INTERNAL_ERROR");
  }
}

export const AFFILIATE_RATE_LIMIT_ADAPTER_VERSION = "0.1";
