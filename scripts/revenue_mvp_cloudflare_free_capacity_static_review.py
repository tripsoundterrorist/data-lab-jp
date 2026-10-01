"""Static, non-network Cloudflare Free capacity review for Revenue MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


VERSION = "0.1"
REVIEW_READY = "STATIC_CAPACITY_REVIEW_READY"
BLOCKED = "STATIC_CAPACITY_REVIEW_BLOCKED"
ROOT = Path(__file__).resolve().parents[1]

# Official Cloudflare documentation reviewed on 2026-10-01.
WORKERS_FREE_REQUESTS_PER_DAY = 100_000
WORKERS_FREE_CPU_MS_PER_REQUEST = 10
D1_FREE_ROWS_READ_PER_DAY = 5_000_000
D1_FREE_ROWS_WRITTEN_PER_DAY = 100_000
D1_FREE_DATABASE_BYTES = 500_000_000
D1_FREE_ACCOUNT_STORAGE_BYTES = 5_000_000_000
D1_FREE_QUERIES_PER_INVOCATION = 50
TARGET_ITEM_COUNT = 300


@dataclass(frozen=True)
class StaticCapacityReview:
    version: str
    status: str
    target_item_count: int
    workers_free_requests_per_day: int
    workers_free_cpu_ms_per_request: int
    d1_free_rows_read_per_day: int
    d1_free_rows_written_per_day: int
    d1_free_database_bytes: int
    d1_free_account_storage_bytes: int
    d1_free_queries_per_invocation: int
    cta_worker_requests_per_click: int
    cta_d1_queries_per_click: int
    lifecycle_batch_size: int
    workers_dev_disabled: bool
    preview_urls_disabled: bool
    paid_plan_required_by_static_design: bool
    cloudflare_free_plan_capacity_verified: bool
    dashboard_observation_required: bool
    activation_scope_target_ready: bool
    production_change_allowed: bool
    reason_codes: tuple[str, ...]
    dashboard_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["dashboard_checks"] = list(self.dashboard_checks)
        return value


def review(root: Path = ROOT) -> StaticCapacityReview:
    reasons: set[str] = set()
    workers_dev_disabled = False
    preview_urls_disabled = False
    lifecycle_batch_size = 0
    activation_scope_target_ready = False
    try:
        config = (root / "deployment-candidates" / "affiliate-worker" /
                  "wrangler.toml").read_text(encoding="utf-8")
        entrypoint = (root / "deployment-candidates" / "affiliate-worker" /
                      "src" / "index.mjs").read_text(encoding="utf-8")
        adapter = (root / "runtime-candidates" /
                   "affiliate-d1-runtime-adapter.mjs").read_text(encoding="utf-8")
        lifecycle = (root / "runtime-candidates" /
                     "affiliate-lifecycle-revalidation.mjs").read_text(encoding="utf-8")

        workers_dev_disabled = "workers_dev = false" in config
        preview_urls_disabled = "preview_urls = false" in config
        if not workers_dev_disabled:
            reasons.add("WORKERS_DEV_NOT_DISABLED")
        if not preview_urls_disabled:
            reasons.add("PREVIEW_URLS_NOT_DISABLED")
        if "[limits]" in config or "cpu_ms" in config:
            reasons.add("FREE_PLAN_CPU_OVERRIDE_PRESENT")
        if 'LIMIT 2"' not in adapter or "WHERE public_id = ?" not in adapter:
            reasons.add("CTA_LOOKUP_NOT_BOUNDED")
        if "const BATCH_SIZE = 5;" in lifecycle and "LIMIT 5`" in lifecycle:
            lifecycle_batch_size = 5
        else:
            reasons.add("LIFECYCLE_BATCH_NOT_BOUNDED")
        activation_scope_target_ready = "itemCount: 300" in entrypoint
    except (OSError, UnicodeError):
        reasons.add("CAPACITY_SOURCE_EVIDENCE_INVALID")

    ready = not reasons
    return StaticCapacityReview(
        VERSION,
        REVIEW_READY if ready else BLOCKED,
        TARGET_ITEM_COUNT,
        WORKERS_FREE_REQUESTS_PER_DAY,
        WORKERS_FREE_CPU_MS_PER_REQUEST,
        D1_FREE_ROWS_READ_PER_DAY,
        D1_FREE_ROWS_WRITTEN_PER_DAY,
        D1_FREE_DATABASE_BYTES,
        D1_FREE_ACCOUNT_STORAGE_BYTES,
        D1_FREE_QUERIES_PER_INVOCATION,
        1,
        1,
        lifecycle_batch_size,
        workers_dev_disabled,
        preview_urls_disabled,
        False,
        False,
        True,
        activation_scope_target_ready,
        False,
        tuple(sorted(reasons)),
        (
            "WORKERS_REQUESTS_24H_AND_CPU_LIMIT_ERRORS",
            "D1_ROWS_READ_24H",
            "D1_ROWS_WRITTEN_24H",
            "D1_DATABASE_AND_ACCOUNT_STORAGE",
            "ACTIVE_CRON_TRIGGER_COUNT_AND_SCHEDULE",
        ),
    )


def main() -> int:
    result = review()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == REVIEW_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
