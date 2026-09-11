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

function fallback(status = 404) {
  return new Response(null, { status, headers: REDIRECT_HEADERS });
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
    if (clientKey.derived !== true) return fallback(404);

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
    return createAffiliateBlockedResponse(result);
  } catch (_) {
    return fallback(404);
  }
}

export const AFFILIATE_PAGES_ENTRYPOINT_CANDIDATE_VERSION = "0.1";
