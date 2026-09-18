-- Chapter 15's own tables, now under real migration control. IF NOT
-- EXISTS on purpose: any dev database that already ran chapter 15's
-- old ad-hoc bootstrapping already has these tables, this migration
-- reconciles that starting state instead of failing against it.

CREATE TABLE IF NOT EXISTS answer_cache (
    tenant_id TEXT NOT NULL,
    question_hash TEXT NOT NULL,
    answer TEXT NOT NULL,
    cited_packages TEXT[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, question_hash)
);

CREATE TABLE IF NOT EXISTS tenant_usage (
    tenant_id TEXT PRIMARY KEY,
    total_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    call_count INTEGER NOT NULL DEFAULT 0,
    cache_hit_count INTEGER NOT NULL DEFAULT 0
);
