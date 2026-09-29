import { fetchAndDeliverDmmAffiliateUrl } from "./affiliate-workers-dmm-provider.mjs";

const PUBLIC_ID = /^itm_[0-9a-f]{24}$/u;
const CONTENT_ID = /^[A-Za-z0-9._-]{1,128}$/u;
const BATCH_SIZE = 5;
const SELECT_SQL = `SELECT public_id, content_id
FROM affiliate_item_lookup
WHERE rights_status = 'CONDITIONALLY_APPROVED'
  AND lifecycle_status = 'RESOLVED'
ORDER BY updated_at ASC, public_id ASC
LIMIT 5`;

function result(status, checked, valid, disabled, reason) {
  return Object.freeze({
    revalidation_version: "0.1",
    status,
    checked,
    valid,
    disabled,
    reason_codes: Object.freeze([reason]),
  });
}

function databaseReady(env) {
  const database = env?.AFFILIATE_ITEM_LOOKUP;
  return database && typeof database.prepare === "function" && typeof database.batch === "function";
}

function batchSucceeded(value, expected) {
  return Array.isArray(value) && value.length === expected &&
    value.every((entry) => entry?.success === true);
}

async function persistValid(database, row, affiliateUrl, checkedAt) {
  const statements = [
    database.prepare(`INSERT INTO affiliate_redirect_target
      (public_id, content_id, affiliate_url, verified_at) VALUES (?, ?, ?, ?)
      ON CONFLICT(public_id) DO UPDATE SET
        content_id = excluded.content_id,
        affiliate_url = excluded.affiliate_url,
        verified_at = excluded.verified_at`).bind(
      row.public_id, row.content_id, affiliateUrl, checkedAt,
    ),
    database.prepare(`UPDATE affiliate_item_lookup SET
      verification_status = 'PASS', affiliate_enabled = 1, updated_at = ?
      WHERE public_id = ? AND content_id = ?
        AND rights_status = 'CONDITIONALLY_APPROVED'
        AND lifecycle_status = 'RESOLVED'`).bind(
      checkedAt, row.public_id, row.content_id,
    ),
    database.prepare(`INSERT INTO affiliate_lifecycle_revalidation_event
      (public_id, checked_at, outcome, affiliate_enabled_after, reason_code)
      VALUES (?, ?, 'VALID', 1, 'OFFICIAL_API_EXACT_MATCH')`).bind(
      row.public_id, checkedAt,
    ),
  ];
  return batchSucceeded(await database.batch(statements), statements.length);
}

async function persistBlocked(database, row, checkedAt, reasonCode) {
  const unavailable = reasonCode === "PROVIDER_RESPONSE_INVALID";
  const outcome = unavailable ? "NOT_AVAILABLE" : "UNCONFIRMED";
  const verification = unavailable ? "FAILED" : "PENDING";
  const statements = [
    database.prepare(`UPDATE affiliate_item_lookup SET
      verification_status = ?, affiliate_enabled = 0, updated_at = ?
      WHERE public_id = ? AND content_id = ?`).bind(
      verification, checkedAt, row.public_id, row.content_id,
    ),
    database.prepare(`INSERT INTO affiliate_lifecycle_revalidation_event
      (public_id, checked_at, outcome, affiliate_enabled_after, reason_code)
      VALUES (?, ?, ?, 0, ?)`).bind(
      row.public_id, checkedAt, outcome, reasonCode,
    ),
  ];
  return batchSucceeded(await database.batch(statements), statements.length);
}

export async function runAffiliateLifecycleRevalidation(
  env, fetcher = fetch, checkedAt = new Date().toISOString(),
) {
  try {
    if (!databaseReady(env) || typeof env?.DMM_API_ID !== "string" || !env.DMM_API_ID ||
        typeof env?.DMM_AFFILIATE_ID !== "string" || !env.DMM_AFFILIATE_ID ||
        typeof fetcher !== "function" || typeof checkedAt !== "string" || !checkedAt) {
      return result("FAIL_CLOSED", 0, 0, 0, "REVALIDATION_BINDING_UNAVAILABLE");
    }
    const query = await env.AFFILIATE_ITEM_LOOKUP.prepare(SELECT_SQL).all();
    if (!query || query.success !== true || !Array.isArray(query.results) ||
        query.results.length > BATCH_SIZE) {
      return result("FAIL_CLOSED", 0, 0, 0, "REVALIDATION_SELECTION_FAILED");
    }
    let valid = 0;
    let disabled = 0;
    for (const row of query.results) {
      if (!row || Object.keys(row).length !== 2 || !PUBLIC_ID.test(row.public_id) ||
          !CONTENT_ID.test(row.content_id)) {
        return result("FAIL_CLOSED", valid + disabled, valid, disabled, "REVALIDATION_ROW_INVALID");
      }
      let affiliateUrl = null;
      const provider = await fetchAndDeliverDmmAffiliateUrl(
        env, row.content_id, async (value) => { affiliateUrl = value; }, fetcher,
      );
      if (provider.status === "DELIVERED" && typeof affiliateUrl === "string") {
        if (!await persistValid(env.AFFILIATE_ITEM_LOOKUP, row, affiliateUrl, checkedAt)) {
          return result("FAIL_CLOSED", valid + disabled, valid, disabled, "REVALIDATION_WRITE_FAILED");
        }
        valid += 1;
      } else {
        const reasonCode = provider?.reason_codes?.[0] || "PROVIDER_INTERNAL_ERROR";
        if (!await persistBlocked(env.AFFILIATE_ITEM_LOOKUP, row, checkedAt, reasonCode)) {
          return result("FAIL_CLOSED", valid + disabled, valid, disabled, "REVALIDATION_WRITE_FAILED");
        }
        disabled += 1;
      }
    }
    return result("COMPLETED", query.results.length, valid, disabled, "BOUNDED_REVALIDATION_COMPLETED");
  } catch (_) {
    return result("FAIL_CLOSED", 0, 0, 0, "REVALIDATION_INTERNAL_ERROR");
  }
}

export const AFFILIATE_LIFECYCLE_REVALIDATION_VERSION = "0.1";
export const AFFILIATE_LIFECYCLE_REVALIDATION_BATCH_SIZE = BATCH_SIZE;
export const AFFILIATE_LIFECYCLE_REVALIDATION_SELECT_SQL = SELECT_SQL;
