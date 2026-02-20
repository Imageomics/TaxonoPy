# Reruns

## The Guard

TaxonoPy checks for existing output before processing. If a prior run is
detected for the current input, it exits with a warning rather than silently
overwriting:

```
Existing cache (...) and/or output (...) detected for this input.
Rerun with --full-rerun to replace them.
```

Detection uses two signals:

- the presence of a `taxonopy_resolve_manifest.json` in the output directory
  (written by any run using TaxonoPy v0.3.0 or later), or
- `.resolved.*` files in the output directory root (legacy fallback for output
  produced by earlier versions).

## `--full-rerun`

`--full-rerun` is the explicit escape hatch through the guard. It clears the
input-scoped cache namespace and removes all TaxonoPy-specific files from the
output directory before proceeding.

```console
taxonopy resolve \
    --input examples/input \
    --output-dir examples/resolved \
    --full-rerun
```

### What it touches

- **Cache**: the namespace scoped to the current command, TaxonoPy version, and
  input fingerprint. Other namespaces (different inputs, different versions) are
  not affected.
- **Output files**: only the files listed in `taxonopy_resolve_manifest.json`.
  Any other files in the output directory are left untouched.

### What it does not touch

- Files not listed in the manifest — including any non-TaxonoPy files you have
  placed in the output directory.
- Cache namespaces from other runs.

### No manifest found

If `--full-rerun` is used but no manifest is present (e.g. output from a
pre-v0.3.0 run, or a manually populated directory), TaxonoPy logs a warning
and proceeds without removing any files:

```
--full-rerun: no manifest found in <output-dir>; no output files were removed.
```

The run then writes fresh output and a new manifest.

## The Manifest

Every TaxonoPy run writes a manifest file to the output directory **before**
creating any output. This means interrupted runs leave a complete record of
what should be cleaned up — `--full-rerun` deletes exactly those files and
nothing else.

Manifest files are command-scoped so they coexist safely if multiple commands
share an output directory:

| Command | Manifest file |
|---|---|
| `resolve` | `taxonopy_resolve_manifest.json` |
| `common-names` | `taxonopy_common_names_manifest.json` |

### Schema

```json
{
    "taxonopy_version": "0.3.0",
    "command": "resolve",
    "created_at": "2025-07-19T10:38:04.123456",
    "input": "examples/input",
    "cache_namespace": "~/.cache/taxonopy/resolve_v0.3.0_a3f9b2c1d4e5f678",
    "files": [
        "sample.resolved.parquet",
        "sample.unsolved.parquet",
        "resolution_stats.json",
        "taxonopy_resolve_manifest.json"
    ]
}
```

All paths in `files` are relative to the output directory. `cache_namespace`
is `null` for `common-names`, which does not use an input-scoped cache.
