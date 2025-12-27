# ADR 0002: Append-once Parquet + DuckDB Reads

## Context

CSV day files were growing unbounded, painful to compact, and slow to read. We need safe writes during market hours and fast reads for UI/algos.

## Decision

- **Writes:** one-row Parquet parts per candle/object event; compact after close.
- **Reads:** in-memory DuckDB over `read_parquet(glob)`; SQL for last-event-per-object and time/price filters.

### Note on objects

Events are appended to a daily **timeline**, and we also materialize a **current snapshot** for fast reads. The UI/viewport queries the snapshot (filtering by `status/top/bottom`), while DuckDB “last event per id” queries remain useful for audits/rebuilds.

## Alternatives

- **Single SQLite file**: simple but write contention and VACUUM pauses during session.
- **Big CSVs**: easiest to inspect but slow IO and brittle parsing.
- **Postgres**: powerful, but adds infra and network round-trips we don’t need yet.

## Consequences

- Tiny files during session (lots of inodes) → addressed by daily/monthly compaction.
- Easy local dev; cloud/object storage friendly later (S3/MinIO).
