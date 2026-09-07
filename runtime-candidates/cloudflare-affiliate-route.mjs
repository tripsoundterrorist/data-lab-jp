const PUBLIC_ID_PATH = /^\/go\/(itm_[0-9a-f]{24})$/u;
const METHODS = new Set(["GET", "HEAD"]);
const SAFE_HEADERS = Object.freeze({
  "Cache-Control": "no-store, max-age=0",
  Pragma: "no-cache",
  "Referrer-Policy": "no-referrer",
  "X-Robots-Tag": "noindex, nofollow, noarchive",
});

function result(status, responseStatus, reasons, invokePipeline = false) {
  return Object.freeze({
    candidate_version: "0.1",
    status,
    response_status: responseStatus,
    invoke_pipeline: invokePipeline,
    response_body_allowed: false,
    redirect_location_present: false,
    response_headers: SAFE_HEADERS,
    reason_codes: Object.freeze([...reasons]),
  });
}

export function assessCloudflareCandidate(request, env, facts) {
  try {
    if (!(request instanceof Request) || !env || !facts) {
      return result("FAIL_CLOSED", 404, ["INVALID_RUNTIME_SHAPE"]);
    }
    const booleans = [
      facts.officialAnswerCandidate,
      facts.publicationGateEligible,
      facts.runtimeChainConnected,
      facts.rateLimitAllowed,
      facts.prDisclosureAvailable,
    ];
    if (!booleans.every((value) => typeof value === "boolean")) {
      return result("FAIL_CLOSED", 404, ["INVALID_GUARD_SHAPE"]);
    }
    if (!METHODS.has(request.method)) {
      return result("BLOCKED", 405, ["METHOD_NOT_ALLOWED"]);
    }
    const url = new URL(request.url);
    const match = PUBLIC_ID_PATH.exec(url.pathname);
    if (!match || url.search || url.hash) {
      return result("BLOCKED", 404, ["ROUTE_NOT_FOUND"]);
    }
    if (!facts.rateLimitAllowed) {
      return result("BLOCKED", 429, ["RATE_LIMIT_BLOCKED"]);
    }
    const bindingsReady =
      typeof env.DMM_API_ID === "string" && env.DMM_API_ID.length > 0 &&
      typeof env.DMM_AFFILIATE_ID === "string" && env.DMM_AFFILIATE_ID.length > 0 &&
      env.AFFILIATE_ITEM_LOOKUP &&
      typeof env.AFFILIATE_ITEM_LOOKUP.prepare === "function";
    if (!bindingsReady) {
      return result("BLOCKED", 404, ["REQUIRED_BINDINGS_UNAVAILABLE"]);
    }
    const blockers = [];
    if (!facts.officialAnswerCandidate) blockers.push("OFFICIAL_ANSWER_GATE_CLOSED");
    if (!facts.publicationGateEligible) blockers.push("PUBLICATION_GATE_CLOSED");
    if (!facts.runtimeChainConnected) blockers.push("RUNTIME_CHAIN_NOT_CONNECTED");
    if (!facts.prDisclosureAvailable) blockers.push("PR_DISCLOSURE_NOT_READY");
    if (blockers.length) return result("BLOCKED", 404, blockers);
    return result("ROUTE_CANDIDATE", 302, ["CLOUDFLARE_REQUEST_VALIDATED"], true);
  } catch (_) {
    return result("FAIL_CLOSED", 404, ["CANDIDATE_INTERNAL_ERROR"]);
  }
}

export const CANDIDATE_VERSION = "0.1";
