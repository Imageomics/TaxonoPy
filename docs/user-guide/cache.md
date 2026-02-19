# Cache

TaxonoPy caches intermediate results (like parsed inputs and grouped entries) to
speed up repeated runs on the same dataset.

## Location

By default, the cache lives under:

- `~/.cache/taxonopy`

You can override this with:

- `TAXONOPY_CACHE_DIR` environment variable, or
- `--cache-dir` CLI flag.

## Namespaces and Reproducibility

Each `resolve` run uses a cache namespace derived from:

- the command name,
- the TaxonoPy version, and
- a fingerprint of the input files (paths + size + modified time).

This keeps caches isolated across datasets and releases.

## Useful CLI Flags

- `--show-cache-path` — print the active cache directory and exit.
- `--cache-stats` — show cache statistics and exit.
- `--clear-cache` — remove cached objects.
- `--refresh-cache` (resolve only) — ignore cached parse/group results.
- `--full-rerun` (resolve only) — clear cache for the input and overwrite outputs.

If you change input files or want to force a clean run, use `--refresh-cache` or
`--full-rerun`.
