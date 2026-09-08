const BLOCKED_STATUS = new Set([404, 405, 429]);
const SAFE_HEADERS = Object.freeze({
  "Cache-Control": "no-store, max-age=0",
  Pragma: "no-cache",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Robots-Tag": "noindex, nofollow, noarchive",
});

function response(status) {
  return new Response(null, { status, headers: SAFE_HEADERS });
}

// Only blocked outcomes may cross this non-deployed HTTP boundary. A route
// candidate, pipeline result, redirect status, or malformed input becomes 404.
export function createAffiliateBlockedResponse(candidate) {
  try {
    if (!candidate || candidate.invoke_pipeline !== false) return response(404);
    if (!BLOCKED_STATUS.has(candidate.response_status)) return response(404);
    return response(candidate.response_status);
  } catch (_) {
    return response(404);
  }
}

export const AFFILIATE_BLOCKED_RESPONSE_ADAPTER_VERSION = "0.1";
