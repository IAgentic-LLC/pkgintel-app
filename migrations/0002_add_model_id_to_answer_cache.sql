-- No default value, and no NOT NULL: since PostgreSQL 11, ADD COLUMN
-- with no default (or a non-volatile constant default) is a real
-- metadata-only operation, no table rewrite, confirmed live against
-- Postgres's own current documentation. Real traffic against
-- answer_cache keeps running unaffected while this applies.
--
-- The real reason for this column: after a GEMINI_MODEL_ID upgrade,
-- an operator needs a real way to tell which cached answers came from
-- the model that's now been replaced, not a guess.

ALTER TABLE answer_cache ADD COLUMN IF NOT EXISTS model_id TEXT;
