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
  UNIQUE (collection_run_id, source_offset, source_position),
  CHECK (source_position >= 1),
  CHECK (price_min IS NULL OR price_min >= 0),
  CHECK (review_average IS NULL OR review_average >= 0),
  CHECK (review_count IS NULL OR review_count >= 0)
) STRICT;

CREATE INDEX idx_item_snapshots_observed_at
  ON item_snapshots (observed_at DESC);
