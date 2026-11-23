-- SQL Server reference script. Run under SERIALIZABLE semantics for the state
-- row; UPDLOCK/HOLDLOCK serializes this publisher with writers using the same row.
SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF NOT EXISTS (SELECT 1 FROM catalogue_state WHERE id = 1)
    INSERT INTO catalogue_state (id, active_version) VALUES (1, 0);

DECLARE @current_version BIGINT;
DECLARE @next_version BIGINT;
SELECT @current_version = active_version
FROM catalogue_state WITH (UPDLOCK, HOLDLOCK)
WHERE id = 1;
SET @next_version = @current_version + 1;

DELETE FROM catalogue_sort_index WHERE version_id > @current_version;

INSERT INTO catalogue_sort_index (version_id, title_id, sort_order)
SELECT @next_version,
       ordered.title_id,
       ordered.position
FROM (
    SELECT movie.title_id,
           ROW_NUMBER() OVER (
               ORDER BY movie.sort_key COLLATE Latin1_General_100_BIN2 ASC, movie.title_id ASC
           ) AS position
    FROM movies AS movie
) AS ordered;

UPDATE catalogue_state
SET active_version = @next_version,
    published_at = SYSUTCDATETIME()
WHERE id = 1;

DELETE FROM catalogue_sort_index WHERE version_id < CASE WHEN @next_version > 1 THEN @next_version - 1 ELSE 1 END;
COMMIT TRANSACTION;
