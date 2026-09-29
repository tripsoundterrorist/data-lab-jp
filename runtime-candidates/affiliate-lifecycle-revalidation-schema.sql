CREATE TABLE affiliate_lifecycle_revalidation_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL
        REFERENCES affiliate_item_lookup(public_id) ON DELETE CASCADE,
    checked_at TEXT NOT NULL,
    outcome TEXT NOT NULL
        CHECK (outcome IN ('VALID', 'NOT_AVAILABLE', 'UNCONFIRMED')),
    affiliate_enabled_after INTEGER NOT NULL
        CHECK (affiliate_enabled_after IN (0, 1)),
    reason_code TEXT NOT NULL
        CHECK (length(reason_code) BETWEEN 1 AND 96)
) STRICT;

CREATE INDEX affiliate_lifecycle_revalidation_event_public_checked
ON affiliate_lifecycle_revalidation_event(public_id, checked_at DESC);
