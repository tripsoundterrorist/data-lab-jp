PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS category_sources (
  source_id INTEGER PRIMARY KEY,
  content_type TEXT NOT NULL UNIQUE,
  site TEXT NOT NULL,
  service TEXT NOT NULL,
  floor TEXT NOT NULL,
  collection_mode TEXT NOT NULL CHECK (collection_mode = 'COLLECTION_ONLY'),
  publication_allowed INTEGER NOT NULL DEFAULT 0 CHECK (publication_allowed = 0),
  UNIQUE (site, service, floor)
) STRICT;

CREATE TABLE IF NOT EXISTS category_collection_runs (
  run_id TEXT PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES category_sources(source_id),
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('running','success','failed')),
  source_sort TEXT NOT NULL,
  requested_hits INTEGER NOT NULL CHECK (requested_hits BETWEEN 1 AND 100),
  fetched_items INTEGER CHECK (fetched_items IS NULL OR fetched_items >= 0),
  total_count INTEGER CHECK (total_count IS NULL OR total_count >= 0),
  response_sha256 TEXT,
  error_code TEXT,
  publication_allowed INTEGER NOT NULL DEFAULT 0 CHECK (publication_allowed = 0),
  CHECK (status = 'running' OR finished_at IS NOT NULL),
  CHECK (status != 'success' OR (fetched_items IS NOT NULL AND response_sha256 IS NOT NULL)),
  CHECK (status != 'failed' OR error_code IS NOT NULL)
) STRICT;

CREATE TABLE IF NOT EXISTS category_items (
  item_id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES category_sources(source_id),
  content_id TEXT NOT NULL,
  product_id TEXT,
  title TEXT,
  release_date_raw TEXT,
  item_url TEXT,
  image_json TEXT CHECK (image_json IS NULL OR json_valid(image_json)),
  contributors_json TEXT NOT NULL CHECK (json_valid(contributors_json)),
  series_json TEXT NOT NULL CHECK (json_valid(series_json)),
  genre_json TEXT NOT NULL CHECK (json_valid(genre_json)),
  source_extension_json TEXT NOT NULL CHECK (json_valid(source_extension_json)),
  first_observed_at TEXT NOT NULL,
  last_observed_at TEXT NOT NULL,
  normalizer_version TEXT NOT NULL,
  publication_allowed INTEGER NOT NULL DEFAULT 0 CHECK (publication_allowed = 0),
  UNIQUE (source_id, content_id)
) STRICT;

CREATE TABLE IF NOT EXISTS category_item_snapshots (
  snapshot_id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES category_items(item_id) ON DELETE CASCADE,
  run_id TEXT NOT NULL REFERENCES category_collection_runs(run_id) ON DELETE RESTRICT,
  observed_at TEXT NOT NULL,
  current_price_raw TEXT,
  current_price_min INTEGER CHECK (current_price_min IS NULL OR current_price_min >= 0),
  list_price_raw TEXT,
  list_price_min INTEGER CHECK (list_price_min IS NULL OR list_price_min >= 0),
  discount_amount INTEGER CHECK (discount_amount IS NULL OR discount_amount >= 0),
  discount_rate REAL CHECK (discount_rate IS NULL OR discount_rate BETWEEN 0 AND 100),
  review_average REAL CHECK (review_average IS NULL OR review_average >= 0),
  review_count INTEGER CHECK (review_count IS NULL OR review_count >= 0),
  source_sort TEXT NOT NULL,
  source_position INTEGER NOT NULL CHECK (source_position >= 1),
  delivery_json TEXT CHECK (delivery_json IS NULL OR json_valid(delivery_json)),
  sanitized_raw_json TEXT NOT NULL CHECK (json_valid(sanitized_raw_json)),
  publication_allowed INTEGER NOT NULL DEFAULT 0 CHECK (publication_allowed = 0),
  UNIQUE (run_id, source_position)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_category_snapshots_observed
  ON category_item_snapshots(observed_at DESC);
