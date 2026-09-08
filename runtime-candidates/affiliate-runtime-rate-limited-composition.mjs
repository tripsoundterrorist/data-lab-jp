import { assessCloudflareCandidate } from "./cloudflare-affiliate-route.mjs";
import { assessAffiliateRateLimit } from "./affiliate-rate-limit-adapter.mjs";
import { runAffiliateRuntimeCandidate } from "./affiliate-runtime-composition.mjs";

const PUBLIC_ID_PATH = /^\/go\/(itm_[0-9a-f]{24})$/u;

function blocked(status, responseStatus, reason) {
  return Object.freeze({
    composition_version: "0.1",
    status,
    invoke_pipeline: false,
    response_status: responseStatus,
    reason_codes: Object.freeze([reason]),
  });
}

export async function runRateLimitedAffiliateRuntimeCandidate(
  request, env, facts, invokePipeline,
) {
  try {
    const route = assessCloudflareCandidate(
      request, env, { ...facts, rateLimitAllowed: true },
    );
    if (route.invoke_pipeline !== true) return route;

    const match = PUBLIC_ID_PATH.exec(new URL(request.url).pathname);
    if (!match) return blocked("FAIL_CLOSED", 404, "COMPOSITION_ROUTE_MISMATCH");

    const rateLimit = await assessAffiliateRateLimit(
      env?.AFFILIATE_ROUTE_RATE_LIMITER, match[1],
    );
    if (rateLimit.allowed !== true) {
      const exceeded = rateLimit.status === "BLOCKED";
      return blocked(
        exceeded ? "BLOCKED" : "FAIL_CLOSED",
        exceeded ? 429 : 404,
        rateLimit.reason_codes[0],
      );
    }

    return await runAffiliateRuntimeCandidate(
      request, env, { ...facts, rateLimitAllowed: true }, invokePipeline,
    );
  } catch (_) {
    return blocked("FAIL_CLOSED", 404, "RATE_LIMITED_COMPOSITION_INTERNAL_ERROR");
  }
}

export const AFFILIATE_RATE_LIMITED_COMPOSITION_VERSION = "0.1";
