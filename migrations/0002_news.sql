-- Wave 3A advisory news metadata persistence.
-- Idempotent only: no destructive actions, no secrets, no article text storage.

CREATE TABLE IF NOT EXISTS news_items (
  item_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  normalized_symbol TEXT NOT NULL,
  provider TEXT NOT NULL,
  source_name TEXT,
  domain TEXT,
  title TEXT NOT NULL,
  snippet TEXT,
  url TEXT NOT NULL,
  url_hash TEXT NOT NULL,
  title_hash TEXT NOT NULL,
  published_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ,
  language TEXT,
  macro_or_micro TEXT,
  event_class TEXT,
  relevance_score NUMERIC,
  freshness_score NUMERIC,
  source_authority_score NUMERIC,
  confidence_score NUMERIC,
  cluster_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_clusters (
  cluster_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  normalized_symbol TEXT NOT NULL,
  representative_title TEXT NOT NULL,
  macro_or_micro TEXT,
  event_class TEXT,
  source_count INTEGER,
  item_count INTEGER,
  dropped_count INTEGER,
  max_relevance_score NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_evidence_links (
  run_id TEXT NOT NULL,
  cluster_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  evidence_type TEXT NOT NULL,
  relevance_score NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, cluster_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_news_items_run ON news_items (run_id);
CREATE INDEX IF NOT EXISTS idx_news_items_symbol ON news_items (normalized_symbol);
CREATE INDEX IF NOT EXISTS idx_news_items_cluster ON news_items (cluster_id);
CREATE INDEX IF NOT EXISTS idx_news_clusters_run ON news_clusters (run_id);
CREATE INDEX IF NOT EXISTS idx_news_evidence_links_run ON news_evidence_links (run_id);
