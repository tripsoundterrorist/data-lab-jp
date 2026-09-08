import { assessCloudflareCandidate } from "./cloudflare-affiliate-route.mjs";
import { runEligibleAffiliateItemLookup } from "./affiliate-d1-runtime-adapter.mjs";

const PUBLIC_ID_PATH = /^\/go\/(itm_[0-9a-f]{24})$/u;

function failed(reason) {
  return Object.freeze({
    composition_version: "0.1",
    status: "FAIL_CLOSED",
    invoke_pipeline: false,
    response_status: 404,
    reason_codes: Object.freeze([reason]),
  });
}

export async function runAffiliateRuntimeCandidate(request, env, facts, invokePipeline) {
  try {
    const route = assessCloudflareCandidate(request, env, facts);
    if (route.invoke_pipeline !== true) return route;

    const match = PUBLIC_ID_PATH.exec(new URL(request.url).pathname);
    if (!match) return failed("COMPOSITION_ROUTE_MISMATCH");

    return await runEligibleAffiliateItemLookup(env, match[1], invokePipeline);
  } catch (_) {
    return failed("COMPOSITION_INTERNAL_ERROR");
  }
}

export const AFFILIATE_RUNTIME_COMPOSITION_VERSION = "0.1";
