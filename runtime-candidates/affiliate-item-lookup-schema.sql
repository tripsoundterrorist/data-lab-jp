CREATE TABLE affiliate_item_lookup (
    public_id TEXT PRIMARY KEY
        CHECK (
            length(public_id) = 28
            AND substr(public_id, 1, 4) = 'itm_'
            AND substr(public_id, 5) NOT GLOB '*[^0-9a-f]*'
        ),
    content_id TEXT NOT NULL UNIQUE
        CHECK (
            length(content_id) BETWEEN 1 AND 128
            AND content_id NOT GLOB '*[^A-Za-z0-9._-]*'
        ),
    rights_status TEXT NOT NULL DEFAULT 'PENDING_SEPARATE_POLICY'
        CHECK (rights_status IN (
            'CONDITIONALLY_APPROVED',
            'PENDING_SEPARATE_POLICY',
            'PROHIBITED'
        )),
    lifecycle_status TEXT NOT NULL DEFAULT 'PENDING_OFFICIAL_CONFIRMATION'
        CHECK (lifecycle_status IN (
            'PENDING_OFFICIAL_CONFIRMATION',
            'RESOLVED'
        )),
    verification_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (verification_status IN ('PASS', 'PENDING', 'FAILED')),
    affiliate_enabled INTEGER NOT NULL DEFAULT 0
        CHECK (affiliate_enabled IN (0, 1)),
    updated_at TEXT NOT NULL,
    CHECK (
        affiliate_enabled = 0
        OR (
            rights_status = 'CONDITIONALLY_APPROVED'
            AND lifecycle_status = 'RESOLVED'
            AND verification_status = 'PASS'
        )
    )
) STRICT;

CREATE VIEW affiliate_runtime_eligible_lookup AS
SELECT public_id, content_id
FROM affiliate_item_lookup
WHERE affiliate_enabled = 1
  AND rights_status = 'CONDITIONALLY_APPROVED'
  AND lifecycle_status = 'RESOLVED'
  AND verification_status = 'PASS';
