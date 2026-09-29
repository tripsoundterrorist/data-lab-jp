const PUBLIC_ID = /^itm_[0-9a-f]{24}$/u;
const CONTENT_ID = /^[A-Za-z0-9._-]{1,128}$/u;
const SQL = "SELECT content_id, affiliate_url FROM affiliate_runtime_redirect_target WHERE public_id = ? LIMIT 2";

function allowedAffiliateUrl(value) {
  try {
    if (typeof value !== "string" || value.length < 12 || value.length > 4096 ||
        /[\u0000-\u0020\u007f]/u.test(value)) return false;
    const parsed = new URL(value);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.port) return false;
    const host = parsed.hostname.toLowerCase();
    return ["dmm.com", "dmm.co.jp", "fanza.com", "fanza.co.jp"]
      .some((allowed) => host === allowed || host.endsWith(`.${allowed}`));
  } catch (_) {
    return false;
  }
}

function blocked(status, reason) {
  return Object.freeze({ adapter_version: "0.1", status, invoke_pipeline: false,
    response_status: 404, reason_codes: Object.freeze([reason]) });
}

export async function runEligibleAffiliateItemLookup(env, publicId, invokePipeline) {
  try {
    const database = env?.AFFILIATE_ITEM_LOOKUP;
    if (!PUBLIC_ID.test(publicId) || typeof invokePipeline !== "function" ||
        !database || typeof database.prepare !== "function") {
      return blocked("BLOCKED", "ELIGIBLE_LOOKUP_UNAVAILABLE");
    }
    const statement = database.prepare(SQL);
    if (!statement || typeof statement.bind !== "function") {
      return blocked("FAIL_CLOSED", "ELIGIBLE_LOOKUP_INTERNAL_ERROR");
    }
    const bound = statement.bind(publicId);
    if (!bound || typeof bound.all !== "function") {
      return blocked("FAIL_CLOSED", "ELIGIBLE_LOOKUP_INTERNAL_ERROR");
    }
    const query = await bound.all();
    if (!query || query.success !== true || !Array.isArray(query.results)) {
      return blocked("FAIL_CLOSED", "ELIGIBLE_LOOKUP_QUERY_FAILED");
    }
    if (query.results.length !== 1) {
      return blocked("BLOCKED", "AFFILIATE_ITEM_NOT_ELIGIBLE");
    }
    const row = query.results[0];
    if (!row || Object.keys(row).length !== 2 || !CONTENT_ID.test(row.content_id) ||
        !allowedAffiliateUrl(row.affiliate_url)) {
      return blocked("FAIL_CLOSED", "ELIGIBLE_LOOKUP_RESULT_INVALID");
    }
    return await invokePipeline(Object.freeze({
      content_id: row.content_id,
      affiliate_url: row.affiliate_url,
    }));
  } catch (_) {
    return blocked("FAIL_CLOSED", "ELIGIBLE_LOOKUP_INTERNAL_ERROR");
  }
}

export const AFFILIATE_D1_ADAPTER_VERSION = "0.1";
export const AFFILIATE_D1_ELIGIBLE_LOOKUP_SQL = SQL;
