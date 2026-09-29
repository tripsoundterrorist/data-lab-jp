import { assessCloudflareCandidate } from "./cloudflare-affiliate-route.mjs";
import { deriveAffiliateOpaqueClientKey } from "./affiliate-client-key-derivation.mjs";
import { runPerClientAffiliateRuntimeCandidate } from "./affiliate-runtime-per-client-composition.mjs";
import { fetchAndDeliverDmmAffiliateUrl } from "./affiliate-workers-dmm-provider.mjs";
import { createAffiliateBlockedResponse } from "./affiliate-blocked-response-adapter.mjs";

const REDIRECT_HEADERS = Object.freeze({
  "Cache-Control": "no-store, max-age=0",
  Pragma: "no-cache",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Robots-Tag": "noindex, nofollow, noarchive",
});

const DIAGNOSTIC_REQUEST_HEADER = "X-Data-Lab-Diagnostic-Key";
const DIAGNOSTIC_RESPONSE_HEADER = "X-Data-Lab-Diagnostic";
const SAFE_DIAGNOSTIC_REASONS = new Set([
  "TRUSTED_CLIENT_ADDRESS_UNAVAILABLE",
  "CLIENT_KEY_INPUT_INVALID",
  "CLIENT_KEY_DERIVATION_INTERNAL_ERROR",
  "RATE_LIMIT_BINDING_UNAVAILABLE",
  "INVALID_RATE_LIMIT_RESPONSE",
  "RATE_LIMIT_INTERNAL_ERROR",
  "ELIGIBLE_LOOKUP_QUERY_FAILED",
  "ELIGIBLE_LOOKUP_INTERNAL_ERROR",
  "AFFILIATE_ITEM_NOT_ELIGIBLE",
  "PROVIDER_SECRET_BINDING_UNAVAILABLE",
  "PROVIDER_UPSTREAM_UNAVAILABLE",
  "PROVIDER_RESPONSE_TOO_LARGE",
  "PROVIDER_RESPONSE_INVALID",
  "PROVIDER_INTERNAL_ERROR",
]);

function fallback(status = 404) {
  return new Response(null, { status, headers: REDIRECT_HEADERS });
}

function privateDiagnosticResponse(response, request, env, reason) {
  const configured = env?.AFFILIATE_DIAGNOSTIC_SECRET;
  const supplied = request?.headers?.get(DIAGNOSTIC_REQUEST_HEADER);
  if (request?.method !== "HEAD" || typeof configured !== "string" || configured.length < 32 ||
      supplied !== configured || !SAFE_DIAGNOSTIC_REASONS.has(reason)) {
    return response;
  }
  const headers = new Headers(response.headers);
  headers.set(DIAGNOSTIC_RESPONSE_HEADER, reason);
  return new Response(null, { status: response.status, headers });
}

// This is deliberately not exported as onRequest and is outside /functions.
// A later reviewed deployment wrapper must supply immutable release facts.
export async function handleAffiliatePagesCandidate(
  context, releaseFacts, dependencies = {},
) {
  try {
    const request = context?.request;
    const env = context?.env;
    const preliminary = assessCloudflareCandidate(
      request, env, { ...releaseFacts, rateLimitAllowed: true },
    );
    if (preliminary.invoke_pipeline !== true) {
      return createAffiliateBlockedResponse(preliminary);
    }

    const clientKey = await deriveAffiliateOpaqueClientKey(
      request, env.AFFILIATE_CLIENT_KEY_SECRET,
    );
    if (clientKey.derived !== true) {
      return privateDiagnosticResponse(
        fallback(404), request, env, clientKey.reason_codes?.[0],
      );
    }

    let redirectResponse = null;
    const result = await runPerClientAffiliateRuntimeCandidate(
      request, env, releaseFacts, clientKey.opaque_client_key,
      async (contentId) => fetchAndDeliverDmmAffiliateUrl(
        env, contentId,
        async (affiliateUrl) => {
          redirectResponse = new Response(null, {
            status: 302,
            headers: { ...REDIRECT_HEADERS, Location: affiliateUrl },
          });
        },
        dependencies.fetcher,
      ),
    );
    if (redirectResponse instanceof Response && result?.status === "DELIVERED" && result?.delivered === true) {
      return redirectResponse;
    }
    return privateDiagnosticResponse(
      createAffiliateBlockedResponse(result), request, env, result?.reason_codes?.[0],
    );
  } catch (_) {
    return fallback(404);
  }
}

export const AFFILIATE_PAGES_ENTRYPOINT_CANDIDATE_VERSION = "0.1";
