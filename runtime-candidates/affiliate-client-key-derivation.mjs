const CLIENT_KEY = /^clt_[0-9a-f]{64}$/u;
const IPV4 = /^(?:\d{1,3}\.){3}\d{1,3}$/u;
const IPV6 = /^[0-9a-f:]+$/iu;

function failed(reason) {
  return Object.freeze({
    adapter_version: "0.1",
    status: "FAIL_CLOSED",
    derived: false,
    reason_codes: Object.freeze([reason]),
  });
}

function validAddress(value) {
  if (typeof value !== "string" || value.length < 2 || value.length > 64) return false;
  if (value.trim() !== value || value.includes(",") || /[\r\n\s]/u.test(value)) return false;
  if (IPV4.test(value)) {
    return value.split(".").every((part) => Number(part) <= 255);
  }
  return value.includes(":") && IPV6.test(value);
}

function toHex(bytes) {
  return [...new Uint8Array(bytes)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

// CF-Connecting-IP is consumed only inside this boundary. Neither it nor the
// secret is returned, logged, persisted, or included in failure details.
export async function deriveAffiliateOpaqueClientKey(request, secret) {
  try {
    if (!(request instanceof Request) || typeof secret !== "string" || secret.length < 32) {
      return failed("CLIENT_KEY_INPUT_INVALID");
    }
    const address = request.headers.get("CF-Connecting-IP");
    if (!validAddress(address)) return failed("TRUSTED_CLIENT_ADDRESS_UNAVAILABLE");

    const encoder = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
    );
    const digest = await crypto.subtle.sign(
      "HMAC", key, encoder.encode(`data-lab-affiliate-client-v0.1\0${address}`),
    );
    const opaqueClientKey = `clt_${toHex(digest)}`;
    if (!CLIENT_KEY.test(opaqueClientKey)) return failed("CLIENT_KEY_DERIVATION_INVALID");
    return Object.freeze({
      adapter_version: "0.1",
      status: "DERIVED",
      derived: true,
      opaque_client_key: opaqueClientKey,
      reason_codes: Object.freeze(["OPAQUE_CLIENT_KEY_DERIVED"]),
    });
  } catch (_) {
    return failed("CLIENT_KEY_DERIVATION_INTERNAL_ERROR");
  }
}

export const AFFILIATE_CLIENT_KEY_DERIVATION_VERSION = "0.1";
