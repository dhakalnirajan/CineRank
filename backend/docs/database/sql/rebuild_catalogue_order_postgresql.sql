-- PostgreSQL reference equivalent of app.services.catalogue_service.
-- Run after the catalogue ingestion transaction has completed. The singleton
-- catalogue_state row serializes this rebuild with writers using the same row.
BEGIN;

-- Ensure the singleton state exists before taking the row lock.
INSERT INTO catalogue_state (id, active_version)
VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;

SELECT active_version
FROM catalogue_state
WHERE id = 1
FOR UPDATE;

-- Remove any abandoned, unpublished staging versions.
DELETE FROM catalogue_sort_index
WHERE version_id > (SELECT active_version FROM catalogue_state WHERE id = 1);

-- Build the next version. sort_key is NFKC + casefold normalized by Python;
-- COLLATE "C" makes this a deterministic byte/code-point style ordering.
INSERT INTO catalogue_sort_index (version_id, title_id, sort_order)
SELECT state.active_version + 1,
       movie.title_id,
       ROW_NUMBER() OVER (ORDER BY movie.sort_key COLLATE "C" ASC, movie.title_id ASC)
FROM movies AS movie
CROSS JOIN catalogue_state AS state
WHERE state.id = 1;

-- Publish in the same transaction, only after all rows were inserted.
UPDATE catalogue_state
SET active_version = active_version + 1,
    published_at = CURRENT_TIMESTAMP
WHERE id = 1;

-- Keep the active and immediately previous version for in-flight readers.
DELETE FROM catalogue_sort_index
WHERE version_id < GREATEST(1, (SELECT active_version FROM catalogue_state WHERE id = 1) - 1);

COMMIT;
