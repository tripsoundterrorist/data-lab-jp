import { assessCloudflareCandidate } from "./cloudflare-affiliate-route.mjs";
import { assessAffiliatePerClientRateLimit } from
  "./affiliate-per-client-rate-limit-adapter.mjs";
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

export async function runPerClientAffiliateRuntimeCandidate(
  request, env, facts, opaqueClientKey, invokePipeline,
) {
  try {
    const route = assessCloudflareCandidate(
      request, env, { ...facts, rateLimitAllowed: true },
    );
    if (route.invoke_pipeline !== true) return route;

    const match = PUBLIC_ID_PATH.exec(new URL(request.url).pathname);
    if (!match) return blocked("FAIL_CLOSED", 404, "COMPOSITION_ROUTE_MISMATCH");

    const rateLimit = await assessAffiliatePerClientRateLimit(
      env?.AFFILIATE_CLIENT_RATE_LIMITER, opaqueClientKey, match[1],
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
    return blocked("FAIL_CLOSED", 404, "PER_CLIENT_COMPOSITION_INTERNAL_ERROR");
  }
}

export const AFFILIATE_PER_CLIENT_COMPOSITION_VERSION = "0.1";
