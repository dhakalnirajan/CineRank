-- MySQL 8 / InnoDB reference equivalent of the Python catalogue service.
-- Ensure movies.sort_key uses a compatible utf8mb4 character set. The explicit
-- binary collation is required for deterministic ordering independent of the
-- database's default case/accent-insensitive collation.
START TRANSACTION;

INSERT INTO catalogue_state (id, active_version)
VALUES (1, 0)
ON DUPLICATE KEY UPDATE id = VALUES(id);

SELECT active_version INTO @current_version
FROM catalogue_state
WHERE id = 1
FOR UPDATE;
SET @next_version = @current_version + 1;

DELETE FROM catalogue_sort_index WHERE version_id > @current_version;

INSERT INTO catalogue_sort_index (version_id, title_id, sort_order)
SELECT @next_version,
       ordered.title_id,
       ordered.position
FROM (
    SELECT movie.title_id,
           ROW_NUMBER() OVER (
               ORDER BY movie.sort_key COLLATE utf8mb4_bin ASC, movie.title_id ASC
           ) AS position
    FROM movies AS movie
) AS ordered;

UPDATE catalogue_state
SET active_version = @next_version,
    published_at = CURRENT_TIMESTAMP(6)
WHERE id = 1;

DELETE FROM catalogue_sort_index
WHERE version_id < GREATEST(1, @next_version - 1);

COMMIT;
