-- concurrent
-- A regular CREATE INDEX takes a SHARE lock that blocks every INSERT,
-- UPDATE, and DELETE against answer_cache until the build finishes,
-- confirmed against Postgres's own current documentation, not
-- assumed. CONCURRENTLY takes a ShareUpdateExclusiveLock instead,
-- which blocks other schema changes but never blocks ordinary
-- read/write traffic, real cost: it cannot run inside a transaction
-- block at all, this migration's own runner handles that by applying
-- it in autocommit mode instead of the usual one.
--
-- What this index is actually for: purge_stale_entries' own DELETE,
-- scanning by created_at, chapter 17's own live EXPLAIN proves the
-- difference this makes.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_answer_cache_created_at
    ON answer_cache (created_at);
