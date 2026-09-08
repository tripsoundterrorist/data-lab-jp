const PUBLIC_ID = /^itm_[0-9a-f]{24}$/u;
const OPAQUE_CLIENT_KEY = /^clt_[0-9a-f]{64}$/u;

function outcome(status, allowed, reason) {
  return Object.freeze({
    adapter_version: "0.1",
    status,
    allowed,
    per_client_candidate: true,
    reason_codes: Object.freeze([reason]),
  });
}

// The opaque key must be produced by a separately reviewed trusted boundary.
// This adapter never derives identity from a request, IP address, or header.
export async function assessAffiliatePerClientRateLimit(
  rateLimiter, opaqueClientKey, publicId,
) {
  try {
    if (!OPAQUE_CLIENT_KEY.test(opaqueClientKey) || !PUBLIC_ID.test(publicId)) {
      return outcome("FAIL_CLOSED", false, "INVALID_PER_CLIENT_RATE_LIMIT_SCOPE");
    }
    if (!rateLimiter || typeof rateLimiter.limit !== "function") {
      return outcome("FAIL_CLOSED", false, "RATE_LIMIT_BINDING_UNAVAILABLE");
    }

    const response = await rateLimiter.limit({
      key: `affiliate-client:${opaqueClientKey}:${publicId}`,
    });
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

export const AFFILIATE_PER_CLIENT_RATE_LIMIT_ADAPTER_VERSION = "0.1";
