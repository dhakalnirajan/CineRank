-- SQLite reference script. BEGIN IMMEDIATE obtains the single-writer reservation
-- before reading the active version, preventing concurrent inserts during build.
BEGIN IMMEDIATE;

INSERT OR IGNORE INTO catalogue_state (id, active_version) VALUES (1, 0);

DELETE FROM catalogue_sort_index
WHERE version_id > (SELECT active_version FROM catalogue_state WHERE id = 1);

INSERT INTO catalogue_sort_index (version_id, title_id, sort_order)
SELECT (SELECT active_version + 1 FROM catalogue_state WHERE id = 1),
       movie.title_id,
       ROW_NUMBER() OVER (ORDER BY movie.sort_key COLLATE BINARY ASC, movie.title_id ASC)
FROM movies AS movie;

UPDATE catalogue_state
SET active_version = active_version + 1,
    published_at = CURRENT_TIMESTAMP
WHERE id = 1;

DELETE FROM catalogue_sort_index
WHERE version_id < MAX(1, (SELECT active_version - 1 FROM catalogue_state WHERE id = 1));

COMMIT;
