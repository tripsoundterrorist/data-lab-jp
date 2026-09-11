const CONTENT_ID = /^[A-Za-z0-9._-]{1,128}$/u;
const MAX_RESPONSE_BYTES = 1024 * 1024;
const ALLOWED_HOSTS = Object.freeze(["dmm.com", "dmm.co.jp", "fanza.com", "fanza.co.jp"]);

function outcome(status, delivered, reason) {
  return Object.freeze({
    provider_version: "0.1",
    status,
    delivery_attempted: delivered,
    delivered,
    reason_codes: Object.freeze([reason]),
  });
}

function allowedAffiliateUrl(value) {
  try {
    if (typeof value !== "string" || value.length < 12 || value.length > 4096) return false;
    if (/[\u0000-\u0020\u007f]/u.test(value)) return false;
    const parsed = new URL(value);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.port) return false;
    const host = parsed.hostname.toLowerCase();
    return ALLOWED_HOSTS.some((allowed) => host === allowed || host.endsWith(`.${allowed}`));
  } catch (_) {
    return false;
  }
}

// The API-issued URL is delivered only to the next trusted in-process boundary.
// It is never included in this provider's return value or failure details.
export async function fetchAndDeliverDmmAffiliateUrl(
  env, contentId, deliverAffiliateUrl, fetcher = fetch,
) {
  try {
    if (!CONTENT_ID.test(contentId) || typeof deliverAffiliateUrl !== "function" || typeof fetcher !== "function") {
      return outcome("FAIL_CLOSED", false, "PROVIDER_INPUT_INVALID");
    }
    if (!env || typeof env.DMM_API_ID !== "string" || !env.DMM_API_ID ||
        typeof env.DMM_AFFILIATE_ID !== "string" || !env.DMM_AFFILIATE_ID) {
      return outcome("FAIL_CLOSED", false, "PROVIDER_SECRET_BINDING_UNAVAILABLE");
    }
    const query = new URLSearchParams({
      api_id: env.DMM_API_ID, affiliate_id: env.DMM_AFFILIATE_ID,
      site: "FANZA", service: "digital", floor: "videoa", cid: contentId,
      hits: "1", offset: "1", output: "json",
    });
    const response = await fetcher(`https://api.dmm.com/affiliate/v3/ItemList?${query}`, {
      method: "GET", headers: { Accept: "application/json" }, redirect: "error",
      signal: AbortSignal.timeout(15000),
    });
    if (!(response instanceof Response) || !response.ok) {
      return outcome("FAIL_CLOSED", false, "PROVIDER_UPSTREAM_UNAVAILABLE");
    }
    const declaredLength = Number(response.headers.get("Content-Length"));
    if (Number.isFinite(declaredLength) && declaredLength > MAX_RESPONSE_BYTES) {
      return outcome("FAIL_CLOSED", false, "PROVIDER_RESPONSE_TOO_LARGE");
    }
    const body = await response.text();
    if (new TextEncoder().encode(body).byteLength > MAX_RESPONSE_BYTES) {
      return outcome("FAIL_CLOSED", false, "PROVIDER_RESPONSE_TOO_LARGE");
    }
    const payload = JSON.parse(body);
    const items = payload?.result?.items;
    if (!Array.isArray(items) || items.length !== 1 || items[0]?.content_id !== contentId ||
        !allowedAffiliateUrl(items[0]?.affiliateURL)) {
      return outcome("FAIL_CLOSED", false, "PROVIDER_RESPONSE_INVALID");
    }
    try {
      await deliverAffiliateUrl(items[0].affiliateURL);
    } catch (_) {
      return outcome("FAIL_CLOSED", true, "PROVIDER_DELIVERY_FAILED");
    }
    return outcome("DELIVERED", true, "PROVIDER_URL_DELIVERED");
  } catch (_) {
    return outcome("FAIL_CLOSED", false, "PROVIDER_INTERNAL_ERROR");
  }
}

export const AFFILIATE_WORKERS_DMM_PROVIDER_VERSION = "0.1";
