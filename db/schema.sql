PRAGMA foreign_keys = ON;

CREATE TABLE items (
  id INTEGER PRIMARY KEY,
  site TEXT NOT NULL,
  service TEXT NOT NULL,
  floor TEXT NOT NULL,
  content_id TEXT NOT NULL,
  product_id TEXT,
  title TEXT,
  source_date TEXT,
  -- JSON arrays containing the id and name values returned by the DMM API.
  maker_json TEXT CHECK (maker_json IS NULL OR json_valid(maker_json)),
  series_json TEXT CHECK (series_json IS NULL OR json_valid(series_json)),
  actress_json TEXT CHECK (actress_json IS NULL OR json_valid(actress_json)),
  genre_json TEXT CHECK (genre_json IS NULL OR json_valid(genre_json)),
  image_url_large TEXT,
  item_url TEXT,
  first_observed_at TEXT NOT NULL,
  last_observed_at TEXT NOT NULL,
  master_updated_at TEXT NOT NULL,
  UNIQUE (site, service, floor, content_id)
) STRICT;

CREATE TABLE collection_runs (
  collection_run_id TEXT PRIMARY KEY,
  run_type TEXT NOT NULL
    CHECK (run_type IN ('native', 'legacy_migrated')),
  started_at TEXT,
  finished_at TEXT,
  first_observed_at TEXT,
  last_observed_at TEXT,
  site TEXT,
  service TEXT,
  floor TEXT,
  source_sort TEXT,
  hits INTEGER CHECK (hits IS NULL OR hits > 0),
  max_items INTEGER CHECK (max_items IS NULL OR max_items > 0),
  max_pages INTEGER CHECK (max_pages IS NULL OR max_pages > 0),
  api_calls INTEGER CHECK (api_calls IS NULL OR api_calls >= 0),
  pages_fetched INTEGER CHECK (pages_fetched IS NULL OR pages_fetched >= 0),
  api_total_count_initial INTEGER
    CHECK (api_total_count_initial IS NULL OR api_total_count_initial >= 0),
  total_count_changed INTEGER
    CHECK (total_count_changed IS NULL OR total_count_changed IN (0, 1)),
  fetched_items INTEGER CHECK (fetched_items IS NULL OR fetched_items >= 0),
  processed_items INTEGER
    CHECK (processed_items IS NULL OR processed_items >= 0),
  duplicate_content_ids_across_pages INTEGER
    CHECK (
      duplicate_content_ids_across_pages IS NULL
      OR duplicate_content_ids_across_pages >= 0
    ),
  items_upserted INTEGER
    CHECK (items_upserted IS NULL OR items_upserted >= 0),
  -- For legacy_migrated rows, this is the currently preserved snapshot count.
  snapshots_inserted INTEGER
    CHECK (snapshots_inserted IS NULL OR snapshots_inserted >= 0),
  collection_complete INTEGER
    CHECK (collection_complete IS NULL OR collection_complete IN (0, 1)),
  status TEXT NOT NULL
    CHECK (status IN ('running', 'success', 'failed', 'unknown')),
  stop_reason TEXT CHECK (
    stop_reason IS NULL OR stop_reason IN (
      'api_end',
      'max_items',
      'max_pages',
      'api_error',
      'validation_error',
      'db_error',
      'unexpected_error'
    )
  ),
  -- Safe internal code only; never store exception text, URLs, or response bodies.
  error_code TEXT,
  CHECK (
    run_type != 'native'
    OR (
      started_at IS NOT NULL
      AND site IS NOT NULL
      AND service IS NOT NULL
      AND floor IS NOT NULL
      AND source_sort IS NOT NULL
      AND hits IS NOT NULL
      AND max_items IS NOT NULL
      AND max_pages IS NOT NULL
      AND status IN ('running', 'success', 'failed')
    )
  ),
  CHECK (status != 'running' OR finished_at IS NULL),
  CHECK (
    status NOT IN ('success', 'failed')
    OR finished_at IS NOT NULL
  ),
  CHECK (
    status != 'success'
    OR (
      collection_complete IS NOT NULL
      AND stop_reason IS NOT NULL
      AND first_observed_at IS NOT NULL
      AND last_observed_at IS NOT NULL
      AND api_calls IS NOT NULL
      AND pages_fetched IS NOT NULL
      AND api_total_count_initial IS NOT NULL
      AND total_count_changed IS NOT NULL
      AND fetched_items IS NOT NULL
      AND processed_items IS NOT NULL
      AND duplicate_content_ids_across_pages IS NOT NULL
      AND items_upserted IS NOT NULL
      AND snapshots_inserted IS NOT NULL
    )
  ),
  CHECK (
    status != 'failed'
    OR (
      collection_complete = 0
      AND stop_reason IS NOT NULL
      AND error_code IS NOT NULL
    )
  ),
  CHECK (
    run_type != 'legacy_migrated'
    OR (
      status = 'unknown'
      AND collection_complete IS NULL
      AND stop_reason IS NULL
      AND error_code IS NULL
    )
  )
) STRICT;

CREATE TABLE item_snapshots (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL,
  collection_run_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  source_sort TEXT NOT NULL,
  source_offset INTEGER NOT NULL CHECK (source_offset >= 0),
  -- One-based position within this API response.
  source_position INTEGER NOT NULL,
  price_raw TEXT,
  price_min INTEGER,
  review_average REAL,
  review_count INTEGER,
  -- Must not contain api_id, affiliate_id, full request URLs, or tokens.
  query_context_json TEXT NOT NULL CHECK (json_valid(query_context_json)),
  FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE,
  FOREIGN KEY (collection_run_id)
    REFERENCES collection_runs (collection_run_id) ON DELETE RESTRICT,
  UNIQUE (collection_run_id, source_offset, source_position),
  CHECK (source_position >= 1),
  CHECK (price_min IS NULL OR price_min >= 0),
  CHECK (review_average IS NULL OR review_average >= 0),
  CHECK (review_count IS NULL OR review_count >= 0)
) STRICT;

CREATE INDEX idx_item_snapshots_observed_at
  ON item_snapshots (observed_at DESC);
