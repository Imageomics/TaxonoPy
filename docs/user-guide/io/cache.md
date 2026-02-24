# Cache

TaxonoPy caches intermediate results (like parsed inputs and grouped entries) to speed up repeated runs on the same dataset.

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
- a fingerprint of the input files.

The namespace determines the subdirectory under the base cache dir:

`{base}/{command}_v{version}_{fingerprint}/`

where `{fingerprint}` is a 16-hex-character hash of each input file's path, size, and modification time.

For example, running `taxonopy resolve -i examples/input -o examples/resolved` with TaxonoPy v0.2.0 would create a cache at:

`~/.cache/taxonopy/resolve_v0.2.0_a3f9b2c1d4e5f678/`

This keeps caches isolated across datasets and releases.

## Useful CLI Flags

- `--show-cache-path` — print the active cache directory and exit.
- `--cache-stats` — show cache statistics and exit.
- `--clear-cache` — remove cached objects.
- `--refresh-cache` (resolve only) — ignore cached parse/group results.
- `--full-rerun` (resolve only) — clear the input-scoped cache and remove TaxonoPy-specific output files before rerunning. See [Reruns](reruns.md) for full details.

If you change input files or want to force a clean run, use `--refresh-cache` or `--full-rerun`.
